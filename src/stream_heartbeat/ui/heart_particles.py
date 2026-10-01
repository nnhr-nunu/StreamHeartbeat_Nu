"""パーティクル。拍のたびに、窓の下からいくつものハートがふわふわ揺れながら立ちのぼる。

ハートの並びは拍の時刻から決める（同じ拍からは同じハートが出る）。状態を持たないので、
窓を作り直しても、時刻を巻き戻しても同じ絵になる。
- 1 拍で 4〜7 個と、小さなきらめきを 2〜3 個。拍の直後から少しずつずらして出る
- 下で小さく生まれてぽんと膨らみ、ゆっくり加速しながら上へ。左右にゆらゆら揺れ、少し傾く
- 上へ行くほど薄れて消える。色はピンク・赤・ばら色・白っぽいピンク、ふち取りだけのものも混ぜる
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

from stream_heartbeat.clock import BeatClock

# 1 個のハートが消えるまでの秒
PARTICLE_LIFE_S = 4.2
PARTICLE_PALETTE = (
    QColor(255, 92, 138),
    QColor(255, 46, 77),
    QColor(255, 158, 181),
    QColor(255, 214, 226),
    QColor(255, 120, 170),
)


def particle_heart(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath(QPointF(cx, cy + 0.50 * s))
    path.cubicTo(cx + 0.95 * s, cy - 0.10 * s, cx + 0.55 * s, cy - 0.95 * s, cx, cy - 0.40 * s)
    path.cubicTo(cx - 0.55 * s, cy - 0.95 * s, cx - 0.95 * s, cy - 0.10 * s, cx, cy + 0.50 * s)
    path.closeSubpath()
    return path


def beat_origins(clock: BeatClock, now: float, span: float) -> list[float]:
    """now から span 秒さかのぼった範囲で打った拍の時刻（新しい順）。"""
    out: list[float] = []
    t = now
    for _ in range(64):
        origin = clock.origin_before(t)
        if origin < now - span or (out and origin >= out[-1]):
            break
        out.append(origin)
        t = origin - 1e-4
    return out


def _spawn(origin: float) -> list[dict[str, float]]:
    rng = random.Random(int(round(origin * 1000.0)) * 7919 + 17)
    count = rng.randint(4, 7)
    sparkles = rng.randint(2, 3)
    parts = []
    for k in range(count + sparkles):
        parts.append(
            {
                "delay": k * 0.045 + rng.uniform(0.0, 0.12),
                "x": rng.uniform(0.06, 0.94),
                "size": rng.uniform(0.032, 0.085),
                "speed": rng.uniform(0.17, 0.27),
                "sway": rng.uniform(0.018, 0.055),
                "freq": rng.uniform(0.35, 0.75),
                "phase": rng.uniform(0.0, 2.0 * math.pi),
                "tilt": rng.uniform(8.0, 20.0),
                "color": float(rng.randrange(len(PARTICLE_PALETTE))),
                "ring": 1.0 if rng.random() < 0.22 else 0.0,
                "sparkle": 1.0 if k >= count else 0.0,
            }
        )
    return parts


def _draw_one(
    painter: QPainter, x: float, y: float, size: float, angle: float, color: QColor, ring: bool
) -> None:
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    if ring:
        pen = QPen(color, max(1.5, size * 0.16))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(particle_heart(0.0, 0.0, size * 0.92))
        painter.restore()
        return
    # 半透明のにじみは付けない（クロマキーの緑に濁った縁が残る）。明るい縁で光らせる
    body = QRadialGradient(QPointF(-size * 0.25, -size * 0.30), size * 1.1)
    body.setColorAt(0.0, color.lighter(140))
    body.setColorAt(0.6, color)
    body.setColorAt(1.0, color.darker(112))
    painter.setPen(QPen(color.lighter(125), max(1.0, size * 0.06)))
    painter.setBrush(body)
    painter.drawPath(particle_heart(0.0, 0.0, size))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 200))
    painter.drawEllipse(QPointF(-size * 0.32, -size * 0.38), size * 0.13, size * 0.08)
    painter.restore()


def _draw_sparkle(painter: QPainter, x: float, y: float, r: float) -> None:
    path = QPainterPath(QPointF(x, y - r))
    k = r * 0.2
    path.quadTo(QPointF(x + k, y - k), QPointF(x + r, y))
    path.quadTo(QPointF(x + k, y + k), QPointF(x, y + r))
    path.quadTo(QPointF(x - k, y + k), QPointF(x - r, y))
    path.quadTo(QPointF(x - k, y - k), QPointF(x, y - r))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 240, 246))
    painter.drawPath(path)


def paint_particles(
    painter: QPainter, rect: QRectF, scale: float, clock: BeatClock, now: float
) -> None:
    w = rect.width()
    h = rect.height()
    side = min(w, h)
    size_k = max(0.3, scale / 0.7)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    base_opacity = painter.opacity()
    # 古い拍のハート（上の方）から描き、新しいものを手前に
    for origin in reversed(beat_origins(clock, now, PARTICLE_LIFE_S + 0.5)):
        for part in _spawn(origin):
            age = now - origin - part["delay"]
            if age <= 0.0 or age >= PARTICLE_LIFE_S:
                continue
            size = side * part["size"] * size_k
            # ゆっくり加速しながら昇る
            rise = h * part["speed"] * (age + 0.18 * age * age)
            y = rect.bottom() + size - rise
            if y < rect.top() - size * 2.0:
                continue
            x = rect.left() + part["x"] * w
            x += w * part["sway"] * math.sin(2.0 * math.pi * part["freq"] * age + part["phase"])
            angle = part["tilt"] * math.sin(
                2.0 * math.pi * part["freq"] * age + part["phase"] + 1.2
            )
            # 生まれた瞬間はぽんと膨らむ
            pop = min(1.0, age / 0.22)
            grow = 0.4 + 0.6 * (1.0 - (1.0 - pop) ** 3) + 0.12 * math.sin(pop * math.pi)
            # 上へ行くほど、また寿命の終わりほど薄れる
            height_left = (y - rect.top()) / h
            fade = min(1.0, age / 0.25) * min(1.0, height_left / 0.35)
            fade *= min(1.0, (PARTICLE_LIFE_S - age) / 0.8)
            if fade <= 0.01:
                continue
            painter.setOpacity(base_opacity * fade)
            if part["sparkle"] > 0.5:
                # きらめきは小さく、またたきながら昇る
                twinkle = 0.55 + 0.45 * math.sin(age * 9.0 + part["phase"])
                _draw_sparkle(painter, x, y, size * 0.32 * grow * twinkle)
                continue
            color = PARTICLE_PALETTE[int(part["color"])]
            _draw_one(painter, x, y, size * grow, angle, color, part["ring"] > 0.5)
    painter.restore()
