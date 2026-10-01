"""モニター画面（心電図の演出）。ベッドサイドのモニターの画面に心電図を映す。

枠と暗い画面・方眼は波形より先に、拍で光るハートの印とガラスの映り込みは波形の後に描く。
波形は画面の中（monitor_screen）に収める。誘導の名前（II）だけ小さく出す（数値は出さない）。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen

MONITOR_BG = QColor(9, 13, 20)
MONITOR_BG_CENTER = QColor(16, 23, 36)
MONITOR_GRID = QColor(28, 40, 58)
MONITOR_GRID_MAJOR = QColor(40, 56, 80)
MONITOR_BEZEL_HI = QColor(74, 80, 92)
MONITOR_BEZEL_LO = QColor(20, 22, 28)
MONITOR_LABEL = QColor(150, 162, 182)
MONITOR_HEART = QColor(255, 70, 76)


def _frame(rect: QRectF) -> tuple[QRectF, QRectF, float]:
    side = min(rect.width(), rect.height())
    margin = side * 0.03
    outer = rect.adjusted(margin, margin * 3.0, -margin, -margin * 3.0)
    bezel = side * 0.028
    return outer, outer.adjusted(bezel, bezel, -bezel, -bezel), side


def monitor_screen(rect: QRectF) -> QRectF:
    """波形を描く画面の中（枠の内側）。"""
    return _frame(rect)[1]


def _heart_icon(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath(QPointF(cx, cy + 0.45 * s))
    path.cubicTo(cx + 0.95 * s, cy - 0.15 * s, cx + 0.50 * s, cy - 0.95 * s, cx, cy - 0.38 * s)
    path.cubicTo(cx - 0.50 * s, cy - 0.95 * s, cx - 0.95 * s, cy - 0.15 * s, cx, cy + 0.45 * s)
    path.closeSubpath()
    return path


def paint_monitor_back(painter: QPainter, rect: QRectF) -> None:
    outer, screen, side = _frame(rect)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    bezel = QLinearGradient(outer.topLeft(), outer.bottomLeft())
    bezel.setColorAt(0.0, MONITOR_BEZEL_HI)
    bezel.setColorAt(1.0, MONITOR_BEZEL_LO)
    painter.setBrush(bezel)
    painter.drawRoundedRect(outer, side * 0.045, side * 0.045)
    glow = QLinearGradient(screen.topLeft(), screen.bottomLeft())
    glow.setColorAt(0.0, MONITOR_BG)
    glow.setColorAt(0.5, MONITOR_BG_CENTER)
    glow.setColorAt(1.0, MONITOR_BG)
    painter.setBrush(glow)
    painter.drawRoundedRect(screen, side * 0.025, side * 0.025)

    # 方眼（5 マスごとに少し明るい線）
    painter.setClipRect(screen)
    step = side * 0.025
    thin = QPen(MONITOR_GRID, 1.0)
    major = QPen(MONITOR_GRID_MAJOR, 1.0)
    k = 0
    x = screen.left() + step
    while x < screen.right():
        k += 1
        painter.setPen(major if k % 5 == 0 else thin)
        painter.drawLine(QPointF(x, screen.top()), QPointF(x, screen.bottom()))
        x += step
    k = 0
    y = screen.top() + step
    while y < screen.bottom():
        k += 1
        painter.setPen(major if k % 5 == 0 else thin)
        painter.drawLine(QPointF(screen.left(), y), QPointF(screen.right(), y))
        y += step
    painter.setClipping(False)

    font = QFont()
    font.setPixelSize(max(10, int(side * 0.035)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(MONITOR_LABEL)
    painter.drawText(QPointF(screen.left() + side * 0.025, screen.top() + side * 0.05), "II")
    painter.restore()


def paint_monitor_front(painter: QPainter, rect: QRectF, flash: float) -> None:
    """拍で光るハートの印（右上）と、ガラスの映り込み。flash は拍の直後 1 から 0 へ。"""
    _outer, screen, side = _frame(rect)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    s = side * 0.032 * (1.0 + 0.25 * flash)
    cx = screen.right() - side * 0.05
    cy = screen.top() + side * 0.045
    dim = QColor(MONITOR_HEART.red(), MONITOR_HEART.green(), MONITOR_HEART.blue(), 70)
    lit = QColor(MONITOR_HEART)
    painter.setBrush(lit if flash > 0.05 else dim)
    painter.drawPath(_heart_icon(cx, cy, s))
    # ガラスの映り込み（左上から斜めに淡く）
    painter.setClipRect(screen)
    sheen = QLinearGradient(screen.topLeft(), QPointF(screen.left() + side * 0.5, screen.bottom()))
    sheen.setColorAt(0.0, QColor(255, 255, 255, 22))
    sheen.setColorAt(0.45, QColor(255, 255, 255, 6))
    sheen.setColorAt(0.46, QColor(255, 255, 255, 0))
    painter.setBrush(sheen)
    painter.drawRect(screen)
    painter.restore()
