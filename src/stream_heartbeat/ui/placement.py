"""操作画面を右、配信用を左に置く。前回の位置があればそれを使う。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QWidget

GAP = 28
MARGIN = 32
MIN_VISIBLE = 80
TITLE_SLACK = 40


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


def window_geom(widget: QWidget) -> dict[str, int]:
    geo = widget.geometry()
    return {"x": geo.x(), "y": geo.y(), "w": geo.width(), "h": geo.height()}


def parse_geom(data: object) -> QRect | None:
    if not isinstance(data, dict):
        return None
    try:
        x = int(data["x"])
        y = int(data["y"])
        w = int(data["w"])
        h = int(data["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if w < 120 or h < 120:
        return None
    return QRect(x, y, w, h)


def fit_geom_on_screen(rect: QRect, screen: QRect) -> QRect | None:
    if rect.width() < 120 or rect.height() < 120:
        return None
    x = min(max(rect.x(), screen.x()), screen.right() - MIN_VISIBLE)
    y = min(max(rect.y(), screen.y()), screen.bottom() - TITLE_SLACK)
    w = min(max(rect.width(), 120), screen.width())
    h = min(max(rect.height(), 120), screen.height())
    fitted = QRect(x, y, w, h)
    if not fitted.intersects(screen):
        return None
    return fitted


def apply_window_geom(widget: QWidget, data: object, screen: QRect) -> bool:
    rect = parse_geom(data)
    if rect is None:
        return False
    fitted = fit_geom_on_screen(rect, screen)
    if fitted is None:
        return False
    widget.resize(fitted.size())
    widget.move(fitted.topLeft())
    return True
