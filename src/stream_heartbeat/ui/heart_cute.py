"""かわいいハート。つやつやの立体感と、拍に合わせたぷにっとした潰れ。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

from stream_heartbeat.clock import CardiacCycle

CUTE_BASE = QColor(255, 96, 150)
CUTE_DEEP = QColor(214, 40, 104)
CUTE_RIM = QColor(150, 20, 70)
CUTE_CHEEK = QColor(255, 150, 176)


def heart_path(cx: float, cy: float, size: float) -> QPainterPath:
    s = size
    path = QPainterPath()
    path.moveTo(cx, cy + 0.42 * s)
    path.cubicTo(cx + 0.98 * s, cy - 0.12 * s, cx + 0.56 * s, cy - 0.98 * s, cx, cy - 0.36 * s)
    path.cubicTo(cx - 0.56 * s, cy - 0.98 * s, cx - 0.98 * s, cy - 0.12 * s, cx, cy + 0.42 * s)
    path.closeSubpath()
    return path


def paint_cute(painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    size = min(rect.width(), rect.height()) * 0.36 * scale
    sq = cycle.squeeze
    bounce = (
        0.06 * math.sin(min(1.0, cycle.age / 0.35) * math.pi) * (1.0 if cycle.age < 0.35 else 0.0)
    )

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(cx, cy + size * 0.06)
    painter.scale(1.0 + 0.14 * sq + bounce, 1.0 - 0.18 * sq - bounce * 0.5)
    painter.translate(-cx, -(cy + size * 0.06))

    path = heart_path(cx, cy, size)
    body = QRadialGradient(QPointF(cx - size * 0.28, cy - size * 0.36), size * 1.35)
    body.setColorAt(0.0, QColor(255, 176, 204))
    body.setColorAt(0.28, CUTE_BASE)
    body.setColorAt(0.75, CUTE_DEEP)
    body.setColorAt(1.0, CUTE_RIM)
    painter.setPen(QPen(CUTE_RIM, max(2.5, size * 0.035)))
    painter.setBrush(body)
    painter.drawPath(path)

    # 下からの照り返し
    painter.setClipPath(path)
    bottom = QLinearGradient(QPointF(cx, cy + size * 0.42), QPointF(cx, cy - size * 0.10))
    bottom.setColorAt(0.0, QColor(255, 120, 170, 130))
    bottom.setColorAt(1.0, QColor(255, 120, 170, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(bottom)
    painter.drawPath(path)

    # 大きなつや
    painter.setBrush(QColor(255, 255, 255, 215))
    painter.save()
    painter.translate(cx - size * 0.40, cy - size * 0.46)
    painter.rotate(-32)
    painter.drawEllipse(QPointF(0, 0), size * 0.20, size * 0.11)
    painter.restore()
    painter.setBrush(QColor(255, 255, 255, 170))
    painter.drawEllipse(QPointF(cx - size * 0.12, cy - size * 0.62), size * 0.05, size * 0.05)

    # ほっぺ
    painter.setBrush(QColor(CUTE_CHEEK.red(), CUTE_CHEEK.green(), CUTE_CHEEK.blue(), 190))
    painter.drawEllipse(QPointF(cx - size * 0.40, cy + size * 0.02), size * 0.11, size * 0.07)
    painter.drawEllipse(QPointF(cx + size * 0.40, cy + size * 0.02), size * 0.11, size * 0.07)

    # 目。拍でぎゅっと閉じる
    eye_open = 1.0 - 0.75 * sq
    for sign in (-1.0, 1.0):
        ex = cx + sign * size * 0.19
        ey = cy - size * 0.10
        painter.setBrush(QColor(44, 24, 48))
        painter.drawEllipse(QPointF(ex, ey), size * 0.055, size * 0.085 * max(0.18, eye_open))
        if eye_open > 0.3:
            painter.setBrush(QColor(255, 255, 255, 230))
            painter.drawEllipse(
                QPointF(ex - size * 0.015, ey - size * 0.035 * eye_open), size * 0.02, size * 0.028
            )

    # 口。拍で「ω」に
    mouth = QPen(QColor(120, 24, 60), max(2.0, size * 0.028))
    mouth.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(mouth)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    my = cy + size * 0.10
    mw = size * 0.10
    m = QPainterPath(QPointF(cx - mw, my))
    m.quadTo(QPointF(cx - mw * 0.5, my + size * 0.06 + size * 0.05 * sq), QPointF(cx, my))
    m.quadTo(QPointF(cx + mw * 0.5, my + size * 0.06 + size * 0.05 * sq), QPointF(cx + mw, my))
    painter.drawPath(m)
    painter.setClipping(False)
    painter.restore()

    # 拍で飛ぶ小さなハートとキラキラ
    if cycle.age < 0.7:
        u = cycle.age / 0.7
        alpha = int(255 * (1.0 - u) ** 1.4)
        for i in range(5):
            ang = math.radians(-120 + i * 30 + 10 * math.sin(i * 2.3))
            dist = size * (0.75 + 0.9 * u)
            px = cx + math.cos(ang) * dist
            py = cy - size * 0.1 + math.sin(ang) * dist * 0.8 - size * 0.2 * u
            r = size * 0.08 * (1.0 - 0.5 * u)
            painter.setPen(Qt.PenStyle.NoPen)
            if i % 2 == 0:
                painter.setBrush(QColor(255, 140, 190, alpha))
                painter.drawPath(heart_path(px, py, r))
            else:
                painter.setBrush(QColor(255, 236, 160, alpha))
                _sparkle(painter, px, py, r * 1.1)


def _sparkle(painter: QPainter, x: float, y: float, r: float) -> None:
    path = QPainterPath(QPointF(x, y - r))
    for i in range(1, 8):
        ang = math.pi * i / 4 - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.35
        path.lineTo(QPointF(x + math.cos(ang) * rad, y + math.sin(ang) * rad))
    path.closeSubpath()
    painter.drawPath(path)
