"""はじけるハート（どのスタイルでも選べる演出）。

- 鼓動のたびに、心臓の縁から小さなハートが 6 個ほど上と横へはじけて、ふわっと浮いて消える
  （選んだだけで動きが見える）
- 配信用の窓をクリックすると、その所から 12 個ほどのハートが輪になって大きくはじける

飛び方は拍・クリックの時刻から決める（同じ拍・同じクリックは同じ飛び方）。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

# はじけたハートが消えるまでの秒（クリック・鼓動）
POP_LIFE_S = 1.3
BEAT_POP_LIFE_S = 0.9
# 鼓動ではじけるハートの数と、飛ぶ向きの範囲（画面で右が 0°、上が負。下の心拍数の文字を避ける）
BEAT_POP_COUNT = 6
BEAT_POP_ARC = (-165.0, -15.0)
POP_COLORS = (
    QColor(255, 82, 132),
    QColor(255, 46, 77),
    QColor(255, 170, 196),
    QColor(255, 236, 242),
)


def _heart(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath(QPointF(cx, cy + 0.50 * s))
    path.cubicTo(cx + 0.95 * s, cy - 0.10 * s, cx + 0.55 * s, cy - 0.95 * s, cx, cy - 0.40 * s)
    path.cubicTo(cx - 0.55 * s, cy - 0.95 * s, cx - 0.95 * s, cy - 0.10 * s, cx, cy + 0.50 * s)
    path.closeSubpath()
    return path


def paint_heart_pops(
    painter: QPainter, rect: QRectF, pops: list[tuple[float, float, float, float]]
) -> None:
    """pops は (はじけてからの秒, x の割合, y の割合, クリックの時刻) の並び。"""
    side = min(rect.width(), rect.height())
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    base = painter.opacity()
    for age, rx, ry, stamp in pops:
        if age < 0.0 or age >= POP_LIFE_S:
            continue
        x0 = rect.left() + rx * rect.width()
        y0 = rect.top() + ry * rect.height()
        u = age / POP_LIFE_S
        # はじけた瞬間の輪
        if age < 0.35:
            ring = age / 0.35
            painter.setOpacity(base * (1.0 - ring) * 0.9)
            painter.setPen(QPen(QColor(255, 214, 228), max(1.5, side * 0.008 * (1.0 - ring))))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(x0, y0), side * 0.15 * ring, side * 0.15 * ring)
        rng = random.Random(int(stamp * 1000.0) * 131 + 7)
        count = 12
        painter.setPen(Qt.PenStyle.NoPen)
        for k in range(count):
            ang = 2.0 * math.pi * k / count + rng.uniform(-0.25, 0.25)
            reach = side * rng.uniform(0.12, 0.22)
            # 勢いよく飛び出して、ゆっくり止まり、ふわっと浮く
            travel = reach * (1.0 - math.exp(-age * 4.5))
            x = x0 + math.cos(ang) * travel
            y = y0 + math.sin(ang) * travel - side * 0.06 * age * age
            size = side * rng.uniform(0.022, 0.042)
            pop = min(1.0, age / 0.12)
            grow = 0.3 + 0.7 * pop + 0.15 * math.sin(pop * math.pi)
            painter.setOpacity(base * (1.0 - u) ** 1.4)
            painter.setBrush(POP_COLORS[k % len(POP_COLORS)])
            painter.save()
            painter.translate(x, y)
            painter.rotate(math.degrees(ang) * 0.15 + 25.0 * math.sin(age * 6.0 + k))
            painter.drawPath(_heart(0.0, 0.0, size * grow))
            painter.restore()
    painter.restore()


def paint_beat_pops(
    painter: QPainter, center: QPointF, radius: float, pops: list[tuple[float, float]]
) -> None:
    """鼓動ではじけるハート。pops は (拍からの秒, 拍の時刻) の並び。center・radius は心臓の所。"""
    if radius <= 1.0:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    base = painter.opacity()
    lo, hi = BEAT_POP_ARC
    for age, stamp in pops:
        if age < 0.0 or age >= BEAT_POP_LIFE_S:
            continue
        u = age / BEAT_POP_LIFE_S
        rng = random.Random(int(stamp * 1000.0) * 97 + 3)
        for k in range(BEAT_POP_COUNT):
            ang = math.radians(
                lo + (hi - lo) * (k + 0.5) / BEAT_POP_COUNT + rng.uniform(-10.0, 10.0)
            )
            # 心臓の縁から外へ飛び出し、ゆっくり止まって浮く
            start = radius * rng.uniform(0.92, 1.08)
            travel = start + radius * rng.uniform(0.35, 0.6) * (1.0 - math.exp(-age * 4.0))
            x = center.x() + math.cos(ang) * travel
            y = center.y() + math.sin(ang) * travel - radius * 0.25 * age * age
            size = radius * rng.uniform(0.13, 0.19)
            pop = min(1.0, age / 0.10)
            # 消えるときは薄めずに縮める（半透明にするとクロマキーの緑が透けて濁る）
            grow = (0.3 + 0.7 * pop + 0.15 * math.sin(pop * math.pi)) * (1.0 - _smooth(0.5, 1.0, u))
            painter.setOpacity(base * (1.0 - _smooth(0.85, 1.0, u)))
            painter.setBrush(POP_COLORS[(k + int(stamp * 10.0)) % len(POP_COLORS)])
            painter.save()
            painter.translate(x, y)
            painter.rotate(math.degrees(ang + math.pi / 2.0) * 0.25)
            painter.drawPath(_heart(0.0, 0.0, size * grow))
            painter.restore()
    painter.restore()


def _smooth(a: float, b: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)
