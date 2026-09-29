"""手元確認用の操作画面。配信出力とは別窓。"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE, OUTPUT_WINDOW_TITLE, display_version
from stream_heartbeat.audio import MicMonitor, MicTap, list_mics
from stream_heartbeat.clock import DisplayClock
from stream_heartbeat.config import (
    DISCLAIMER,
    LIVE_STATUS,
    PREVIEW_IDLE_STATUS,
    PREVIEW_LOST_STATUS,
)
from stream_heartbeat.oshilog import AuxBpmPoller
from stream_heartbeat.paths import resolve_data_dir
from stream_heartbeat.profile import (
    HeartProfile,
    load_last_profile_name,
    load_profile,
    profiles_dir,
    save_app_state,
    save_last_profile_name,
    save_profile,
)
from stream_heartbeat.samples import AUDIO_FILTER, load_audio_mono
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon
from stream_heartbeat.ui.combo import MarkedComboBox
from stream_heartbeat.ui.forms import CenteredForm
from stream_heartbeat.ui.heart_paint import (
    BACKDROPS,
    BPM_COLORS,
    BPM_OUTLINES,
    GL_STYLES,
    ROTATABLE_STYLES,
)
from stream_heartbeat.ui.operator_controls import ProfileControlsMixin
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.placement import window_geom
from stream_heartbeat.ui.slider import labeled_slider
from stream_heartbeat.ui.styles import DARK_QSS

STYLES = [
    ("realistic", "surgical", "リアル1"),
    ("realistic", "vivid", "リアル2"),
    ("realistic", "anatomy", "リアル3"),
    ("echo", "", "心エコー"),
    ("mri", "", "MRI"),
    ("xray", "", "レントゲン1"),
    ("xray_heart", "", "レントゲン2"),
    ("cute", "", "かわいい"),
    ("mech", "", "機械"),
    ("ecg", "", "心電図"),
]
GL_FAIL_LABEL = "立体表示を使えないため 2D で描いています"
CAL_START = "補正開始"
CAL_SAVE = "補正を保存"
CAL_DISCARD = "補正を破棄"
CAL_RESET = "設定を初期化"
NOTICE_MS = 3500
# この秒数マイクから何も届かなければ、抜けたか止まったとみなして知らせる
NO_AUDIO_S = 2.0
NO_AUDIO_LABEL = "マイクから音が届いていません。つながりと、選んだマイクを確かめてください"
SAVE_FAIL_LABEL = "保存できませんでした（ファイルが使用中か、空き容量が足りません）"


def _make_fold(
    title: str, inner: QWidget, *, expanded: bool = False
) -> tuple[QWidget, QToolButton]:
    toggle = QToolButton()
    toggle.setObjectName("fold")
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    toggle.setArrowType(Qt.ArrowType.NoArrow)
    inner.setVisible(expanded)

    def _sync(on: bool) -> None:
        inner.setVisible(on)
        toggle.setText(f"{'▼' if on else '▶'} {title}")

    toggle.toggled.connect(_sync)
    _sync(expanded)
    wrap = QWidget()
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(toggle)
    layout.addWidget(inner)
    return wrap, toggle


def _right(widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(widget)
    return row


def _toggle_box(
    title: str, check: QCheckBox, form: QFormLayout, reset: QPushButton
) -> tuple[QGroupBox, QWidget]:
    """チェックを外している間は細かい設定を畳む。"""
    details = QWidget()
    inner = QVBoxLayout(details)
    inner.setContentsMargins(0, 0, 0, 0)
    inner.addLayout(form)
    inner.addLayout(_right(reset))
    col = QVBoxLayout()
    col.addWidget(check)
    col.addWidget(details)
    box = QGroupBox(title)
    box.setLayout(col)
    return box, details


class OperatorWindow(ProfileControlsMixin, QMainWindow):
    def __init__(self, session: HeartSession, output: OutputWindow) -> None:
        super().__init__()
        self._session = session
        self._output = output
        self._mic = MicTap()
        self._monitor = MicMonitor()
        self._data_dir = resolve_data_dir()
        self._t0 = time.perf_counter()
        self._display_clock = DisplayClock()
        self._closing = False
        self._last_audio = 0.0
        self._no_audio = False
        self._mic_open = False
        # マイクの抜き差しを受けて一覧を作り直す
        self._devices = QMediaDevices(self)
        self._devices.audioInputsChanged.connect(self._on_mics_changed)
        self.setWindowTitle(OPERATOR_WINDOW_TITLE)
        self.setMinimumSize(440, 420)
        self.resize(500, 760)
        self.setStyleSheet(DARK_QSS)
        apply_app_icon(self)

        self._status = QLabel(PREVIEW_IDLE_STATUS)
        self._status.setObjectName("preview")
        self._status.setWordWrap(True)
        self._notice = QLabel("")
        self._notice.setObjectName("status")
        self._notice.setWordWrap(True)
        self._notice.hide()
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._clear_notice)
        self._aux = QLabel("推しログ(ぬ) 補助: —")
        self._aux.setObjectName("meta")
        self._aux.setWordWrap(True)
        self._warn = QLabel("")
        self._warn.setObjectName("warn")
        self._warn.setWordWrap(True)
        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setObjectName("disclaimer")
        disclaimer.setWordWrap(True)
        version = QLabel(display_version())
        version.setObjectName("meta")

        self._profiles = MarkedComboBox()
        self._profiles.setEditable(False)
        self._mics = MarkedComboBox()
        self._style = MarkedComboBox()
        for key, look, label in STYLES:
            self._style.addItem(label, (key, look))
        self._angle_locked = QCheckBox("角度を固定")
        self._angle_locked.setToolTip("配信用の窓をドラッグしても回さない")
        self._reset_angle = QPushButton("角度をリセット")
        self._angle_hint = QLabel("配信用の窓を左ドラッグで回転、ダブルクリックで元の向き。")
        self._angle_hint.setObjectName("meta")
        self._angle_hint.setWordWrap(True)
        self._gl_note = QLabel("")
        self._gl_note.setObjectName("warn")
        self._gl_note.setWordWrap(True)
        self._scale, scale_row = labeled_slider(20, 120, "小", "大")
        self._opacity, opacity_row = labeled_slider(10, 100, "透明", "不透明")
        self._text = QLineEdit()
        self._show_beat_text = QCheckBox("同期文字を配信用に出す")
        self._beat_scale, beat_scale_row = labeled_slider(50, 200, "小", "大")
        self._beat_opacity, beat_opacity_row = labeled_slider(10, 100, "透明", "不透明")
        self._beat_x, beat_x_row = labeled_slider(0, 100, "左", "右")
        self._beat_y, beat_y_row = labeled_slider(0, 100, "上", "下")
        self._beat_jitter, beat_jitter_row = labeled_slider(0, 40, "なし", "大")
        self._beat_tilt, beat_tilt_row = labeled_slider(0, 100, "なし", "強")
        self._beat_color = MarkedComboBox()
        self._beat_outline = MarkedComboBox()
        self._show_bpm = QCheckBox("心拍数を配信用に出す")
        self._bpm_scale, bpm_scale_row = labeled_slider(50, 200, "小", "大")
        self._bpm_x, bpm_x_row = labeled_slider(0, 100, "左", "右")
        self._bpm_y, bpm_y_row = labeled_slider(0, 100, "上", "下")
        self._bpm_color = MarkedComboBox()
        self._bpm_outline = MarkedComboBox()
        for hex_color, label in BPM_COLORS:
            self._beat_color.addItem(label, hex_color)
            self._bpm_color.addItem(label, hex_color)
        for hex_color, label in BPM_OUTLINES:
            self._beat_outline.addItem(label, hex_color)
            self._bpm_outline.addItem(label, hex_color)
        self._backdrop = MarkedComboBox()
        for key, label in BACKDROPS:
            self._backdrop.addItem(label, key)
        # 不整脈表示は判定が不安定なため、いったん出さない。
        # self._show_arrhythmia = QCheckBox("不整脈！を配信用に出す")
        self._public_id = QLineEdit()
        self._bpm_url = QLineEdit()
        self._level = QLabel("")
        self._level.setObjectName("warn")
        self._level.setWordWrap(True)
        self._level.hide()
        self._meter = QProgressBar()
        self._meter.setObjectName("meter")
        self._meter.setRange(0, 100)
        self._meter.setTextVisible(False)
        self._meter.setToolTip("心音を拾うと動きます。まったく動かないときはマイクを確かめてください")

        self._cal_btn = QPushButton(CAL_START)
        self._discard_cal = QPushButton(CAL_DISCARD)
        self._discard_cal.setEnabled(False)
        self._reset_cal = QPushButton(CAL_RESET)
        self._reset_cal.setEnabled(False)
        self._tap_btn = QPushButton("拍")
        self._tap_btn.setObjectName("tap")
        self._tap_btn.setEnabled(False)
        # 心音ファイル追加はいったん出さない。
        # load_cal = QPushButton("心音ファイルを追加")
        save_btn = QPushButton("上書き保存")
        save_btn.setToolTip("今の見た目と補正を、選んでいるプロファイルに保存します")
        save_as_btn = QPushButton("名前を付けて保存")
        save_as_btn.setToolTip("別の名前で保存します（配信ごとに見た目を切り替えたいとき）")

        self._cal_btn.clicked.connect(self._on_cal_primary)
        self._discard_cal.clicked.connect(self._discard_current_cal)
        self._reset_cal.clicked.connect(self._reset_saved_cal)
        self._tap_btn.clicked.connect(self._tap_now)
        # load_cal.clicked.connect(self._add_audio_sample)
        self._tap_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._tap_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._tap_shortcut.activated.connect(self._tap_now)
        self._tap_shortcut.setEnabled(False)
        save_btn.clicked.connect(self._save_current)
        save_as_btn.clicked.connect(self._save_as)
        self._profiles.currentIndexChanged.connect(self._load_selected_profile)
        self._style.currentIndexChanged.connect(self._apply_controls)
        self._angle_locked.toggled.connect(self._apply_controls)
        self._reset_angle.clicked.connect(lambda: self._output.canvas.reset_angle())
        self._scale.valueChanged.connect(self._apply_controls)
        self._opacity.valueChanged.connect(self._apply_controls)
        self._text.textChanged.connect(self._apply_controls)
        self._show_beat_text.toggled.connect(self._apply_controls)
        self._beat_scale.valueChanged.connect(self._apply_controls)
        self._beat_opacity.valueChanged.connect(self._apply_controls)
        self._beat_x.valueChanged.connect(self._apply_controls)
        self._beat_y.valueChanged.connect(self._apply_controls)
        self._beat_jitter.valueChanged.connect(self._apply_controls)
        self._beat_tilt.valueChanged.connect(self._apply_controls)
        self._beat_color.currentIndexChanged.connect(self._apply_controls)
        self._beat_outline.currentIndexChanged.connect(self._apply_controls)
        self._show_bpm.toggled.connect(self._apply_controls)
        self._bpm_scale.valueChanged.connect(self._apply_controls)
        self._bpm_x.valueChanged.connect(self._apply_controls)
        self._bpm_y.valueChanged.connect(self._apply_controls)
        self._bpm_color.currentIndexChanged.connect(self._apply_controls)
        self._bpm_outline.currentIndexChanged.connect(self._apply_controls)
        self._backdrop.currentIndexChanged.connect(self._apply_controls)
        # self._show_arrhythmia.toggled.connect(self._apply_controls)
        self._mics.currentIndexChanged.connect(self._on_mic_picked)

        self._reset_beat = QPushButton("設定をリセット")
        self._reset_bpm = QPushButton("設定をリセット")
        self._reset_beat.clicked.connect(self._reset_beat_look)
        self._reset_bpm.clicked.connect(self._reset_bpm_look)

        # 入れ子の枠を重ねると横幅が足りなくなるので、枠は 1 段だけにする。
        profile_wrap = QWidget()
        profile_row = QHBoxLayout(profile_wrap)
        profile_row.setContentsMargins(0, 0, 0, 0)
        profile_row.addWidget(self._profiles, 1)
        profile_row.addWidget(save_btn)
        profile_row.addWidget(save_as_btn)
        input_form = CenteredForm()
        input_form.addRow("プロファイル", profile_wrap)
        input_form.addRow("マイク", self._mics)
        input_form.addRow("音の大きさ", self._meter)
        input_box = QGroupBox("① マイク")
        input_box.setLayout(input_form)

        cal_row = QHBoxLayout()
        cal_row.addWidget(self._cal_btn)
        cal_row.addWidget(self._discard_cal)
        cal_hint = QLabel(
            "・配信前に一度、配信で使うマイクを使用して補正作業を行うのをおすすめします。\n"
            "・補正開始ボタンを押下後、マイクが拾った自分の心音が再生されるので、"
            "その鼓動を聴きながら拍動に合わせて「拍」ボタン（またはスペース）を10回程度押して下さい。\n"
            "・補正を破棄ボタンで補正を中断することができます。"
        )
        cal_hint.setObjectName("meta")
        cal_hint.setWordWrap(True)
        cal_box = QGroupBox("② 心拍の補正（配信前調整）")
        cal_inner = QVBoxLayout()
        cal_inner.addWidget(cal_hint)
        cal_inner.addLayout(cal_row)
        cal_inner.addWidget(self._tap_btn)
        # cal_inner.addWidget(load_cal)
        cal_inner.addLayout(_right(self._reset_cal))
        cal_box.setLayout(cal_inner)

        style_form = CenteredForm()
        style_form.addRow("スタイル", self._style)
        style_form.addRow("大きさ", scale_row)
        style_form.addRow("透明度", opacity_row)
        style_box = QGroupBox("③ スタイル")
        style_box.setLayout(style_form)

        beat_form = CenteredForm()
        beat_form.addRow("文言", self._text)
        beat_form.addRow("大きさ", beat_scale_row)
        beat_form.addRow("透明度", beat_opacity_row)
        beat_form.addRow("左右", beat_x_row)
        beat_form.addRow("上下", beat_y_row)
        beat_form.addRow("ゆらぎ", beat_jitter_row)
        beat_form.addRow("傾き", beat_tilt_row)
        beat_form.addRow("文字色", self._beat_color)
        beat_form.addRow("縁取り", self._beat_outline)
        beat_box, self._beat_details = _toggle_box(
            "④ 同期文字", self._show_beat_text, beat_form, self._reset_beat
        )

        bpm_form = CenteredForm()
        bpm_form.addRow("大きさ", bpm_scale_row)
        bpm_form.addRow("左右", bpm_x_row)
        bpm_form.addRow("上下", bpm_y_row)
        bpm_form.addRow("文字色", self._bpm_color)
        bpm_form.addRow("縁取り", self._bpm_outline)
        bpm_box, self._bpm_details = _toggle_box(
            "⑤ 心拍数", self._show_bpm, bpm_form, self._reset_bpm
        )

        angle_row = QHBoxLayout()
        angle_row.addWidget(self._angle_locked, 1)
        angle_row.addWidget(self._reset_angle)
        self._angle_wrap = QWidget()
        angle_col = QVBoxLayout(self._angle_wrap)
        angle_col.setContentsMargins(0, 0, 0, 0)
        angle_col.addLayout(angle_row)
        angle_col.addWidget(self._angle_hint)
        obs_hint = QLabel(
            f"OBS では「ウィンドウキャプチャ」で「{OUTPUT_WINDOW_TITLE}」を選び、"
            "クロマキーで背景の色を抜きます。"
        )
        obs_hint.setObjectName("meta")
        obs_hint.setWordWrap(True)
        other_form = CenteredForm()
        other_form.addRow("背景", self._backdrop)
        other_inner = QVBoxLayout()
        other_inner.addLayout(other_form)
        other_inner.addWidget(obs_hint)
        other_inner.addWidget(self._angle_wrap)
        other_inner.addWidget(self._gl_note)
        self._other_box = QGroupBox("⑥ 背景と向き")
        self._other_box.setLayout(other_inner)

        oshi = CenteredForm()
        oshi.addRow("心拍ID", self._public_id)
        oshi.addRow("補助 BPM URL", self._bpm_url)
        oshi_inner = QWidget()
        oshi_inner.setLayout(oshi)
        oshi_wrap, _oshi_fold = _make_fold("推しログ(ぬ)連携", oshi_inner, expanded=False)

        self._banner = QFrame()
        self._banner.setObjectName("detectBanner")
        self._banner.setProperty("kind", "preview")
        banner_layout = QVBoxLayout(self._banner)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        banner_layout.setSpacing(4)
        banner_layout.addWidget(self._status)
        banner_layout.addWidget(self._notice)
        banner_layout.addWidget(self._level)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setSpacing(10)
        layout.addWidget(disclaimer)
        layout.addWidget(input_box)
        layout.addWidget(cal_box)
        layout.addWidget(style_box)
        layout.addWidget(beat_box)
        layout.addWidget(bpm_box)
        layout.addWidget(self._other_box)
        layout.addWidget(oshi_wrap)
        layout.addWidget(self._aux)
        layout.addWidget(self._warn)
        layout.addStretch(1)
        layout.addWidget(version)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(root)

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self._banner)
        shell_layout.addWidget(scroll, 1)
        self.setCentralWidget(shell)

        self._fill_mics()
        self._fill_profiles()
        self._load_into_controls(self._session.profile)
        self._restart_mic()

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()
        self._aux_poller = AuxBpmPoller()
        self._aux_timer = QTimer(self)
        self._aux_timer.setInterval(5000)
        self._aux_timer.timeout.connect(self._poll_aux)
        self._aux_timer.start()
        self._poll_aux()

    def _fill_mics(self) -> None:
        self._mics.blockSignals(True)
        self._mics.clear()
        for mic in list_mics():
            self._mics.addItem(mic.name, mic.id)
        self._mics.blockSignals(False)

    def _on_mics_changed(self) -> None:
        """保存したマイクが戻ればそれに、抜けたら既定のマイクに切り替える。"""
        self._fill_mics()
        self._mics.blockSignals(True)
        self._select_mic(self._session.profile.mic_id)
        self._mics.blockSignals(False)
        self._restart_mic()

    def _profile_path(self, name: str) -> Path:
        safe = name.strip() or "default"
        return profiles_dir(self._data_dir) / f"{safe}.json"

    def _fill_profiles(self) -> None:
        self._profiles.blockSignals(True)
        self._profiles.clear()
        names = [p.stem for p in sorted(profiles_dir(self._data_dir).glob("*.json"))]
        last = load_last_profile_name(self._data_dir)
        if last not in names:
            names.insert(0, last)
        for name in names:
            self._profiles.addItem(name)
        self._profiles.setCurrentText(last)
        self._profiles.blockSignals(False)
        path = self._profile_path(last)
        # 起動時は app.py が同じプロファイルを読み込み済み。二度読みしない
        if path.is_file() and self._session.profile.name != last:
            self._session.profile = load_profile(path)
            self._session.rebuild_detector()

    def _load_selected_profile(self, _index: int = 0) -> None:
        name = self._profiles.currentText().strip()
        if not name:
            return
        path = self._profile_path(name)
        if not path.is_file():
            return
        # 閉じるときと同じく、切り替える前に今のプロファイルを保存する。
        # 補正の途中なら、その録音は切り替え先へ持ち込まない
        previous = self._session.profile
        if previous.name != name:
            self._write_profile(previous)
        self._session.discard_calibration()
        self._sync_cal_ui()
        self._session.profile = load_profile(path)
        self._session.rebuild_detector()
        self._load_into_controls(self._session.profile)
        self._restart_mic()

    def _rebuild_output(self) -> None:
        """配信用の窓を同じ場所に作り直す（背景を透明にしたとき）。"""
        old = self._output
        new = OutputWindow(self._session)
        new.set_quit_handler(self.close)
        new.canvas.angle_locked = old.canvas.angle_locked
        new.setGeometry(old.geometry())
        if old.isVisible():
            new.show()
        self._output = new
        old.allow_close()
        old.close()
        old.deleteLater()
        self._flash(
            "透明にするため配信用の窓を開き直しました。OBS の取り込みが外れたら選び直してください"
        )

    def _refresh_style_controls(self) -> None:
        style, _look = self._style_choice()
        rotatable = style in ROTATABLE_STYLES
        self._angle_wrap.setVisible(rotatable)
        failed = style in GL_STYLES and self._output.canvas.gl_error is not None
        self._gl_note.setText(GL_FAIL_LABEL if failed else "")
        self._gl_note.setVisible(failed)

    def _set_banner_kind(self, kind: str) -> None:
        if self._banner.property("kind") != kind:
            self._banner.setProperty("kind", kind)
            style = self._banner.style()
            style.unpolish(self._banner)
            style.polish(self._banner)
            self._banner.update()
        if self._status.objectName() != kind:
            self._status.setObjectName(kind)
            style = self._status.style()
            style.unpolish(self._status)
            style.polish(self._status)

    def _set_detect_status(self) -> None:
        clock = self._session.clock
        if clock.detected:
            kind = "live"
            text = f"{LIVE_STATUS}  {clock.bpm} BPM"
        elif clock.has_beats:
            kind = "preview"
            text = f"{PREVIEW_LOST_STATUS}  最後 {clock.bpm} BPM"
        else:
            kind = "preview"
            text = PREVIEW_IDLE_STATUS
        self._set_banner_kind(kind)
        self._status.setText(text)

    def _restart_mic(self) -> None:
        self._apply_controls()
        mic_id = str(self._mics.currentData() or "")
        self._last_audio = self._now()
        self._no_audio = False
        try:
            self._mic.start(mic_id)
        except Exception:
            self._mic_open = False
            self._meter.setValue(0)
            self._level.setText(
                "マイクを開けません。OBS と同時に使うときは、独占モードをオフにしてください"
            )
            self._level.show()
            return
        self._mic_open = True
        self._level.hide()

    def _watch_audio(self, got_samples: bool, now: float) -> None:
        if got_samples:
            self._last_audio = now
            if self._no_audio:
                self._no_audio = False
                self._level.hide()
            return
        if self._mic_open and not self._no_audio and now - self._last_audio > NO_AUDIO_S:
            self._no_audio = True
            self._meter.setValue(0)
            self._level.setText(NO_AUDIO_LABEL)
            self._level.show()

    def _now(self) -> float:
        return time.perf_counter() - self._t0

    def _flash(self, text: str) -> None:
        self._notice.setText(text)
        self._notice.show()
        self._notice_timer.start(NOTICE_MS)

    def _clear_notice(self) -> None:
        self._notice.setText("")
        self._notice.hide()

    def _sync_cal_ui(self) -> None:
        on = self._session.recording
        saved = bool(self._session.profile.calibration)
        self._cal_btn.setText(CAL_SAVE if on else CAL_START)
        self._discard_cal.setEnabled(on)
        self._tap_btn.setEnabled(on)
        self._tap_shortcut.setEnabled(on)
        self._reset_cal.setEnabled(saved and not on)
        self._tap_btn.setText("拍")
        if on:
            self._monitor.start()
            self._tap_btn.setFocus()
            self._warn.setText("ヘッドホン推奨。補正中の音は操作画面だけに聞こえます。")
            return
        self._monitor.stop()
        if self._warn.text().startswith("ヘッドホン"):
            self._warn.setText("")

    def _on_cal_primary(self) -> None:
        if self._session.recording:
            self._commit_cal()
        else:
            self._begin_cal()

    def _begin_cal(self) -> None:
        self._session.begin_calibration(self._session.now)
        self._sync_cal_ui()

    def _discard_current_cal(self) -> None:
        self._session.discard_calibration()
        self._sync_cal_ui()
        self._flash("補正を破棄しました")

    def _tap_now(self) -> None:
        if self._session.tap(self._session.now):
            self._tap_btn.setText(f"拍  {len(self._session.taps)}")

    def _commit_cal(self) -> None:
        saved = self._session.commit_calibration()
        self._sync_cal_ui()
        if not saved:
            self._flash("音が録れていなかったので保存しませんでした。マイクを確かめてください")
            return
        self._save_current(notice="補正を保存しました")

    def _confirm_reset(self) -> bool:
        answer = QMessageBox.question(
            self,
            "設定を初期化",
            "保存した心拍の補正を全部消して、最初からやり直しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _reset_saved_cal(self) -> None:
        if not self._confirm_reset():
            return
        self._session.reset_calibration()
        self._sync_cal_ui()
        self._save_current(notice="補正の設定を初期化しました")

    def _add_audio_sample(self) -> None:
        path, _ok = QFileDialog.getOpenFileName(self, "心音ファイルを追加", "", AUDIO_FILTER)
        if not path:
            return
        try:
            samples = load_audio_mono(Path(path))
        except (OSError, ValueError, RuntimeError):
            self._flash("この音声ファイルは読めませんでした")
            return
        if not samples:
            self._flash("音声ファイルが空でした")
            return
        self._session.profile.calibration.append(samples)
        self._session.rebuild_detector()
        self._sync_cal_ui()
        self._save_current(notice="心音サンプルを追加しました")

    def _write_profile(self, profile: HeartProfile) -> bool:
        try:
            save_profile(self._profile_path(profile.name), profile)
            save_last_profile_name(profile.name, self._data_dir)
        except OSError:
            self._flash(SAVE_FAIL_LABEL)
            return False
        return True

    def _save_current(self, *, notice: str | None = "プロファイルを保存しました") -> bool:
        self._apply_controls()
        name = self._session.profile.name
        if not self._write_profile(self._session.profile):
            return False
        if self._profiles.findText(name) < 0:
            self._profiles.blockSignals(True)
            self._profiles.addItem(name)
            self._profiles.setCurrentText(name)
            self._profiles.blockSignals(False)
        if notice:
            self._flash(notice)
        return True

    def _save_as(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "名前を付けて保存",
            "プロファイル名",
            QLineEdit.EchoMode.Normal,
            self._profiles.currentText(),
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        # 保存は一覧で選んでいる名前を使うので、先に新しい名前を一覧に足して選ぶ
        self._profiles.blockSignals(True)
        if self._profiles.findText(name) < 0:
            self._profiles.addItem(name)
        self._profiles.setCurrentText(name)
        self._profiles.blockSignals(False)
        self._save_current(notice=f"「{name}」として保存しました")

    def _poll_aux(self) -> None:
        profile = self._session.profile
        profile.oshilog_public_id = self._public_id.text().strip()
        profile.oshilog_bpm_url = self._bpm_url.text().strip()
        bpm = self._aux_poller.poll(profile.oshilog_bpm_url)
        self._session.clock.oshilog_bpm = bpm
        if bpm is None:
            self._aux.setText("推しログ(ぬ) 補助: —")
        else:
            self._aux.setText(f"推しログ(ぬ) 補助: {bpm}（遅延のことがあります）")

    def _on_tick(self) -> None:
        samples = self._mic.pull_mono()
        now = self._now()
        if samples:
            peak = max(abs(x) for x in samples)
            # 心音は小さいので、平方根で小さい音も見えるようにする。
            self._meter.setValue(min(100, int(peak**0.5 * 100)))
        self._watch_audio(bool(samples), now)
        recording = self._session.recording
        if recording and samples:
            self._monitor.write_mono(samples)
        self._session.tick(now, samples)
        if recording:
            self._set_banner_kind("record")
            self._status.setText(f"補正中  {self._session.tap_label()}")
        else:
            self._set_detect_status()
        if not recording:
            if self._session.clock.bpm_mismatch():
                self._warn.setText("時計と数字がズレています（推しログは遅延します）")
            elif self._warn.text().startswith("時計と数字"):
                self._warn.setText("")
        if self._output.canvas.gl_error is not None and not self._gl_note.isVisible():
            self._refresh_style_controls()
        self._output.canvas.set_now(self._display_clock.at(now, self._session.now))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            super().closeEvent(event)
            return
        self._closing = True
        self._timer.stop()
        self._aux_timer.stop()
        self._save_current(notice=None)
        # 保存に失敗しても、マイクや配信用の窓を残したまま終われなくならないようにする
        try:
            save_app_state(
                self._data_dir,
                operator_geom=window_geom(self),
                output_geom=window_geom(self._output),
            )
        except OSError:
            pass
        self._monitor.stop()
        self._mic.stop()
        self._output.allow_close()
        self._output.close()
        super().closeEvent(event)
