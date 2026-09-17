from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize

from stream_heartbeat.ui.placement import place_side_by_side


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
