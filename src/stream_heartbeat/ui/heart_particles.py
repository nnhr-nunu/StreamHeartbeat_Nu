"""パーティクル。拍のたびに、真ん中からハートが一気にぶわっと広がり、ふわっと浮いてすうっと消える。

ハートの並びは拍の時刻から決める（同じ拍からは同じハートが出る）。状態を持たないので、
窓を作り直しても、時刻を巻き戻しても同じ絵になる。
- 拍の頭に、ハートの形の輪郭が真ん中から広がって細く消える（どこで拍が来たか分かる）
- 同時に 26 個ほどのハートと、きらめきが 6 個ほど飛び出す。大半は広がった先がハートの形の
  輪郭に並び、残りは中を埋める。出だしは速く、すぐ勢いを失って止まる（ぶわっ）。
  生まれた瞬間は少し大きく膨らむ
- そのあとゆっくり上へ浮きながら、縮んで薄れて消える（すうっ）。薄めるのは終わり際だけ
  （長く半透明にするとクロマキーの緑が透けて濁る）
- 残る長さは拍の間隔に合わせる。速い心拍ほど短く、前の拍のハートが消えかけた所へ次が来る
- 色はピンク・赤・ばら色・白っぽいピンク、ふち取りだけのものも混ぜる
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

from stream_heartbeat.clock import BeatClock

# 1 拍で出るハート（輪郭に並ぶもの・中を埋めるもの）・きらめきの数
BURST_OUTLINE = 20
BURST_INNER = 6
BURST_SPARKLES = 6
# ハートが残る秒（拍の間隔に対する割合と、その上下限）
LIFE_PER_BEAT = 1.6
LIFE_MIN_S = 0.85
LIFE_MAX_S = 1.5
# 飛び出しの速さ（秒）。この 3 倍ほどで広がり切る
BURST_TAU_S = 0.09
# 広がる大きさ（窓の短い辺に対する割合）と、広がりの真ん中を上へ寄せる量（窓の高さに対する割合。
# 下の心拍数の文字に重ねない）
BURST_REACH = 0.34
BURST_LIFT = 0.05
# 拍の頭に広がる輪郭が消えるまでの秒
WAVE_LIFE_S = 0.45
PARTICLE_PALETTE = (
    QColor(255, 92, 138),
    QColor(255, 46, 77),
    QColor(255, 158, 181),
    QColor(255, 214, 226),
    QColor(255, 120, 170),
)
WAVE_COLOR = QColor(255, 196, 214)


def particle_heart(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath(QPointF(cx, cy + 0.50 * s))
    path.cubicTo(cx + 0.95 * s, cy - 0.10 * s, cx + 0.55 * s, cy - 0.95 * s, cx, cy - 0.40 * s)
    path.cubicTo(cx - 0.55 * s, cy - 0.95 * s, cx - 0.95 * s, cy - 0.10 * s, cx, cy + 0.50 * s)
    path.closeSubpath()
    return path


def heart_curve(t: float) -> tuple[float, float]:
    """ハートの形の輪郭の点（t は 0〜2π。画面の右・下が正。幅・高さがおよそ 2 で真ん中が 0）。"""
    x = 16.0 * math.sin(t) ** 3
    y = 13.0 * math.cos(t) - 5.0 * math.cos(2.0 * t) - 2.0 * math.cos(3.0 * t) - math.cos(4.0 * t)
    # 上のくぼみ（y=5）・左右のふくらみ（y≈12）・下の先（y=-17）。上下の真ん中を 0 にそろえる
    return x / 16.0, -(y + 2.5) / 14.5


def life_s(clock: BeatClock) -> float:
    """1 拍ぶんのハートが残る秒。"""
    return max(LIFE_MIN_S, min(LIFE_MAX_S, clock.interval() * LIFE_PER_BEAT))


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
    hearts = BURST_OUTLINE + BURST_INNER
    parts = []
    for k in range(hearts + BURST_SPARKLES):
        sparkle = k >= hearts
        if k < BURST_OUTLINE:
            # 輪郭にほぼ等しい間をあけて並ぶ（形が読める）
            t = 2.0 * math.pi * (k + rng.uniform(-0.25, 0.25)) / BURST_OUTLINE
            reach = rng.uniform(0.93, 1.05)
        elif not sparkle:
            t = rng.uniform(0.0, 2.0 * math.pi)
            reach = rng.uniform(0.25, 0.7)
        else:
            # きらめきは輪郭の少し外へ散る
            t = 2.0 * math.pi * (k - hearts + rng.uniform(0.2, 0.8)) / BURST_SPARKLES
            reach = rng.uniform(1.1, 1.35)
        hx, hy = heart_curve(t)
        parts.append(
            {
                "dx": hx * reach,
                "dy": hy * reach,
                "size": rng.uniform(0.012, 0.02) if sparkle else rng.uniform(0.028, 0.056),
                "rise": rng.uniform(0.10, 0.20),
                "sway": rng.uniform(0.004, 0.012),
                "freq": rng.uniform(0.8, 1.6),
                "phase": rng.uniform(0.0, 2.0 * math.pi),
                "tilt": rng.uniform(-22.0, 22.0),
                "color": float(rng.randrange(len(PARTICLE_PALETTE))),
                "ring": 1.0 if rng.random() < 0.2 else 0.0,
                "sparkle": 1.0 if sparkle else 0.0,
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


def _heart_outline(cx: float, cy: float, r: float) -> QPainterPath:
    steps = 48
    path = QPainterPath()
    for i in range(steps + 1):
        hx, hy = heart_curve(2.0 * math.pi * i / steps)
        point = QPointF(cx + hx * r, cy + hy * r)
        if i == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return path


def _paint_wave(painter: QPainter, center: QPointF, reach: float, age: float, base: float) -> None:
    """拍の頭に真ん中から広がるハートの輪郭。広がりながら細くなって消える（薄めずに細らせる）。"""
    u = age / WAVE_LIFE_S
    if u <= 0.0 or u >= 1.0:
        return
    grow = 1.0 - math.exp(-age / (BURST_TAU_S * 1.4))
    width = reach * 0.045 * (1.0 - u) ** 1.6
    if width < 0.6:
        return
    painter.setOpacity(base * (1.0 - _smooth(0.7, 1.0, u)))
    pen = QPen(WAVE_COLOR, width)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(_heart_outline(center.x(), center.y(), reach * (0.25 + 0.85 * grow)))


def paint_particles(
    painter: QPainter, rect: QRectF, scale: float, clock: BeatClock, now: float
) -> None:
    h = rect.height()
    side = min(rect.width(), h)
    size_k = max(0.3, scale / 0.7)
    reach = side * BURST_REACH * size_k
    center = QPointF(rect.center().x(), rect.center().y() - BURST_LIFT * h)
    life = life_s(clock)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    base_opacity = painter.opacity()
    # 古い拍のハートから描き、新しいものを手前に
    for origin in reversed(beat_origins(clock, now, life)):
        age = now - origin
        if age < 0.0 or age >= life:
            continue
        _paint_wave(painter, center, reach, age, base_opacity)
        u = age / life
        # ぶわっ: 出だしが速く、すぐ止まる
        spread = 1.0 - math.exp(-age / BURST_TAU_S)
        # すうっ: 後半で縮みながら浮き、終わり際に薄れる
        shrink = 1.0 - _smooth(0.4, 1.0, u)
        fade = 1.0 - _smooth(0.65, 1.0, u)
        if fade <= 0.01:
            continue
        painter.setOpacity(base_opacity * fade)
        for part in _spawn(origin):
            size = side * part["size"] * size_k
            x = center.x() + part["dx"] * reach * spread
            x += side * part["sway"] * math.sin(2.0 * math.pi * part["freq"] * age + part["phase"])
            y = center.y() + part["dy"] * reach * spread - side * part["rise"] * u**1.5
            # 生まれた瞬間はぽんと膨らみ、少し大きくなってから落ち着く
            pop = min(1.0, age / 0.07)
            grow = (1.0 - (1.0 - pop) ** 3) * (1.0 + 0.35 * math.exp(-age / 0.1))
            grow *= 0.2 + 0.8 * shrink
            if part["sparkle"] > 0.5:
                twinkle = 0.6 + 0.4 * math.sin(age * 14.0 + part["phase"])
                _draw_sparkle(painter, x, y, size * 1.6 * grow * twinkle)
                continue
            angle = part["tilt"] * (0.5 + 0.5 * spread)
            color = PARTICLE_PALETTE[int(part["color"])]
            _draw_one(painter, x, y, size * grow, angle, color, part["ring"] > 0.5)
    painter.restore()


def _smooth(a: float, b: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)
