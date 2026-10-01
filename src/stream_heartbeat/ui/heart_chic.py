"""オシャレ1。モデル雑誌の表紙のような、刷りもの風の色づかいのハート。

- 後ろにバターイエローの丸（太陽）と、細いコバルトの輪
- 蛍光ピンクのハートと、右下へずれて覗くコバルトのハート（刷りのずれ）
- ピンクの面に、2 色目が刷り重なったすみれの網点（ハーフトーン）の陰と、紙に刷ったようなかすれ
- 少しずれた線画のハートと、小さな十字・星・効果線のあしらい
- 拍で刷りのずれが開き、丸がふくらみ、効果線が飛ぶ
窓の描き方（GL）では色の合成の種類が使えないこともあるので、重なりの色はそのまま塗る。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform

from stream_heartbeat.clock import CardiacCycle

CHIC_SUN = QColor(255, 213, 74)
CHIC_PINK = QColor(255, 62, 140)
CHIC_COBALT = QColor(45, 71, 240)
CHIC_VIOLET = QColor(74, 31, 168)
CHIC_INK = QColor(28, 24, 64)
CHIC_CREAM = QColor(255, 244, 230)


def chic_heart(cx: float, cy: float, s: float) -> QPainterPath:
    """少し縦長で、肩の張った大人っぽいハート。"""
    path = QPainterPath(QPointF(cx, cy + 0.66 * s))
    path.cubicTo(
        cx + 0.30 * s, cy + 0.36 * s, cx + 0.86 * s, cy + 0.02 * s, cx + 0.84 * s, cy - 0.36 * s
    )
    path.cubicTo(cx + 0.82 * s, cy - 0.74 * s, cx + 0.28 * s, cy - 0.86 * s, cx, cy - 0.46 * s)
    path.cubicTo(
        cx - 0.28 * s, cy - 0.86 * s, cx - 0.82 * s, cy - 0.74 * s, cx - 0.84 * s, cy - 0.36 * s
    )
    path.cubicTo(cx - 0.86 * s, cy + 0.02 * s, cx - 0.30 * s, cy + 0.36 * s, cx, cy + 0.66 * s)
    path.closeSubpath()
    return path


def _scaled(path: QPainterPath, center: QPointF, k: float) -> QPainterPath:
    t = QTransform()
    t.translate(center.x(), center.y())
    t.scale(k, k)
    t.translate(-center.x(), -center.y())
    return t.map(path)


def _halftone(painter: QPainter, heart: QPainterPath, cx: float, cy: float, s: float) -> None:
    """網点の陰。右下ほど点が大きい。"""
    painter.save()
    painter.setClipPath(heart)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(CHIC_VIOLET.red(), CHIC_VIOLET.green(), CHIC_VIOLET.blue(), 210))
    step = s * 0.075
    angle = math.radians(18.0)
    ca, sa = math.cos(angle), math.sin(angle)
    span = int(1.3 * s / step) + 2
    box = heart.boundingRect()
    for i in range(-span, span + 1):
        for j in range(-span, span + 1):
            u = i * step
            v = j * step
            x = cx + u * ca - v * sa
            y = cy + u * sa + v * ca
            if not box.contains(x, y):
                continue
            shade = ((x - cx) * 0.8 + (y - cy) * 0.6) / s
            r = step * 0.46 * max(0.0, min(1.0, (shade + 0.05) / 0.85))
            if r > step * 0.05:
                painter.drawEllipse(QPointF(x, y), r, r)
    painter.restore()


def _grain(painter: QPainter, heart: QPainterPath, cx: float, cy: float, s: float) -> None:
    """刷りのかすれ。ハートに付いて一緒に動く、決まった並びの小さな点。"""
    painter.save()
    painter.setClipPath(heart)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(CHIC_CREAM.red(), CHIC_CREAM.green(), CHIC_CREAM.blue(), 70))
    seed = 12345
    for _ in range(140):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        x = cx + ((seed % 1000) / 1000.0 - 0.5) * 1.8 * s
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        y = cy + ((seed % 1000) / 1000.0 - 0.5) * 1.6 * s
        r = s * (0.004 + 0.010 * ((seed >> 10) % 100) / 100.0)
        painter.drawEllipse(QPointF(x, y), r, r)
    painter.restore()


def _plus(painter: QPainter, x: float, y: float, r: float) -> None:
    painter.drawLine(QPointF(x - r, y), QPointF(x + r, y))
    painter.drawLine(QPointF(x, y - r), QPointF(x, y + r))


def _star(x: float, y: float, r: float) -> QPainterPath:
    path = QPainterPath(QPointF(x, y - r))
    for i in range(1, 8):
        ang = math.pi * i / 4 - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.30
        path.lineTo(QPointF(x + math.cos(ang) * rad, y + math.sin(ang) * rad))
    path.closeSubpath()
    return path


def paint_chic(
    painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle, now: float = 0.0
) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    s = min(rect.width(), rect.height()) * 0.36 * scale
    sq = cycle.squeeze
    # 拍で刷りのずれが開き、ゆっくり戻る
    kick = math.exp(-cycle.age / 0.25) if cycle.age < 1.5 else 0.0
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)

    # 太陽（後ろの丸）と細い輪
    sun_r = s * 0.95 * (1.0 + 0.03 * sq)
    painter.setBrush(CHIC_SUN)
    painter.drawEllipse(QPointF(cx + s * 0.24, cy - s * 0.20), sun_r, sun_r)
    ring = QPen(CHIC_COBALT, max(1.5, s * 0.018))
    painter.setPen(ring)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(cx - s * 0.38, cy + s * 0.30), s * 0.66, s * 0.66)
    painter.setPen(Qt.PenStyle.NoPen)

    pulse = 1.0 + 0.08 * sq
    center = QPointF(cx, cy)
    pink = _scaled(chic_heart(cx, cy, s), center, pulse)
    off = s * (0.07 + 0.05 * kick)
    blue = pink.translated(off, off * 0.8)
    painter.setBrush(CHIC_COBALT)
    painter.drawPath(blue)
    painter.setBrush(CHIC_PINK)
    painter.drawPath(pink)
    # ピンクの右下に網点の陰（2 色目が刷り重なったすみれ）
    _halftone(painter, pink, cx, cy, s * pulse)
    _grain(painter, pink, cx, cy, s * pulse)

    # ずれた線画のハート
    line = QPen(CHIC_INK, max(1.5, s * 0.022))
    line.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(line)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    jitter = s * 0.02 * kick
    outline = _scaled(chic_heart(cx, cy, s), center, 1.05 * pulse)
    painter.drawPath(outline.translated(-s * 0.08 - jitter, -s * 0.07 + jitter))

    # あしらい: 十字・星・効果線
    small = QPen(CHIC_INK, max(1.2, s * 0.016))
    small.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(small)
    _plus(painter, cx - s * 1.02, cy - s * 0.62, s * 0.06)
    _plus(painter, cx + s * 1.08, cy + s * 0.42, s * 0.045)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(CHIC_PINK)
    twinkle = 0.8 + 0.2 * math.sin(now * 3.0)
    painter.drawPath(_star(cx + s * 0.98, cy - s * 0.86, s * 0.10 * twinkle))
    painter.setBrush(CHIC_COBALT)
    painter.drawPath(_star(cx - s * 0.80, cy + s * 0.70, s * 0.06))
    if kick > 0.05:
        burst = QPen(CHIC_INK, max(1.5, s * 0.02))
        burst.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(burst)
        reach = s * (0.10 + 0.12 * (1.0 - kick))
        for k, ang in enumerate((-70.0, -45.0, -20.0)):
            a = math.radians(ang)
            base = QPointF(cx + s * 0.78, cy - s * 0.66)
            start = base + QPointF(math.cos(a), math.sin(a)) * (s * 0.06 + reach * 0.4)
            end = base + QPointF(math.cos(a), math.sin(a)) * (s * 0.06 + reach * (1.0 + 0.2 * k))
            painter.drawLine(start, end)
    painter.restore()
