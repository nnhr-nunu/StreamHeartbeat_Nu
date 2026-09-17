"""操作画面と配信用を横に並べ、起動時に重ならないようにする。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize

GAP = 28
MARGIN = 32


def place_side_by_side(operator: QSize, output: QSize, screen: QRect) -> tuple[QPoint, QPoint]:
    left = screen.x() + MARGIN
    top = screen.y() + MARGIN
    op = QPoint(left, top)
    out = QPoint(left + operator.width() + GAP, top)
    if out.x() + output.width() > screen.right() - 8:
        out = QPoint(left + min(320, operator.width() // 2), top + min(220, operator.height() // 3))
    out = QPoint(
        min(out.x(), max(screen.x(), screen.right() - output.width() - 8)),
        min(out.y(), max(screen.y(), screen.bottom() - output.height() - 8)),
    )
    if abs(out.x() - op.x()) < 80 and abs(out.y() - op.y()) < 80:
        out = QPoint(min(screen.right() - output.width() - 8, op.x() + 240), op.y() + 160)
    return op, out
