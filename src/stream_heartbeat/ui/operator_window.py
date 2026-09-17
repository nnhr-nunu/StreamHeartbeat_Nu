"""手元確認用の操作画面。配信出力とは別窓。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE
from stream_heartbeat.audio import MicTap, list_mics
from stream_heartbeat.config import DETECT_LOST_LABEL, DISCLAIMER
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
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.output_window import OutputWindow

STYLES = [
    ("realistic", "リアル"),
    ("cute", "かわいい"),
    ("mech", "機械"),
    ("ecg", "心電図"),
]


class OperatorWindow(QMainWindow):
    def __init__(self, session: HeartSession, output: OutputWindow) -> None:
        super().__init__()
        self._session = session
        self._output = output
        self._mic = MicTap()
        self._data_dir = resolve_data_dir()
        self._mono = 0.0
        self.setWindowTitle(OPERATOR_WINDOW_TITLE)
        self.setMinimumSize(420, 560)
        self.resize(460, 640)

        self._status = QLabel(DETECT_LOST_LABEL)
        self._aux = QLabel("OshiLog 補助: —")
        self._warn = QLabel("")
        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setWordWrap(True)

        self._profiles = QComboBox()
        self._profiles.setEditable(True)
        self._mics = QComboBox()
        self._style = QComboBox()
        for key, label in STYLES:
            self._style.addItem(label, key)
        self._scale = QSlider(Qt.Orientation.Horizontal)
        self._scale.setRange(20, 120)
        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(10, 100)
        self._text = QLineEdit()
        self._show_bpm = QCheckBox("心拍数を配信用に出す")
        self._public_id = QLineEdit()
        self._bpm_url = QLineEdit()
        self._level = QLabel("入力: —")

        start_cal = QPushButton("キャリブ開始")
        keep_cal = QPushButton("このセッションを採用")
        drop_cal = QPushButton("破棄")
        save_btn = QPushButton("プロファイルを保存")

        start_cal.clicked.connect(self._session.begin_calibration)
        keep_cal.clicked.connect(self._commit_cal)
        drop_cal.clicked.connect(self._session.discard_calibration)
        save_btn.clicked.connect(self._save_current)
        self._profiles.currentTextChanged.connect(self._maybe_load_named)
        self._style.currentIndexChanged.connect(self._apply_controls)
        self._scale.valueChanged.connect(self._apply_controls)
        self._opacity.valueChanged.connect(self._apply_controls)
        self._text.textChanged.connect(self._apply_controls)
        self._show_bpm.toggled.connect(self._apply_controls)
        self._mics.currentIndexChanged.connect(self._restart_mic)

        form = QFormLayout()
        form.addRow("プロファイル", self._profiles)
        form.addRow("マイク", self._mics)
        form.addRow("スタイル", self._style)
        form.addRow("大きさ", self._scale)
        form.addRow("透明度", self._opacity)
        form.addRow("同期文字", self._text)
        form.addRow(self._show_bpm)
        form.addRow("OshiLog 心拍ID", self._public_id)
        form.addRow("補助 BPM URL", self._bpm_url)

        cal_row = QHBoxLayout()
        cal_row.addWidget(start_cal)
        cal_row.addWidget(keep_cal)
        cal_row.addWidget(drop_cal)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(disclaimer)
        layout.addLayout(form)
        layout.addLayout(cal_row)
        layout.addWidget(save_btn)
        layout.addWidget(self._level)
        layout.addWidget(self._status)
        layout.addWidget(self._aux)
        layout.addWidget(self._warn)
        self.setCentralWidget(root)

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

    def _maybe_load_named(self, name: str) -> None:
        path = self._profile_path(name)
        if path.is_file():
            self._session.profile = load_profile(path)
            self._session.rebuild_detector()
            self._load_into_controls(self._session.profile)
            self._restart_mic()

    def _load_into_controls(self, profile: HeartProfile) -> None:
        self._text.setText(profile.beat_text)
        self._show_bpm.setChecked(profile.show_bpm)
        self._scale.setValue(int(profile.scale * 100))
        self._opacity.setValue(int(profile.opacity * 100))
        self._public_id.setText(profile.oshilog_public_id)
        self._bpm_url.setText(profile.oshilog_bpm_url)
        idx = max(0, self._style.findData(profile.style))
        self._style.setCurrentIndex(idx)
        for i in range(self._mics.count()):
            if self._mics.itemData(i) == profile.mic_id:
                self._mics.setCurrentIndex(i)
                break

    def _apply_controls(self) -> None:
        profile = self._session.profile
        profile.name = self._profiles.currentText().strip() or "default"
        profile.style = str(self._style.currentData() or "realistic")
        profile.scale = self._scale.value() / 100.0
        profile.opacity = self._opacity.value() / 100.0
        profile.beat_text = self._text.text() or "ドクン"
        profile.show_bpm = self._show_bpm.isChecked()
        profile.oshilog_public_id = self._public_id.text().strip()
        profile.oshilog_bpm_url = self._bpm_url.text().strip()
        if self._mics.currentData():
            profile.mic_id = str(self._mics.currentData())

    def _restart_mic(self) -> None:
        self._apply_controls()
        mic_id = str(self._mics.currentData() or "")
        try:
            self._mic.start(mic_id)
        except Exception:
            self._level.setText("入力: マイクを開けません（OBS と同時なら独占モードをオフ）")

    def _commit_cal(self) -> None:
        self._session.commit_calibration()
        self._save_current()

    def _save_current(self) -> None:
        self._apply_controls()
        name = self._session.profile.name
        save_profile(self._profile_path(name), self._session.profile)
        save_last_profile_name(name, self._data_dir)
        if self._profiles.findText(name) < 0:
            self._profiles.addItem(name)

    def _poll_aux(self) -> None:
        self._apply_controls()
        bpm = fetch_aux_bpm(self._session.profile.oshilog_bpm_url)
        self._session.clock.oshilog_bpm = bpm
        if bpm is None:
            self._aux.setText("OshiLog 補助: —")
        else:
            self._aux.setText(f"OshiLog 補助: {bpm}（遅延のことがあります）")

    def _on_tick(self) -> None:
        samples = self._mic.pull_mono()
        if samples:
            peak = max(abs(x) for x in samples)
            self._level.setText(f"入力: {peak:.2f}")
        self._mono += 0.016
        self._session.tick(self._mono, samples)
        if self._session.clock.detected:
            self._status.setText(f"検出中  {self._session.clock.bpm} BPM")
        else:
            self._status.setText(DETECT_LOST_LABEL)
        if self._session.clock.bpm_mismatch():
            self._warn.setText("時計と数字がズレています（OshiLog は遅延します）")
        else:
            self._warn.setText("")
        self._output.canvas.set_now(self._mono)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_current()
        self._mic.stop()
        self._output.allow_close()
        self._output.close()
        super().closeEvent(event)
