"""デスクトップの音: 16 kHz モノラルへの変換と、入力欄・録音中の聞き返しの扱い。"""

from __future__ import annotations

import array
import sys
from pathlib import Path

import pytest

from stream_heartbeat.loopback import MonoDownsampler, decode_samples
from stream_heartbeat.profile import load_app_state
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui import input_panel
from stream_heartbeat.ui.input_panel import MODE_DESKTOP, MODE_MIC, InputPanel
from stream_heartbeat.ui.output_window import OVERLAY_MIN_SIDE, OutputWindow


class FakeTap:
    def __init__(self) -> None:
        self.running = False
        self.failed = False
        self.samples = [0.5, -0.5]

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def pull_mono(self) -> list[float]:
        return self.samples if self.running else []


@pytest.mark.parametrize("rate", [8000, 16000, 44100, 48000, 96000])
def test_downsampler_keeps_time_for_any_rate(rate: int) -> None:
    mono = MonoDownsampler(rate, 2)
    out: list[float] = []
    # 細切れに渡しても、1 秒の音は 16000 個前後になる
    for _ in range(100):
        out.extend(mono.feed([0.25] * (rate // 100 * 2)))
    assert abs(len(out) - 16000) <= 1
    assert all(abs(x - 0.25) < 1e-9 for x in out)


def test_downsampler_averages_channels_and_stretch() -> None:
    assert MonoDownsampler(48000, 2).feed([1.0, 0.0] * 3) == [0.5]
    assert MonoDownsampler(16000, 1).feed([0.1, 0.2]) == [0.1, 0.2]
    with pytest.raises(ValueError):
        MonoDownsampler(0, 2)


def test_decode_samples_formats() -> None:
    assert list(decode_samples(array.array("f", [0.5, -0.5]).tobytes(), 32, True)) == [0.5, -0.5]
    assert list(decode_samples(array.array("h", [16384]).tobytes(), 16, False)) == [0.5]
    assert list(decode_samples(array.array("i", [1 << 30]).tobytes(), 32, False)) == [0.5]
    with pytest.raises(ValueError):
        decode_samples(b"\0\0\0", 24, False)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows だけの入力")
def test_panel_runs_tap_only_while_chosen(qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(input_panel, "LoopbackTap", FakeTap)
    panel = InputPanel(tmp_path, lambda _text: None, lambda: 0.0)
    qtbot.addWidget(panel)
    tap = panel._desktop
    assert not tap.running
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_DESKTOP))
    assert tap.running and panel.pull(0.0) == [0.5, -0.5]
    assert load_app_state(tmp_path)["input_mode"] == MODE_DESKTOP
    tap.failed = True
    panel.pull(0.0)
    assert panel._desktop_fail.isVisibleTo(panel)
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_MIC))
    assert not tap.running and panel.pull(0.0) == []
    assert not panel._desktop_fail.isVisibleTo(panel)
    # 覚えたモードで開くと、すぐ取り込み始める
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData(MODE_DESKTOP))
    again = InputPanel(tmp_path, lambda _text: None, lambda: 0.0)
    qtbot.addWidget(again)
    assert again.mode == MODE_DESKTOP and again._desktop.running
    again.shutdown()
    assert not again._desktop.running


def test_overlay_only_applies_on_transparent_backdrop(qapp) -> None:
    del qapp
    from PySide6.QtCore import Qt

    session = HeartSession()
    session.profile.backdrop = "green"
    window = OutputWindow(session)
    window.set_overlay_choice(True, True)
    window.apply_backdrop()
    top = Qt.WindowType.WindowStaysOnTopHint
    through = Qt.WindowType.WindowTransparentForInput
    assert not window.windowFlags() & top and not window.canvas.overlay
    session.profile.backdrop = "transparent"
    window.apply_backdrop()
    assert window.windowFlags() & top and window.windowFlags() & through
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.canvas.overlay and window.minimumWidth() == OVERLAY_MIN_SIDE
    # 出す前の窓は作り直さなくてよい。出したあとに選び直すと作り直す
    assert not window.needs_rebuild()
    window.show()
    assert not window.needs_rebuild()
    window.set_overlay_choice(True, False)
    assert window.needs_rebuild() and not window.needs_transparent_rebuild()
    window.set_overlay_choice(True, True)
    session.profile.backdrop = "green"
    assert window.needs_rebuild()
    window.allow_close()
    window.close()


def test_overlay_right_drag_moves_and_wheel_resizes(qapp) -> None:
    del qapp
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QWheelEvent

    session = HeartSession()
    session.profile.backdrop = "transparent"
    window = OutputWindow(session)
    window.set_overlay_choice(True, False)
    window.apply_backdrop()
    window.setGeometry(100, 100, 400, 400)
    window.show()
    canvas = window.canvas
    right = Qt.MouseButton.RightButton

    def mouse(kind: QEvent.Type, x: float, buttons: Qt.MouseButton = right) -> None:
        spot = QPointF(x, 50.0)
        button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else right
        canvas.event(
            QMouseEvent(kind, spot, spot, spot, button, buttons, Qt.KeyboardModifier.NoModifier)
        )

    start = window.pos()
    mouse(QEvent.Type.MouseButtonPress, 50.0)
    mouse(QEvent.Type.MouseMove, 80.0)
    mouse(QEvent.Type.MouseButtonRelease, 80.0, Qt.MouseButton.NoButton)
    assert window.pos() == start + QPoint(30, 0)
    mouse(QEvent.Type.MouseMove, 120.0, Qt.MouseButton.NoButton)
    assert window.pos() == start + QPoint(30, 0)

    center = window.geometry().center()
    spot = QPointF(10.0, 10.0)
    canvas.wheelEvent(
        QWheelEvent(
            spot,
            spot,
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
    )
    assert window.width() < 400
    assert (window.geometry().center() - center).manhattanLength() <= 2
    window.allow_close()
    window.close()


def test_operator_rebuilds_output_and_remembers_overlay(qapp, tmp_path: Path) -> None:
    del qapp
    from PySide6.QtCore import Qt

    from stream_heartbeat.ui.operator_window import OperatorWindow

    session = HeartSession()
    session.profile.backdrop = "transparent"
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    output.show()
    operator._apply_controls()
    assert operator._overlay_wrap.isVisibleTo(operator)
    operator._on_top.setChecked(True)
    assert operator._output is not output
    assert operator._output.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert load_app_state(operator._data_dir)["overlay_on_top"] is True
    # 緑に戻すと枠のある窓に戻り、設定の欄は隠れる
    operator._backdrop.setCurrentIndex(operator._backdrop.findData("green"))
    assert not operator._output.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert not operator._overlay_wrap.isVisibleTo(operator)
    operator.close()
