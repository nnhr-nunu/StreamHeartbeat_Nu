"""手元確認用の操作画面。配信出力とは別窓。"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut, QShowEvent
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
    QPushButton,
    QScrollArea,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE, display_version
from stream_heartbeat.audio import MicMonitor, MicTap, list_mics
from stream_heartbeat.config import (
    DISCLAIMER,
    LIVE_STATUS,
    PREVIEW_IDLE_STATUS,
    PREVIEW_LOST_STATUS,
)
from stream_heartbeat.oshilog import fetch_aux_bpm
from stream_heartbeat.paths import resolve_data_dir
from stream_heartbeat.profile import (
    HeartProfile,
    load_last_profile_name,
    load_profile,
    profiles_dir,
    save_last_profile_name,
    save_profile,
)
from stream_heartbeat.render.heart_shaders import REALISTIC_LOOKS
from stream_heartbeat.samples import AUDIO_FILTER, load_audio_mono
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon
from stream_heartbeat.ui.capture_exclude import exclude_from_capture
from stream_heartbeat.ui.combo import MarkedComboBox
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.styles import DARK_QSS

STYLES = [
    ("realistic", "リアル"),
    ("echo", "心エコー"),
    ("mri", "MRI"),
    ("xray", "レントゲン"),
    ("cute", "かわいい"),
    ("mech", "機械"),
    ("ecg", "心電図"),
]
ROTATABLE_STYLES = frozenset({"realistic", "mech", "xray", "mri"})
GL_FAIL_LABEL = "立体表示を使えないため 2D で描いています"
CAL_START = "補正開始"
CAL_SAVE = "補正を保存"
CAL_DISCARD = "補正を破棄"
CAL_RESET = "設定を初期化"
NOTICE_MS = 3500


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


class OperatorWindow(QMainWindow):
    def __init__(self, session: HeartSession, output: OutputWindow) -> None:
        super().__init__()
        self._session = session
        self._output = output
        self._mic = MicTap()
        self._monitor = MicMonitor()
        self._data_dir = resolve_data_dir()
        self._t0 = time.perf_counter()
        self.setWindowTitle(OPERATOR_WINDOW_TITLE)
        self.setMinimumSize(440, 420)
        self.resize(500, 760)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
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
        for key, label in STYLES:
            self._style.addItem(label, key)
        self._look = MarkedComboBox()
        for look in REALISTIC_LOOKS:
            self._look.addItem(look.label, look.key)
        self._angle_locked = QCheckBox("角度を固定（配信用の窓をドラッグしても回さない）")
        self._reset_angle = QPushButton("角度をリセット")
        self._angle_hint = QLabel("配信用の窓を左ドラッグで回転、ダブルクリックで元の向き。")
        self._angle_hint.setObjectName("meta")
        self._angle_hint.setWordWrap(True)
        self._gl_note = QLabel("")
        self._gl_note.setObjectName("warn")
        self._gl_note.setWordWrap(True)
        self._scale = QSlider(Qt.Orientation.Horizontal)
        self._scale.setRange(20, 120)
        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(10, 100)
        self._text = QLineEdit()
        self._show_beat_text = QCheckBox("同期文字を配信用に出す")
        self._beat_scale = QSlider(Qt.Orientation.Horizontal)
        self._beat_scale.setRange(50, 200)
        self._beat_opacity = QSlider(Qt.Orientation.Horizontal)
        self._beat_opacity.setRange(10, 100)
        self._show_bpm = QCheckBox("心拍数を配信用に出す")
        self._show_arrhythmia = QCheckBox("不整脈！を配信用に出す")
        self._public_id = QLineEdit()
        self._bpm_url = QLineEdit()
        self._level = QLabel("入力: —")

        self._cal_btn = QPushButton(CAL_START)
        self._discard_cal = QPushButton(CAL_DISCARD)
        self._discard_cal.setEnabled(False)
        self._reset_cal = QPushButton(CAL_RESET)
        self._reset_cal.setEnabled(False)
        self._tap_btn = QPushButton("拍")
        self._tap_btn.setObjectName("tap")
        self._tap_btn.setEnabled(False)
        load_cal = QPushButton("心音ファイルを追加")
        save_btn = QPushButton("上書き保存")
        save_as_btn = QPushButton("名前を付けて保存")

        self._cal_btn.clicked.connect(self._on_cal_primary)
        self._discard_cal.clicked.connect(self._discard_current_cal)
        self._reset_cal.clicked.connect(self._reset_saved_cal)
        self._tap_btn.clicked.connect(self._tap_now)
        load_cal.clicked.connect(self._add_audio_sample)
        self._tap_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._tap_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._tap_shortcut.activated.connect(self._tap_now)
        self._tap_shortcut.setEnabled(False)
        save_btn.clicked.connect(self._save_current)
        save_as_btn.clicked.connect(self._save_as)
        self._profiles.currentIndexChanged.connect(self._load_selected_profile)
        self._style.currentIndexChanged.connect(self._apply_controls)
        self._look.currentIndexChanged.connect(self._apply_controls)
        self._angle_locked.toggled.connect(self._apply_controls)
        self._reset_angle.clicked.connect(self._output.canvas.reset_angle)
        self._scale.valueChanged.connect(self._apply_controls)
        self._opacity.valueChanged.connect(self._apply_controls)
        self._text.textChanged.connect(self._apply_controls)
        self._show_beat_text.toggled.connect(self._apply_controls)
        self._beat_scale.valueChanged.connect(self._apply_controls)
        self._beat_opacity.valueChanged.connect(self._apply_controls)
        self._show_bpm.toggled.connect(self._apply_controls)
        self._show_arrhythmia.toggled.connect(self._apply_controls)
        self._mics.currentIndexChanged.connect(self._restart_mic)

        look = QFormLayout()
        look.addRow("スタイル", self._style)
        self._look_label = QLabel("質感")
        look.addRow(self._look_label, self._look)
        look.addRow("大きさ", self._scale)
        look.addRow("透明度", self._opacity)
        beat_inner = QWidget()
        beat_form = QFormLayout(beat_inner)
        beat_form.setContentsMargins(8, 0, 0, 0)
        beat_form.addRow(self._show_beat_text)
        beat_form.addRow("文言", self._text)
        beat_form.addRow("大きさ", self._beat_scale)
        beat_form.addRow("透明度", self._beat_opacity)
        beat_wrap, _beat_fold = _make_fold("同期文字", beat_inner, expanded=True)
        look.addRow(beat_wrap)
        look.addRow(self._show_bpm)
        look.addRow(self._show_arrhythmia)
        angle_row = QHBoxLayout()
        angle_row.addWidget(self._angle_locked, 1)
        angle_row.addWidget(self._reset_angle)
        self._angle_wrap = QWidget()
        angle_col = QVBoxLayout(self._angle_wrap)
        angle_col.setContentsMargins(0, 0, 0, 0)
        angle_col.addLayout(angle_row)
        angle_col.addWidget(self._angle_hint)
        look.addRow(self._angle_wrap)
        look.addRow(self._gl_note)
        look_box = QGroupBox("配信用の見た目")
        look_box.setLayout(look)

        profile_wrap = QWidget()
        profile_row = QHBoxLayout(profile_wrap)
        profile_row.setContentsMargins(0, 0, 0, 0)
        profile_row.addWidget(self._profiles, 1)
        profile_row.addWidget(save_btn)
        profile_row.addWidget(save_as_btn)
        input_form = QFormLayout()
        input_form.addRow("プロファイル", profile_wrap)
        input_form.addRow("マイク", self._mics)
        input_box = QGroupBox("入力")
        input_box.setLayout(input_form)

        oshi = QFormLayout()
        oshi.addRow("心拍ID", self._public_id)
        oshi.addRow("補助 BPM URL", self._bpm_url)
        oshi_inner = QWidget()
        oshi_inner.setLayout(oshi)
        oshi_wrap, _oshi_fold = _make_fold("推しログ(ぬ)連携", oshi_inner, expanded=False)

        cal_row = QHBoxLayout()
        cal_row.addWidget(self._cal_btn)
        cal_row.addWidget(self._discard_cal)
        cal_hint = QLabel(
            "目安は 10〜20 秒と、ドクンに合わせた「拍」（またはスペース）4回以上です。\n"
            "押すたびに心臓へ波紋が出ます。少し遅れても大丈夫です。\n"
            "「補正開始」で心音を覚え、「補正を保存」で型に足します。いらない途中は「補正を破棄」です。\n"
            "間違えて保存したら「設定を初期化」で型を消してやり直せます。\n"
            "ヘッドホン推奨。補正中の音は操作画面だけに聞こえ、配信には出ません。\n"
            "同じマイクで録るか、wav / mp3 を足しても精度が上がります。"
        )
        cal_hint.setObjectName("meta")
        cal_hint.setWordWrap(True)
        cal_box = QGroupBox("心拍の補正（配信前調整）")
        cal_inner = QVBoxLayout()
        cal_inner.addLayout(cal_row)
        cal_inner.addWidget(self._tap_btn)
        cal_inner.addWidget(load_cal)
        cal_inner.addWidget(self._reset_cal)
        cal_inner.addWidget(cal_hint)
        cal_box.setLayout(cal_inner)

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
        layout.addWidget(disclaimer)
        layout.addWidget(input_box)
        layout.addWidget(look_box)
        layout.addWidget(cal_box)
        layout.addWidget(oshi_wrap)
        layout.addWidget(self._aux)
        layout.addWidget(self._warn)
        layout.addStretch(1)
        layout.addWidget(version)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
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
        if path.is_file():
            self._session.profile = load_profile(path)
            self._session.rebuild_detector()

    def _load_selected_profile(self, _index: int = 0) -> None:
        name = self._profiles.currentText().strip()
        if not name:
            return
        path = self._profile_path(name)
        if not path.is_file():
            return
        self._session.profile = load_profile(path)
        self._session.rebuild_detector()
        self._load_into_controls(self._session.profile)
        self._restart_mic()

    def _load_into_controls(self, profile: HeartProfile) -> None:
        # 途中で値変更の合図が飛ぶと、まだ初期値の他の項目でプロファイルが上書きされる。
        # 全部入れ終わってから一度だけ反映する。
        widgets = (
            self._text,
            self._show_beat_text,
            self._beat_scale,
            self._beat_opacity,
            self._show_bpm,
            self._show_arrhythmia,
            self._scale,
            self._opacity,
            self._public_id,
            self._bpm_url,
            self._style,
            self._look,
            self._angle_locked,
            self._mics,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self._text.setText(profile.beat_text)
            self._show_beat_text.setChecked(profile.show_beat_text)
            self._beat_scale.setValue(int(profile.beat_text_scale * 100))
            self._beat_opacity.setValue(int(profile.beat_text_opacity * 100))
            self._show_bpm.setChecked(profile.show_bpm)
            self._show_arrhythmia.setChecked(profile.show_arrhythmia)
            self._scale.setValue(int(profile.scale * 100))
            self._opacity.setValue(int(profile.opacity * 100))
            self._public_id.setText(profile.oshilog_public_id)
            self._bpm_url.setText(profile.oshilog_bpm_url)
            idx = max(0, self._style.findData(profile.style))
            self._style.setCurrentIndex(idx)
            look_idx = max(0, self._look.findData(profile.realistic_look))
            self._look.setCurrentIndex(look_idx)
            for i in range(self._mics.count()):
                if self._mics.itemData(i) == profile.mic_id:
                    self._mics.setCurrentIndex(i)
                    break
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._output.canvas.sync_orbit_from_profile()
        self._apply_controls()
        self._sync_cal_ui()

    def _apply_controls(self) -> None:
        profile = self._session.profile
        profile.name = self._profiles.currentText().strip() or "default"
        profile.style = str(self._style.currentData() or "realistic")
        profile.realistic_look = str(self._look.currentData() or "surgical")
        self._output.canvas.angle_locked = self._angle_locked.isChecked()
        self._refresh_style_controls()
        profile.scale = self._scale.value() / 100.0
        profile.opacity = self._opacity.value() / 100.0
        profile.beat_text = self._text.text() or "ドクン"
        profile.show_beat_text = self._show_beat_text.isChecked()
        profile.beat_text_scale = self._beat_scale.value() / 100.0
        profile.beat_text_opacity = self._beat_opacity.value() / 100.0
        profile.show_bpm = self._show_bpm.isChecked()
        profile.show_arrhythmia = self._show_arrhythmia.isChecked()
        profile.oshilog_public_id = self._public_id.text().strip()
        profile.oshilog_bpm_url = self._bpm_url.text().strip()
        if self._mics.currentData():
            profile.mic_id = str(self._mics.currentData())

    def _refresh_style_controls(self) -> None:
        style = str(self._style.currentData() or "realistic")
        is_realistic = style == "realistic"
        self._look.setVisible(is_realistic)
        self._look_label.setVisible(is_realistic)
        self._angle_wrap.setVisible(style in ROTATABLE_STYLES)
        failed = style in ROTATABLE_STYLES and self._output.canvas.gl_error is not None
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
        try:
            self._mic.start(mic_id)
        except Exception:
            self._level.setText("入力: マイクを開けません（OBS と同時なら独占モードをオフ）")

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
        self._session.commit_calibration()
        self._sync_cal_ui()
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
        count = len(self._session.profile.calibration)
        self._sync_cal_ui()
        self._save_current(notice=f"心音サンプルを追加しました（{count} 件）")

    def _save_current(self, *, notice: str | None = "プロファイルを保存しました") -> None:
        self._apply_controls()
        name = self._session.profile.name
        save_profile(self._profile_path(name), self._session.profile)
        save_last_profile_name(name, self._data_dir)
        if self._profiles.findText(name) < 0:
            self._profiles.blockSignals(True)
            self._profiles.addItem(name)
            self._profiles.setCurrentText(name)
            self._profiles.blockSignals(False)
        if notice:
            self._flash(notice)

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
        self._session.profile.name = name
        self._save_current(notice=f"「{name}」として保存しました")
        self._profiles.blockSignals(True)
        self._profiles.setCurrentText(name)
        self._profiles.blockSignals(False)

    def _poll_aux(self) -> None:
        self._apply_controls()
        bpm = fetch_aux_bpm(self._session.profile.oshilog_bpm_url)
        self._session.clock.oshilog_bpm = bpm
        if bpm is None:
            self._aux.setText("推しログ(ぬ) 補助: —")
        else:
            self._aux.setText(f"推しログ(ぬ) 補助: {bpm}（遅延のことがあります）")

    def _on_tick(self) -> None:
        samples = self._mic.pull_mono()
        if samples:
            peak = max(abs(x) for x in samples)
            self._level.setText(f"入力: {peak:.2f}")
        recording = self._session.recording
        if recording and samples:
            self._monitor.write_mono(samples)
        now = self._now()
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
        self._output.canvas.set_now(self._session.now)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        exclude_from_capture(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_current(notice=None)
        self._monitor.stop()
        self._mic.stop()
        self._output.allow_close()
        self._output.close()
        super().closeEvent(event)
