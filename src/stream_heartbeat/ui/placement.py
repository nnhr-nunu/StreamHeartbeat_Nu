"""操作画面を右、配信用を左に置く。前回の位置があればそれを使う。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QWidget

GAP = 28
MARGIN = 32
MIN_VISIBLE = 80
TITLE_SLACK = 40
# 横に並べるのに要る余白の最小（端 2 つと間の合計 px）
MIN_SPARE = 24


def place_side_by_side(operator: QSize, output: QSize, screen: QRect) -> tuple[QPoint, QPoint]:
    """操作画面と配信用の窓の位置（操作画面, 配信用）。

    横に並びきらない画面では、端と間の余白を詰めて重ならないようにする。それでも入らなければ
    少しずらして重ねる。
    """
    margin, gap = MARGIN, GAP
    spare = screen.width() - output.width() - operator.width()
    if spare < MARGIN * 2 + GAP and spare >= MIN_SPARE:
        margin = gap = spare // 3
    left = screen.x() + margin
    top = screen.y() + MARGIN
    out = QPoint(left, top)
    op = QPoint(left + output.width() + gap, top)
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


def separate_windows(
    operator: QWidget, output: QWidget, screens: list[QRect], fallback: QRect
) -> bool:
    """2 つの窓が重なっていれば、操作画面のある画面に横に並べ直す。並べ直したら True。

    起動したときにどちらの窓も隠れずに前へ出るようにする（前回の位置が重なっていたときも）。
    """
    op_rect = operator.frameGeometry()
    out_rect = output.frameGeometry()
    if not op_rect.intersects(out_rect):
        return False
    screen = screen_for(op_rect, screens, fallback)
    op_pos, out_pos = place_side_by_side(operator.size(), output.size(), screen)
    output.move(out_pos)
    operator.move(op_pos)
    return True


def window_geom(widget: QWidget) -> dict[str, int]:
    # move() は枠を含む位置なので pos() で保存する（geometry() だと枠の分ずつずれる）
    pos = widget.pos()
    size = widget.size()
    return {"x": pos.x(), "y": pos.y(), "w": size.width(), "h": size.height()}


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


def screen_for(rect: QRect, screens: list[QRect], fallback: QRect) -> QRect:
    """保存した位置といちばん広く重なる画面。どれにも重ならなければ fallback（主画面）。"""
    best = fallback
    best_area = 0
    for screen in screens:
        overlap = rect.intersected(screen)
        area = 0 if overlap.isEmpty() else overlap.width() * overlap.height()
        if area > best_area:
            best = screen
            best_area = area
    return best


def apply_window_geom(
    widget: QWidget, data: object, screen: QRect, screens: list[QRect] | None = None
) -> bool:
    """前回の位置へ戻す。2 枚目以降の画面に置いていた窓はその画面に戻す。"""
    rect = parse_geom(data)
    if rect is None:
        return False
    fitted = fit_geom_on_screen(rect, screen_for(rect, screens or [], screen))
    if fitted is None:
        return False
    widget.resize(fitted.size())
    widget.move(fitted.topLeft())
    return True
