from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QWidget

from stream_heartbeat.ui.placement import (
    apply_window_geom,
    fit_geom_on_screen,
    place_side_by_side,
    window_geom,
)


def test_operator_and_output_do_not_share_origin() -> None:
    op, out = place_side_by_side(QSize(480, 740), QSize(720, 720), QRect(0, 0, 1920, 1080))
    assert op != out
    assert out.x() < op.x()
    op_rect = QRect(op, QSize(480, 740))
    out_rect = QRect(out, QSize(720, 720))
    assert not op_rect.intersects(out_rect)


def test_small_screen_still_offsets_windows() -> None:
    op, out = place_side_by_side(QSize(480, 740), QSize(720, 720), QRect(0, 0, 1280, 720))
    assert op != QPoint(out.x(), out.y())
    assert abs(out.x() - op.x()) >= 80 or abs(out.y() - op.y()) >= 80


def test_fit_geom_keeps_window_on_screen() -> None:
    screen = QRect(0, 0, 1920, 1080)
    fitted = fit_geom_on_screen(QRect(100, 80, 500, 700), screen)
    assert fitted == QRect(100, 80, 500, 700)
    off = fit_geom_on_screen(QRect(-4000, -4000, 500, 700), screen)
    assert off is not None
    assert screen.intersects(off)


def test_apply_window_geom_restores_position(qapp) -> None:
    del qapp
    screen = QRect(0, 0, 1920, 1080)
    widget = QWidget()
    widget.resize(400, 300)
    saved = {"x": 220, "y": 90, "w": 480, "h": 640}
    assert apply_window_geom(widget, saved, screen) is True
    assert widget.pos() == QPoint(220, 90)
    assert widget.size() == QSize(480, 640)
    assert window_geom(widget)["x"] == 220
    widget.close()
