"""手元確認用の操作画面。配信出力とは別窓。"""

from __future__ import annotations

import time
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QCheckBox,
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
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE, display_version
from stream_heartbeat.audio import MicMonitor, MicTap
from stream_heartbeat.clock import DisplayClock
from stream_heartbeat.config import (
    DISCLAIMER,
    LIVE_STATUS,
    PREVIEW_IDLE_STATUS,
    PREVIEW_LOST_STATUS,
)
from stream_heartbeat.i18n import (
    SKIP_PROP,
    other_language_label,
    tr,
    translate_tree,
)
from stream_heartbeat.oshilog import AuxBpmPoller
from stream_heartbeat.paths import resolve_data_dir
from stream_heartbeat.profile import (
    HeartProfile,
    clean_profile_name,
    load_last_profile_name,
    load_profile,
    profiles_dir,
    save_app_state,
    save_last_profile_name,
    save_profile,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon
from stream_heartbeat.ui.combo import MarkedComboBox
from stream_heartbeat.ui.effects import FRONT_EFFECTS, active_effect
from stream_heartbeat.ui.fold import make_fold
from stream_heartbeat.ui.forms import CenteredForm
from stream_heartbeat.ui.heart_paint import (
    BACKDROPS,
    BPM_COLORS,
    BPM_OUTLINES,
    GL_STYLES,
    ROTATABLE_STYLES,
)
from stream_heartbeat.ui.input_panel import InputPanel
from stream_heartbeat.ui.operator_calibration import (
    CAL_DISCARD,
    CAL_RESET,
    CAL_START,
    CalibrationMixin,
)
from stream_heartbeat.ui.operator_controls import ProfileControlsMixin
from stream_heartbeat.ui.operator_input import InputMixin
from stream_heartbeat.ui.operator_language import LanguageMixin, obs_hint
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.placement import window_geom
from stream_heartbeat.ui.slider import labeled_slider
from stream_heartbeat.ui.style_catalog import (
    MODEL_MATERIALS,
    STYLES,
    XRAY_MATERIALS,
    has_material,
    has_xray_material,
)
from stream_heartbeat.ui.styles import DARK_QSS
from stream_heartbeat.ui.update_notice import UpdateNotice
from stream_heartbeat.ui.vts_panel import VtsPanel

GL_FAIL_LABEL = "立体表示を使えないため 2D で描いています"
NOTICE_MS = 3500
# 設定を変えたら、この間隔で見回ってプロファイルへ自動で書く（保存ボタンを押さなくてよい）
AUTOSAVE_MS = 2000
SAVE_FAIL_LABEL = "保存できませんでした（ファイルが使用中か、空き容量が足りません）"
CLOCK_WARN = "時計と数字がズレています（推しログは遅延します）"
CAL_FOLD_TITLE = "心拍の補正（数字が合わないときだけ）"
# 拍の文字・心拍数は配信用の窓でつまんで動かせる（label_drag）
DRAG_HINT = "配信用の窓で、出ている文字をドラッグして動かすこともできます"


def _right(widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(widget)
    return row


def _toggle_box(
    title: str, check: QCheckBox, form: QFormLayout, reset: QPushButton, hint: str = ""
) -> tuple[QGroupBox, QWidget]:
    """チェックを外している間は細かい設定を畳む。hint は設定の上に出す一言。"""
    details = QWidget()
    inner = QVBoxLayout(details)
    inner.setContentsMargins(0, 0, 0, 0)
    if hint:
        note = QLabel(hint)
        note.setObjectName("meta")
        note.setWordWrap(True)
        inner.addWidget(note)
    inner.addLayout(form)
    inner.addLayout(_right(reset))
    col = QVBoxLayout()
    col.addWidget(check)
    col.addWidget(details)
    box = QGroupBox(title)
    box.setLayout(col)
    return box, details


class OperatorWindow(
    CalibrationMixin, InputMixin, LanguageMixin, ProfileControlsMixin, QMainWindow
):
    def __init__(self, session: HeartSession, output: OutputWindow) -> None:
        super().__init__()
        self._session = session
        self._output = output
        self._mic = MicTap()
        self._monitor = MicMonitor()
        self._data_dir = resolve_data_dir()
        self._t0 = time.perf_counter()
        self._display_clock = DisplayClock()
        self._clock_warn = False
        self._closing = False
        self._saved_snapshot: tuple = ()
        self._last_audio = 0.0
        self._no_audio = False
        self._mic_open = False
        # マイクの代わりの入力（ファイル・心拍計）
        self._input = InputPanel(self._data_dir, self._flash, self._now)
        self._input.mode_changed.connect(self._on_input_mode)
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
        # 推しログ(ぬ)の補助の値は、届いているときだけ出す
        self._aux = QLabel("")
        self._aux.setObjectName("meta")
        self._aux.setWordWrap(True)
        self._aux.hide()
        self._warn = QLabel("")
        self._warn.setObjectName("warn")
        self._warn.setWordWrap(True)
        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setObjectName("disclaimer")
        disclaimer.setWordWrap(True)
        version = QLabel(display_version())
        version.setObjectName("meta")

        # プロファイル名とマイク名は利用者のデータなので、言語を変えても付け替えない
        self._profiles = MarkedComboBox()
        self._profiles.setEditable(False)
        self._profiles.setProperty(SKIP_PROP, True)
        self._mics = MarkedComboBox()
        self._mics.setProperty(SKIP_PROP, True)
        # スタイル・材質・演出はよく切り替えるので、この 3 つだけホイールでも変えられる
        self._style = MarkedComboBox(wheel=True)
        for key, look, label in STYLES:
            self._style.addItem(label, (key, look))
        # リアル1 の材質。演出（聴診器など）と一緒に使えるよう、演出とは別に選ぶ
        self._material = MarkedComboBox(wheel=True)
        for key, label in MODEL_MATERIALS:
            self._material.addItem(label, key)
        # レントゲン4 の心臓の材質（X 線が入る。リアル1 とは別に覚える）
        self._xray_material = MarkedComboBox(wheel=True)
        for key, label in XRAY_MATERIALS:
            self._xray_material.addItem(label, key)
        # 演出（心臓わしづかみ・聴診器）。選べるものはスタイルで変わる
        self._effect = MarkedComboBox(wheel=True)
        self._effect_hint = QLabel("")
        self._effect_hint.setObjectName("meta")
        self._effect_hint.setWordWrap(True)
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
        self._show_beat_text = QCheckBox("鼓動に合わせて文字を出す")
        self._beat_scale, beat_scale_row = labeled_slider(50, 200, "小", "大")
        self._beat_opacity, beat_opacity_row = labeled_slider(10, 100, "透明", "不透明")
        self._beat_x, beat_x_row = labeled_slider(0, 100, "左", "右")
        self._beat_y, beat_y_row = labeled_slider(0, 100, "上", "下")
        self._beat_jitter, beat_jitter_row = labeled_slider(0, 40, "なし", "大")
        self._beat_tilt, beat_tilt_row = labeled_slider(0, 100, "なし", "強")
        self._beat_color = MarkedComboBox()
        self._beat_outline = MarkedComboBox()
        self._show_bpm = QCheckBox("心拍数（BPM）を出す")
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
        # 変更は自動で保存するので、上書き保存のボタンは置かない
        self._profiles.setToolTip("設定は変えるたびに自動で保存されます")
        save_as_btn = QPushButton("名前を付けて保存")
        save_as_btn.setToolTip("今の設定を別の名前で残します（配信ごとに見た目を切り替えたいとき）")

        self._cal_btn.clicked.connect(self._on_cal_primary)
        self._discard_cal.clicked.connect(self._discard_current_cal)
        self._reset_cal.clicked.connect(self._reset_saved_cal)
        self._tap_btn.clicked.connect(self._tap_now)
        # load_cal.clicked.connect(self._add_audio_sample)
        self._tap_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._tap_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._tap_shortcut.activated.connect(self._tap_now)
        self._tap_shortcut.setEnabled(False)
        save_as_btn.clicked.connect(self._save_as)
        self._profiles.currentIndexChanged.connect(self._load_selected_profile)
        self._style.currentIndexChanged.connect(self._apply_controls)
        self._effect.currentIndexChanged.connect(self._on_effect_picked)
        self._material.currentIndexChanged.connect(self._apply_controls)
        self._xray_material.currentIndexChanged.connect(self._apply_controls)
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
        # プロファイルは見た目・補正のまとまりなので、どの欄にも入れず一番上に置く
        profile_wrap = QWidget()
        profile_row = QHBoxLayout(profile_wrap)
        profile_row.setContentsMargins(0, 0, 0, 0)
        profile_row.addWidget(self._profiles, 1)
        profile_row.addWidget(save_as_btn)
        profile_form = CenteredForm()
        profile_form.addRow("プロファイル", profile_wrap)
        input_form = CenteredForm()
        input_form.addRow("入力", self._input.mode_combo)
        input_form.addRow("マイク", self._mics)
        input_form.addRow("音の大きさ", self._meter)
        self._input_form = input_form
        input_col = QVBoxLayout()
        input_col.addLayout(input_form)
        input_col.addWidget(self._input)
        input_box = QGroupBox("① 入力")
        input_box.setLayout(input_col)

        cal_row = QHBoxLayout()
        cal_row.addWidget(self._cal_btn, 1)
        cal_row.addWidget(self._discard_cal)
        self._cal_hint = QLabel(self._cal_hint_text())
        self._cal_hint.setObjectName("guide")
        self._cal_hint.setWordWrap(True)
        cal_inner_widget = QWidget()
        cal_inner = QVBoxLayout(cal_inner_widget)
        cal_inner.setContentsMargins(0, 0, 0, 0)
        cal_inner.addWidget(self._cal_hint)
        cal_inner.addLayout(cal_row)
        cal_inner.addWidget(self._tap_btn)
        # cal_inner.addWidget(load_cal)
        cal_inner.addLayout(_right(self._reset_cal))
        # 言語ボタンは「心拍の補正」の見出しの右に置く
        self._lang_btn = QPushButton(other_language_label())
        self._lang_btn.setObjectName("langBtn")
        self._lang_btn.clicked.connect(self._toggle_language)
        cal_wrap, _cal_fold = make_fold(CAL_FOLD_TITLE, cal_inner_widget, side=self._lang_btn)

        angle_row = QHBoxLayout()
        angle_row.addWidget(self._angle_locked, 1)
        angle_row.addWidget(self._reset_angle)
        self._angle_wrap = QWidget()
        angle_col = QVBoxLayout(self._angle_wrap)
        angle_col.setContentsMargins(0, 0, 0, 0)
        angle_col.addLayout(angle_row)
        angle_col.addWidget(self._angle_hint)
        self._obs_hint = QLabel(obs_hint(self._session.profile.backdrop))
        self._obs_hint.setObjectName("meta")
        self._obs_hint.setWordWrap(True)
        # 背景と向き（回せるスタイルだけ）も見た目の一部なので、スタイルの欄にまとめる
        style_form = CenteredForm()
        style_form.addRow("スタイル", self._style)
        style_form.addRow("材質", self._material)
        style_form.addRow("材質", self._xray_material)
        style_form.addRow("演出", self._effect)
        self._style_form = style_form
        style_form.addRow("大きさ", scale_row)
        style_form.addRow("透明度", opacity_row)
        style_form.addRow("背景", self._backdrop)
        style_inner = QVBoxLayout()
        style_inner.addLayout(style_form)
        style_inner.addWidget(self._effect_hint)
        style_inner.addWidget(self._gl_note)
        style_inner.addWidget(self._angle_wrap)
        style_inner.addWidget(self._obs_hint)
        style_box = QGroupBox("② スタイル")
        style_box.setLayout(style_inner)

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
            "③ 同期文字", self._show_beat_text, beat_form, self._reset_beat, DRAG_HINT
        )

        bpm_form = CenteredForm()
        bpm_form.addRow("大きさ", bpm_scale_row)
        bpm_form.addRow("左右", bpm_x_row)
        bpm_form.addRow("上下", bpm_y_row)
        bpm_form.addRow("文字色", self._bpm_color)
        bpm_form.addRow("縁取り", self._bpm_outline)
        bpm_box, self._bpm_details = _toggle_box(
            "④ 心拍数", self._show_bpm, bpm_form, self._reset_bpm, DRAG_HINT
        )

        oshi = CenteredForm()
        oshi.addRow("心拍ID", self._public_id)
        oshi.addRow("補助 BPM URL", self._bpm_url)
        oshi_inner = QWidget()
        oshi_inner.setLayout(oshi)
        oshi_wrap, _oshi_fold = make_fold("推しログ(ぬ)連携（未実装）", oshi_inner, expanded=False)
        # 未実装のうちは画面に出さない（保存した値はそのまま使う）
        oshi_wrap.hide()
        # 配信用の窓は作り直すことがあるので、そのときの窓に聞く
        self._vts = VtsPanel(
            self._session, self._data_dir, self._flash, lambda: self._output.canvas.stetho_offset()
        )
        vts_layout = QVBoxLayout()
        vts_layout.addWidget(self._vts)
        vts_box = QGroupBox("⑤ VTube Studio 連携")
        vts_box.setLayout(vts_layout)

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
        layout.addLayout(profile_form)
        layout.addWidget(input_box)
        layout.addWidget(style_box)
        layout.addWidget(beat_box)
        layout.addWidget(bpm_box)
        layout.addWidget(vts_box)
        layout.addWidget(cal_wrap)
        layout.addWidget(oshi_wrap)
        layout.addWidget(self._aux)
        layout.addWidget(self._warn)
        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.addWidget(disclaimer, 1)
        footer.addWidget(version, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(footer)
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
        # 新しい版のお知らせはスクロールしなくても見える所に出す
        self._update_notice = UpdateNotice()
        shell_layout.addWidget(self._update_notice)
        shell_layout.addWidget(scroll, 1)
        self.setCentralWidget(shell)

        self._fill_mics()
        self._fill_profiles()
        self._load_into_controls(self._session.profile)
        self._show_input_rows()
        self._restart_mic()
        # 部品は日本語の原文で作ったので、英語で始めるときはここで付け替える
        translate_tree(self)

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
        # 配信用の窓で回した向きや聴診器を置いた所も、操作画面の変更と同じく自動で保存する
        self._saved_snapshot = self._profile_snapshot()
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_MS)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

    def _profile_snapshot(self) -> tuple:
        """補正の音を除いた設定の値。変わったかを見るだけなので、長い音の並びは比べない。"""
        profile = self._session.profile
        return tuple(
            getattr(profile, item.name) for item in fields(profile) if item.name != "calibration"
        )

    def _autosave(self) -> None:
        snapshot = self._profile_snapshot()
        if self._closing or snapshot == self._saved_snapshot:
            return
        # 保存に失敗しても知らせを出し続けないよう、試した値を覚えておく（次に変えたらまた試す）
        self._saved_snapshot = snapshot
        self._save_current(notice=None)

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
        self._saved_snapshot = self._profile_snapshot()

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
        style, look = self._style_choice()
        self._style_form.setRowVisible(self._material, has_material(style, look))
        self._style_form.setRowVisible(self._xray_material, has_xray_material(style, look))
        # 手で掴んでいる間・パドルではさんでいる間は正面に固定するので、向きの操作は出さない
        front = active_effect(style, self._session.profile.effect) in FRONT_EFFECTS
        self._angle_wrap.setVisible(style in ROTATABLE_STYLES and not front)
        failed = style in GL_STYLES and self._output.canvas.gl_error is not None
        self._gl_note.setText(tr(GL_FAIL_LABEL) if failed else "")
        self._gl_note.setVisible(failed)
        self._obs_hint.setText(obs_hint(self._session.profile.backdrop))
        self._sync_effect_choices()

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

    def _refresh_status(self) -> None:
        """上の帯の文。補正中は拍の数、そうでなければ心音を読めているか。"""
        if self._session.recording:
            self._set_banner_kind("record")
            self._status.setText(tr("補正中  {label}", label=self._session.tap_label()))
        else:
            self._set_detect_status()

    def _set_detect_status(self) -> None:
        clock = self._session.clock
        if clock.detected:
            kind = "live"
            text = self._input_live_text(clock.bpm) or f"{tr(LIVE_STATUS)}  {clock.bpm} BPM"
        elif clock.has_beats:
            kind = "preview"
            text = tr("{status}  最後 {bpm} BPM", status=tr(PREVIEW_LOST_STATUS), bpm=clock.bpm)
        else:
            kind = "preview"
            text = tr(PREVIEW_IDLE_STATUS)
        self._set_banner_kind(kind)
        self._status.setText(text)

    def _now(self) -> float:
        return time.perf_counter() - self._t0

    def _flash(self, text: str) -> None:
        """知らせを出す。原文でも訳したあとの文でも渡せる（訳した文は tr で変わらない）。"""
        self._notice.setText(tr(text))
        self._notice.show()
        self._notice_timer.start(NOTICE_MS)

    def _clear_notice(self) -> None:
        self._notice.setText("")
        self._notice.hide()

    def _write_profile(self, profile: HeartProfile) -> bool:
        try:
            save_profile(self._profile_path(profile.name), profile)
            save_last_profile_name(profile.name, self._data_dir)
        except OSError:
            self._flash(SAVE_FAIL_LABEL)
            return False
        if profile is self._session.profile:
            self._saved_snapshot = self._profile_snapshot()
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
            tr("名前を付けて保存"),
            tr("プロファイル名"),
            QLineEdit.EchoMode.Normal,
            self._profiles.currentText(),
        )
        if not ok:
            return
        name = clean_profile_name(name)
        if not name:
            return
        exists = self._profile_path(name).is_file()
        if exists and name != self._session.profile.name and not self._confirm_overwrite(name):
            return
        # 保存は一覧で選んでいる名前を使うので、先に新しい名前を一覧に足して選ぶ
        self._profiles.blockSignals(True)
        if self._profiles.findText(name) < 0:
            self._profiles.addItem(name)
        self._profiles.setCurrentText(name)
        self._profiles.blockSignals(False)
        self._save_current(notice=tr("「{name}」として保存しました", name=name))

    def _confirm_overwrite(self, name: str) -> bool:
        answer = QMessageBox.question(
            self,
            tr("名前を付けて保存"),
            tr("「{name}」はもうあります。今の設定で置き換えますか？", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _poll_aux(self) -> None:
        profile = self._session.profile
        profile.oshilog_public_id = self._public_id.text().strip()
        profile.oshilog_bpm_url = self._bpm_url.text().strip()
        bpm = self._aux_poller.poll(profile.oshilog_bpm_url)
        self._session.clock.oshilog_bpm = bpm
        self._show_aux(bpm)

    def _show_aux(self, bpm: int | None) -> None:
        self._aux.setVisible(bpm is not None)
        if bpm is not None:
            self._aux.setText(tr("推しログ(ぬ) 補助: {bpm}（遅延のことがあります）", bpm=bpm))

    def _on_tick(self) -> None:
        now = self._now()
        samples, beats = self._pull_input(now)
        if samples:
            peak = max(abs(x) for x in samples)
            # 心音は小さいので、平方根で小さい音も見えるようにする。
            self._meter.setValue(min(100, int(peak**0.5 * 100)))
        self._watch_audio(bool(samples), now)
        recording = self._session.recording
        if recording and samples:
            self._monitor.write_mono(samples)
        self._session.tick(now, samples, beats=beats)
        self._refresh_status()
        if not recording:
            mismatch = self._session.clock.bpm_mismatch()
            if mismatch:
                self._warn.setText(tr(CLOCK_WARN))
            elif self._clock_warn:
                self._warn.setText("")
            self._clock_warn = mismatch
        if self._output.canvas.gl_error is not None and not self._gl_note.isVisible():
            self._refresh_style_controls()
        shown = self._display_clock.at(now, self._session.now)
        self._output.canvas.set_now(shown)
        self._sync_label_sliders()
        self._vts.tick(shown)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            super().closeEvent(event)
            return
        self._closing = True
        self._timer.stop()
        self._aux_timer.stop()
        self._autosave_timer.stop()
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
        self._input.shutdown()
        self._vts.shutdown()
        self._output.allow_close()
        self._output.close()
        super().closeEvent(event)
