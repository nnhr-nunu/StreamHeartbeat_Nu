from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QLabel

from stream_heartbeat.ui.slider import labeled_slider


def _wheel() -> QWheelEvent:
    return QWheelEvent(
        QPointF(8, 8),
        QPointF(8, 8),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_labeled_slider_shows_ends_and_ignores_wheel(qapp: QApplication) -> None:
    del qapp
    slider, row = labeled_slider(0, 100, "0", "100")
    slider.setValue(40)
    slider.wheelEvent(_wheel())
    assert slider.value() == 40
    ends = [lab.text() for lab in row.findChildren(QLabel)]
    assert "0" in ends
    assert "100" in ends
