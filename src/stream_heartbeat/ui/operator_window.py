"""手元確認用の操作画面。配信出力とは別窓。"""

from __future__ import annotations

import wave
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE, display_version
from stream_heartbeat.audio import MicTap, list_mics
from stream_heartbeat.config import DETECT_LOST_LABEL, DISCLAIMER
from stream_heartbeat.detect import load_wav_mono
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
from stream_heartbeat.ui.app_icon import apply_app_icon
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.styles import DARK_QSS

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
        self.setMinimumSize(440, 420)
        self.resize(500, 760)
        self.setStyleSheet(DARK_QSS)
        apply_app_icon(self)

        self._status = QLabel(DETECT_LOST_LABEL)
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        self._aux = QLabel("OshiLog 補助: —")
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
        self._show_arrhythmia = QCheckBox("不整脈！を配信用に出す")
        self._public_id = QLineEdit()
        self._bpm_url = QLineEdit()
        self._level = QLabel("入力: —")

        start_cal = QPushButton("キャリブ開始")
        keep_cal = QPushButton("このセッションを採用")
        drop_cal = QPushButton("破棄")
        load_cal = QPushButton("心音WAVを追加")
        save_btn = QPushButton("プロファイルを保存")

        start_cal.clicked.connect(self._session.begin_calibration)
        keep_cal.clicked.connect(self._commit_cal)
        drop_cal.clicked.connect(self._session.discard_calibration)
        load_cal.clicked.connect(self._add_wav_sample)
        save_btn.clicked.connect(self._save_current)
        self._profiles.currentTextChanged.connect(self._maybe_load_named)
        self._style.currentIndexChanged.connect(self._apply_controls)
        self._scale.valueChanged.connect(self._apply_controls)
        self._opacity.valueChanged.connect(self._apply_controls)
        self._text.textChanged.connect(self._apply_controls)
        self._show_bpm.toggled.connect(self._apply_controls)
        self._show_arrhythmia.toggled.connect(self._apply_controls)
        self._mics.currentIndexChanged.connect(self._restart_mic)

        look = QFormLayout()
        look.addRow("スタイル", self._style)
        look.addRow("大きさ", self._scale)
        look.addRow("透明度", self._opacity)
        look.addRow("同期文字", self._text)
        look.addRow(self._show_bpm)
        look.addRow(self._show_arrhythmia)
        look_box = QGroupBox("配信用の見た目")
        look_box.setLayout(look)

        input_form = QFormLayout()
        input_form.addRow("プロファイル", self._profiles)
        input_form.addRow("マイク", self._mics)
        input_box = QGroupBox("入力")
        input_box.setLayout(input_form)

        oshi = QFormLayout()
        oshi.addRow("心拍ID", self._public_id)
        oshi.addRow("補助 BPM URL", self._bpm_url)
        oshi_box = QGroupBox("OshiLog")
        oshi_box.setLayout(oshi)

        cal_row = QHBoxLayout()
        cal_row.addWidget(start_cal)
        cal_row.addWidget(keep_cal)
        cal_row.addWidget(drop_cal)
        cal_hint = QLabel(
            "同じマイクで自分の心音を録るか、16bit WAV を足すと精度が上がります。"
            "指パッチンのような高い短い音は捨てます。"
        )
        cal_hint.setObjectName("meta")
        cal_hint.setWordWrap(True)
        cal_box = QGroupBox("キャリブ（配信前）")
        cal_inner = QVBoxLayout()
        cal_inner.addLayout(cal_row)
        cal_inner.addWidget(load_cal)
        cal_inner.addWidget(cal_hint)
        cal_box.setLayout(cal_inner)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(disclaimer)
        layout.addWidget(input_box)
        layout.addWidget(look_box)
        layout.addWidget(cal_box)
        layout.addWidget(oshi_box)
        layout.addWidget(save_btn)
        layout.addWidget(self._level)
        layout.addWidget(self._status)
        layout.addWidget(self._aux)
        layout.addWidget(self._warn)
        layout.addStretch(1)
        layout.addWidget(version)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

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
        self._show_arrhythmia.setChecked(profile.show_arrhythmia)
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
        profile.show_arrhythmia = self._show_arrhythmia.isChecked()
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

    def _add_wav_sample(self) -> None:
        path, _ok = QFileDialog.getOpenFileName(self, "心音WAVを追加", "", "WAV (*.wav)")
        if not path:
            return
        try:
            samples = load_wav_mono(Path(path))
        except (OSError, ValueError, wave.Error):
            self._warn.setText("WAV は 16bit で、先頭チャンネルだけ使います")
            return
        if not samples:
            self._warn.setText("WAV が空でした")
            return
        self._session.profile.calibration.append(samples)
        self._session.rebuild_detector()
        self._save_current()
        count = len(self._session.profile.calibration)
        self._status.setText(f"心音サンプルを追加しました（{count} 件）")

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
