"""聴診器: 心臓に当てたチェストピースと、窓の上の外へ伸びるゴム管。

チェストピースは裏（耳管側）から見た姿。黒い縁と金属の円盤、斜め上へ伸びる軸。
鼓動では心臓に近いほど強く押し返されて手前へ浮き、外へ少しずれ、音の輪が広がる。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.ui.effects import HeartFrame, beat_jolt

TUBE = QColor(38, 38, 44)
TUBE_SHINE = QColor(130, 132, 142, 150)
RIM_DARK = QColor(18, 18, 22)
RIM_LIGHT = QColor(70, 70, 78)
METAL_LIGHT = QColor(238, 241, 245)
METAL_MID = QColor(176, 182, 192)
METAL_DARK = QColor(112, 118, 130)
# 軸の向き（画面の右から反時計回りの度）。管は右上へ抜ける
STEM_DEG = 62.0
# 音の輪が広がり切って消えるまでの秒
RING_LIFE_S = 0.42


def stetho_radius(frame: HeartFrame) -> float:
    """チェストピースの半径。心臓の大きさに合わせる（本物は心臓の縦の 3 分の 1 ほどの径）。"""
    return max(14.0, frame.radius * 0.34)


def paint_stethoscope(
    painter: QPainter,
    rect: QRectF,
    pos: QPointF,
    frame: HeartFrame,
    cycle: CardiacCycle,
    *,
    time_s: float,
    opacity: float,
) -> None:
    """pos（窓の中の点）に当てた聴診器を描く（心臓の後に描く）。"""
    r = stetho_radius(frame)
    heart_r = max(1.0, frame.radius)
    away = pos - frame.center
    dist = math.hypot(away.x(), away.y())
    # 心臓の上ほど鼓動を強く拾う。外れた所では少しだけ
    near = max(0.12, min(1.0, 1.35 - 0.75 * dist / heart_r))
    lift = near * beat_jolt(cycle.squeeze, cycle.fill)
    outward = QPointF(away.x() / dist, away.y() / dist) if dist > 1e-3 else QPointF(0.0, -1.0)
    center = pos + outward * (heart_r * 0.045 * lift)
    size = r * (1.0 + 0.08 * lift)
    tilt = 5.0 * lift * (1.0 if outward.x() >= 0.0 else -1.0)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    stem_dir = QPointF(math.cos(math.radians(STEM_DEG)), -math.sin(math.radians(STEM_DEG)))
    stem_end = center + stem_dir * (size * 1.55)
    _paint_tube(painter, rect, stem_end, stem_dir, size, time_s, lift)
    _paint_shadow(painter, center, size, lift)
    _paint_stem(painter, center, stem_dir, size)
    painter.save()
    painter.translate(center)
    painter.rotate(tilt)
    _paint_head(painter, size)
    painter.restore()
    _paint_rings(painter, center, size, cycle, near)
    painter.restore()


def _paint_tube(
    painter: QPainter,
    rect: QRectF,
    start: QPointF,
    direction: QPointF,
    size: float,
    time_s: float,
    lift: float,
) -> None:
    """軸の先から窓の上の外へ抜けるゴム管。ゆっくり揺れ、鼓動で少し跳ねる。"""
    width = max(4.0, size * 0.2)
    sway = rect.width() * (0.012 * math.sin(time_s * 1.3) + 0.01 * lift)
    end = QPointF(
        start.x() + (rect.right() - start.x()) * 0.35 + sway,
        rect.top() - width * 3.0,
    )
    reach = max(size * 2.0, (start.y() - end.y()) * 0.45)
    c1 = start + direction * reach
    c2 = QPointF(end.x() - sway * 1.5, end.y() + (start.y() - end.y()) * 0.4)
    path = QPainterPath(start)
    path.cubicTo(c1, c2, end)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(TUBE, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPath(path)
    painter.setPen(QPen(TUBE_SHINE, width * 0.22, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPath(path.translated(-width * 0.2, -width * 0.12))


def _paint_shadow(painter: QPainter, center: QPointF, size: float, lift: float) -> None:
    """心臓に落ちる影。浮くほど離れて薄くなる（小さく寄せる。緑の背景で縁が残らないよう）。"""
    offset = QPointF(size * (0.10 + 0.08 * lift), size * (0.13 + 0.10 * lift))
    shadow = QRadialGradient(center + offset, size * 1.1)
    alpha = int(110 * (1.0 - 0.35 * lift))
    shadow.setColorAt(0.0, QColor(0, 0, 0, alpha))
    shadow.setColorAt(0.8, QColor(0, 0, 0, alpha // 2))
    shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(shadow))
    painter.drawEllipse(center + offset, size * 1.1, size * 1.1)


def _paint_stem(painter: QPainter, center: QPointF, direction: QPointF, size: float) -> None:
    """チェストピースから斜め上へ出る金属の軸（根元は円盤の下に隠れる）。"""
    start = center + direction * (size * 0.3)
    end = center + direction * (size * 1.6)
    side = QPointF(-direction.y(), direction.x()) * (size * 0.12)
    shine = QLinearGradient(start + side, start - side)
    shine.setColorAt(0.0, METAL_DARK)
    shine.setColorAt(0.4, METAL_LIGHT)
    shine.setColorAt(1.0, METAL_DARK)
    painter.setPen(QPen(QColor(80, 84, 94), max(1.0, size * 0.02)))
    painter.setBrush(QBrush(shine))
    body = QPainterPath(start + side)
    body.lineTo(end + side)
    body.lineTo(end - side)
    body.lineTo(start - side)
    body.closeSubpath()
    painter.drawPath(body)
    # 管を差し込む輪
    collar = center + direction * (size * 1.22)
    wide = QPointF(-direction.y(), direction.x()) * (size * 0.16)
    ring = QPainterPath(collar + wide)
    ring.lineTo(collar + wide + direction * (size * 0.16))
    ring.lineTo(collar - wide + direction * (size * 0.16))
    ring.lineTo(collar - wide)
    ring.closeSubpath()
    painter.drawPath(ring)


def _paint_head(painter: QPainter, size: float) -> None:
    """原点を中心に、黒い縁・金属の円盤・中央の突起を描く。"""
    origin = QPointF(0.0, 0.0)
    rim = QRadialGradient(QPointF(-size * 0.25, -size * 0.3), size * 1.2)
    rim.setColorAt(0.0, RIM_LIGHT)
    rim.setColorAt(1.0, RIM_DARK)
    painter.setPen(QPen(QColor(8, 8, 10), max(1.0, size * 0.03)))
    painter.setBrush(QBrush(rim))
    painter.drawEllipse(origin, size, size)
    # 縁の左上の照り返し
    painter.setPen(
        QPen(
            QColor(255, 255, 255, 90),
            max(1.0, size * 0.05),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(-size * 0.92, -size * 0.92, size * 1.84, size * 1.84), 100 * 16, 70 * 16)

    disc = size * 0.8
    metal = QConicalGradient(origin, 35.0)
    for stop, color in (
        (0.0, METAL_LIGHT),
        (0.14, METAL_MID),
        (0.3, METAL_LIGHT),
        (0.48, METAL_DARK),
        (0.66, METAL_LIGHT),
        (0.84, METAL_MID),
        (1.0, METAL_LIGHT),
    ):
        metal.setColorAt(stop, color)
    painter.setPen(QPen(QColor(96, 100, 112), max(1.0, size * 0.02)))
    painter.setBrush(QBrush(metal))
    painter.drawEllipse(origin, disc, disc)
    depth = QRadialGradient(QPointF(-disc * 0.3, -disc * 0.35), disc * 1.3)
    depth.setColorAt(0.0, QColor(255, 255, 255, 90))
    depth.setColorAt(0.6, QColor(255, 255, 255, 0))
    depth.setColorAt(1.0, QColor(0, 0, 0, 70))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(depth))
    painter.drawEllipse(origin, disc, disc)
    # 同心の溝
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(90, 95, 106, 170), max(1.0, size * 0.03)))
    painter.drawEllipse(origin, disc * 0.62, disc * 0.62)
    painter.setPen(QPen(QColor(255, 255, 255, 110), max(1.0, size * 0.018)))
    painter.drawEllipse(QPointF(-size * 0.012, -size * 0.016), disc * 0.6, disc * 0.6)
    boss = QRadialGradient(QPointF(-disc * 0.06, -disc * 0.08), disc * 0.26)
    boss.setColorAt(0.0, METAL_LIGHT)
    boss.setColorAt(1.0, METAL_DARK)
    painter.setPen(QPen(QColor(80, 84, 94), max(1.0, size * 0.02)))
    painter.setBrush(QBrush(boss))
    painter.drawEllipse(origin, disc * 0.22, disc * 0.22)


def _paint_rings(
    painter: QPainter, center: QPointF, size: float, cycle: CardiacCycle, near: float
) -> None:
    """拍のたびにチェストピースから広がる音の輪（ドッで 1 つ、少し遅れてクンで 1 つ）。"""
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for delay, strength in ((0.0, 1.0), (0.2, 0.6)):
        age = cycle.age - delay
        if age < 0.0 or age > RING_LIFE_S:
            continue
        k = age / RING_LIFE_S
        alpha = int(170 * near * strength * (1.0 - k) ** 1.5)
        if alpha <= 2:
            continue
        radius = size * (1.12 + 1.1 * k)
        painter.setPen(QPen(QColor(255, 255, 255, alpha), max(1.5, size * 0.05 * (1.0 - 0.5 * k))))
        painter.drawEllipse(center, radius, radius)
