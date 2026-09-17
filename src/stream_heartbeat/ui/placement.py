"""操作画面を右、配信用を左に置く。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize

GAP = 28
MARGIN = 32


def place_side_by_side(operator: QSize, output: QSize, screen: QRect) -> tuple[QPoint, QPoint]:
    left = screen.x() + MARGIN
    top = screen.y() + MARGIN
    out = QPoint(left, top)
    op = QPoint(left + output.width() + GAP, top)
    if op.x() + operator.width() > screen.right() - 8:
        op = QPoint(
            min(screen.right() - operator.width() - 8, left + min(360, output.width() // 2)),
            top + min(200, output.height() // 4),
        )
    op = QPoint(
        min(op.x(), max(screen.x(), screen.right() - operator.width() - 8)),
        min(op.y(), max(screen.y(), screen.bottom() - operator.height() - 8)),
    )
    out = QPoint(
        min(out.x(), max(screen.x(), screen.right() - output.width() - 8)),
        min(out.y(), max(screen.y(), screen.bottom() - output.height() - 8)),
    )
    if abs(out.x() - op.x()) < 80 and abs(out.y() - op.y()) < 80:
        op = QPoint(min(screen.right() - operator.width() - 8, out.x() + 280), out.y() + 140)
    return op, out
