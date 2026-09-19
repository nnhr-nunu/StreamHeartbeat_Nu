from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from stream_heartbeat.ui.heart_paint import backdrop_color, paint_bpm


def test_backdrop_colors() -> None:
    assert backdrop_color("green").name().lower() == "#00ff00"
    assert backdrop_color("white").name().lower() == "#ffffff"
    assert backdrop_color("black").name().lower() == "#000000"
    trans = backdrop_color("transparent")
    assert trans.alpha() == 0


def test_paint_bpm_can_sit_high_with_outline(qapp: QApplication) -> None:
    del qapp
    image = QImage(240, 240, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 255, 0))
    painter = QPainter(image)
    paint_bpm(
        painter,
        QRectF(0, 0, 240, 240),
        88,
        scale=1.6,
        pos=(0.5, 0.18),
        color="#FFFFFF",
        outline="#000000",
    )
    painter.end()
    top_has_ink = False
    bottom_is_green = True
    for y in range(20, 80):
        for x in range(60, 180):
            top = QColor(image.pixel(x, y))
            if top != QColor(0, 255, 0):
                top_has_ink = True
                break
        if top_has_ink:
            break
    for x in range(60, 180):
        bottom = QColor(image.pixel(x, 220))
        if bottom != QColor(0, 255, 0):
            bottom_is_green = False
    assert top_has_ink
    assert bottom_is_green
