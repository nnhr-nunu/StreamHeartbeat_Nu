"""はじけるハート（どのスタイルでも選べる演出）。配信用の窓をクリックした所からハートがはじける。

1 回のクリックで 12 個ほどのハートが輪になって飛び出し、勢いを失いながらふわっと浮いて消える。
飛び方はクリックした時刻から決める（同じクリックは同じ飛び方）。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

# はじけたハートが消えるまでの秒
POP_LIFE_S = 1.3
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
