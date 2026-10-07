"""操作画面「① 入力」: マイク・音声ファイル・Bluetooth の心拍計の切り替え（β）。"""

from __future__ import annotations

import array
import wave
from pathlib import Path

from PySide6.QtWidgets import QApplication

from stream_heartbeat.ble_heart_rate import CONNECTED
from stream_heartbeat.heart_rate import HeartRateReading
from stream_heartbeat.profile import load_app_state
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.input_panel import MODE_BLE, MODE_FILE, MODE_MIC, InputPanel
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _wav(path: Path, seconds: float) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(array.array("h", [3000] * int(seconds * 16000)).tobytes())
    return path


def _panel(qtbot, tmp_path: Path, clock: FakeTime) -> tuple[InputPanel, list[str]]:
    notices: list[str] = []
    panel = InputPanel(tmp_path, notices.append, clock)
    qtbot.addWidget(panel)
    return panel, notices


def test_file_plays_in_time_loops_and_is_remembered(qtbot, tmp_path: Path) -> None:
    clock = FakeTime()
    panel, notices = _panel(qtbot, tmp_path, clock)
    assert panel.mode == MODE_MIC and panel.pull(0.0) == []
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_FILE))
    panel._file = _wav(tmp_path / "heart.wav", 1.0)
    panel._play.click()
    assert panel._player is not None and panel._player.playing and notices == []
    clock.now = 0.5
    assert len(panel.pull(0.5)) == 8000
    # くり返し再生: 1 秒のファイルを 1.5 秒ぶん流しても止まらない
    assert len(panel.pull(1.5)) == 16000 and panel._player.playing
    panel._loop.setChecked(False)
    state = load_app_state(tmp_path)
    assert state["input_mode"] == MODE_FILE and state["input_loop"] is False
    assert not panel._player.loop
    # 止めると音は来ない。マイクに戻すと（ファイルを使っていないので）何も返さない
    panel._play.click()
    assert panel.pull(2.0) == []
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_MIC))
    assert panel.pull(3.0) == []
    panel.shutdown()


def test_unreadable_file_is_reported(qtbot, tmp_path: Path) -> None:
    clock = FakeTime()
    panel, notices = _panel(qtbot, tmp_path, clock)
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_FILE))
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not audio")
    panel._file = broken
    panel._play.click()
    assert notices == ["このファイルは読めませんでした"]
    assert panel._player is None
    panel.shutdown()


def test_monitor_heart_rate_becomes_beats(qtbot, tmp_path: Path) -> None:
    clock = FakeTime()
    panel, _notices = _panel(qtbot, tmp_path, clock)
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_BLE))
    # つながって心拍数が届いた（本物の Bluetooth は使わない）
    panel._link.state_changed.emit(CONNECTED)
    clock.now = 10.0
    panel._on_reading(HeartRateReading(bpm=75))
    assert panel.heart_rate == 75
    assert panel._ble_status.text() == "受信中  75 BPM"
    assert panel.beats(10.0) == [10.0]
    assert panel.beats(10.5) == [] and panel.beats(10.9) == [10.8]
    # 心拍計を使っていない間は拍を返さない
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_MIC))
    assert panel.beats(12.0) == []
    panel.shutdown()


def test_operator_window_switches_inputs(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    try:
        form = operator._input_form
        combo = operator._input.mode_combo
        assert form.isRowVisible(operator._mics)
        combo.setCurrentIndex(combo.findData(MODE_FILE))
        assert not form.isRowVisible(operator._mics) and form.isRowVisible(operator._meter)
        assert not operator._mic_open
        combo.setCurrentIndex(combo.findData(MODE_BLE))
        assert not form.isRowVisible(operator._meter)
        # 心拍計は音が無いので、補正は始められない
        assert not operator._cal_btn.isEnabled()
        for i in range(8):
            session.tick(i * 0.8, [], beats=[i * 0.8])
        operator._refresh_status()
        assert operator._status.text().startswith("心拍計から受信中")
        combo.setCurrentIndex(combo.findData(MODE_MIC))
        assert operator._cal_btn.isEnabled() and form.isRowVisible(operator._mics)
    finally:
        operator.close()
        output.close()
