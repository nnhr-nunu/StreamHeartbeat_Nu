"""操作画面のスライダー。ホイールでは動かさない。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget


class NoWheelSlider(QSlider):
    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


def labeled_slider(
    minimum: int,
    maximum: int,
    left: str,
    right: str,
) -> tuple[QSlider, QWidget]:
    slider = NoWheelSlider(Qt.Orientation.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    start = QLabel(left)
    start.setObjectName("sliderEnd")
    end = QLabel(right)
    end.setObjectName("sliderEnd")
    layout.addWidget(start)
    layout.addWidget(slider, 1)
    layout.addWidget(end)
    return slider, row
