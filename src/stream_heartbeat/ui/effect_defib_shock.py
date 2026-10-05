"""除細動器のショックの見せ方。

空中を飛ぶ稲妻ではなく、本物の放電に寄せる: 板が心臓に触れた所がまぶしく光ってぱちぱちと揺らぎ、
電流が心臓の表面を枝分かれしながら一面に走って、心臓が内側から青白く光る。
光は足し合わせ（加算）で重ねるので、心臓の模様が透けたまま明るくなる。
窓全体は光らせない。広い面は明滅させない（心臓の光は 1 回ふくらんで引くだけ。
ぱちぱちと変わるのは細い電流の筋と、触れた所の小さな光）。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QTransform,
)

from stream_heartbeat.ui.effects import HeartFrame

# 見せ方の長さ（秒）: 触れた所の光・表面を走る電流・心臓の光・板の熱
FLASH_S = 0.26
CURRENT_S = 0.5
GLOW_S = 0.95
HOT_S = 0.8
SHOCK_S = max(FLASH_S, CURRENT_S, GLOW_S, HOT_S)
# 電流が触れた所から心臓の一面へ広がるまでの秒
SPREAD_S = 0.05
# 電流の形を変える速さ（1 秒あたり）
CRACKLE_HZ = 30.0
# 心臓の光の広がり（胴の半分の幅・高さに対する割合）
GLOW_REACH = 0.95

GLOW = QColor(70, 140, 255)
MID = QColor(120, 185, 255)
WHITE = QColor(255, 255, 255)

Disc = tuple[QPointF, float, float]
_PLUS = QPainter.CompositionMode.CompositionMode_Plus
_OVER = QPainter.CompositionMode.CompositionMode_SourceOver


def contact_points(discs: list[Disc], radius: float, squash: float) -> list[QPointF]:
    """左右の板が心臓に触れている所（板の心臓の側の縁）。"""
    return [
        QPointF(center.x() - outward * radius * squash * 0.7, center.y())
        for center, _tilt, outward in discs
    ]


def glow_level(since: float) -> float:
    """心臓の光の強さ（0〜1）。一瞬でふくらみ、ゆっくり引く。1 回だけで、明滅はしない。"""
    if since < 0.0 or since >= GLOW_S:
        return 0.0
    rise = min(1.0, since / 0.03)
    fall = math.exp(-max(0.0, since - 0.03) / 0.2)
    # 終わりで 0 につなぐ
    return rise * fall * min(1.0, (GLOW_S - since) / 0.2)


def current_level(since: float) -> float:
    """表面を走る電流の強さ（0〜1）。初めの一撃が強く、尾を引いて弱まる。"""
    if since < 0.0 or since >= CURRENT_S:
        return 0.0
    hold = math.exp(-max(0.0, since - SPREAD_S) / 0.14)
    return hold * min(1.0, (CURRENT_S - since) / 0.12)


def paint_shock_under(
    painter: QPainter,
    outline: QPainterPath,
    frame: HeartFrame,
    contacts: list[QPointF],
    radius: float,
    since: float,
    seed: int,
) -> None:
    """パドルより奥: 心臓が内側から光り、表面を電流が走る（どちらも心臓の輪郭の中だけ）。"""
    glow, current = glow_level(since), current_level(since)
    if glow <= 0.0 and current <= 0.0:
        return
    painter.save()
    painter.setClipPath(outline, Qt.ClipOperation.IntersectClip)
    if glow > 0.0:
        _paint_glow(painter, outline, frame, glow)
    if current > 0.0:
        _paint_current(painter, contacts, frame, radius, since, current, seed)
    painter.restore()


def paint_shock_over(
    painter: QPainter,
    discs: list[Disc],
    contacts: list[QPointF],
    radius: float,
    squash: float,
    since: float,
    seed: int,
) -> None:
    """パドルより手前: 板の熱と、触れた所の放電の光。"""
    if since < HOT_S:
        for center, tilt, outward in discs:
            _paint_hot_rim(painter, center, tilt, outward, radius, squash, since)
    if since < FLASH_S:
        for k, (point, (_c, _t, outward)) in enumerate(zip(contacts, discs)):
            _paint_flash(painter, point, outward, radius, since, seed * 13 + k)


def _alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out


def _paint_glow(painter: QPainter, outline: QPainterPath, frame: HeartFrame, g: float) -> None:
    """電流が通った心臓が、内側から青白く光って引いていく。

    まず赤を青白い膜で冷ややかに寄せ、その上に内側からの光を足す（模様は透けたまま明るくなる）。
    輪郭は形のおおよそなので、どちらも縁の手前で薄くする（心臓の外へはみ出して光らない）。
    """
    # 胴の形に合わせた楕円の光（真ん中が明るく、縁の手前で消える）
    shape = QTransform()
    shape.translate(frame.center.x(), frame.center.y())
    shape.scale(frame.half_w * GLOW_REACH, frame.half_h * GLOW_REACH)
    tint = QRadialGradient(QPointF(0.0, 0.0), 1.0)
    tint.setColorAt(0.0, QColor(150, 200, 255, int(150 * g)))
    tint.setColorAt(0.6, QColor(130, 185, 255, int(120 * g)))
    tint.setColorAt(0.85, QColor(110, 170, 255, int(45 * g)))
    tint.setColorAt(1.0, QColor(110, 170, 255, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    brush = QBrush(tint)
    brush.setTransform(shape)
    painter.setBrush(brush)
    painter.drawPath(outline)
    painter.setCompositionMode(_PLUS)
    light = QRadialGradient(QPointF(0.0, 0.0), 1.0)
    light.setColorAt(0.0, QColor(120, 175, 255, int(225 * g)))
    light.setColorAt(0.4, QColor(80, 145, 255, int(175 * g)))
    light.setColorAt(0.75, QColor(50, 110, 255, int(60 * g)))
    light.setColorAt(1.0, QColor(40, 100, 255, 0))
    brush = QBrush(light)
    brush.setTransform(shape)
    painter.setBrush(brush)
    painter.drawPath(outline)
    painter.setCompositionMode(_OVER)


def _walk(
    start: QPointF,
    heading: float,
    goal: QPointF | None,
    steps: int,
    step: float,
    rng: random.Random,
    wander: float,
) -> list[QPointF]:
    """start から折れ曲がりながら進む電流の筋（goal があればその方へ寄っていく）。"""
    pts = [start]
    p = start
    for _ in range(steps):
        if goal is not None:
            heading = math.atan2(goal.y() - p.y(), goal.x() - p.x())
        heading += rng.uniform(-wander, wander)
        p = QPointF(p.x() + math.cos(heading) * step, p.y() + math.sin(heading) * step)
        pts.append(p)
    return pts


def _add(path: QPainterPath, pts: list[QPointF]) -> None:
    path.moveTo(pts[0])
    for p in pts[1:]:
        path.lineTo(p)


def _current_paths(
    contacts: list[QPointF], frame: HeartFrame, reach: float, rng: random.Random
) -> tuple[QPainterPath, QPainterPath, QPainterPath]:
    """左右の触れた所から心臓の一面へ広がる電流の網（太い幹・枝・細い小枝）。"""
    trunks, limbs, twigs = QPainterPath(), QPainterPath(), QPainterPath()
    a, b = contacts
    span = math.hypot(b.x() - a.x(), b.y() - a.y()) or 1.0
    mid = QPointF((a.x() + b.x()) * 0.5, (a.y() + b.y()) * 0.5)
    step = span / 15.0
    tall = frame.half_h
    for start in (a, b):
        for k in range(4):
            # 幹: 向こうの板の方へ、上下に扇のように広がって走る（左右の幹が真ん中で出会う）
            lift = (k - 1.5) / 1.5
            goal = QPointF(
                mid.x() + rng.uniform(-0.12, 0.12) * span,
                mid.y() + lift * tall * 0.8 + rng.uniform(-0.12, 0.12) * tall,
            )
            n = max(1, round((9 if k in (1, 2) else 7) * reach))
            trunk = _walk(start, 0.0, goal, n, step, rng, 0.7)
            _add(trunks, trunk)
            for i in range(1, len(trunk) - 1):
                if rng.random() > 0.4:
                    continue
                root, ahead = trunk[i], trunk[i + 1]
                heading = math.atan2(ahead.y() - root.y(), ahead.x() - root.x())
                heading += rng.choice((-1.0, 1.0)) * rng.uniform(0.5, 1.3)
                limb = _walk(root, heading, None, rng.randint(2, 5), step * 0.75, rng, 0.6)
                _add(limbs, limb)
                for j in range(1, len(limb)):
                    if rng.random() > 0.3:
                        continue
                    turn = heading + rng.choice((-1.0, 1.0)) * rng.uniform(0.6, 1.4)
                    _add(twigs, _walk(limb[j], turn, None, rng.randint(1, 3), step * 0.5, rng, 0.7))
    return trunks, limbs, twigs


def _stroke(painter: QPainter, path: QPainterPath, color: QColor, width: float) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.strokePath(path, pen)


def _paint_current(
    painter: QPainter,
    contacts: list[QPointF],
    frame: HeartFrame,
    radius: float,
    since: float,
    level: float,
    seed: int,
) -> None:
    """左右の触れた所から、心臓の表面を枝分かれしながら一面に走る電流。形はぱちぱちと変わる。"""
    reach = min(1.0, 0.25 + since / SPREAD_S)
    tick = int(since * CRACKLE_HZ)
    rng = random.Random(seed * 101 + tick)
    # 筋の明るさは形が変わるたびに少し揺らぐ（細い筋だけなので、広い面の明滅にはならない）
    f = level * (0.75 + 0.25 * rng.random())
    paths = _current_paths(contacts, frame, reach, rng)
    widths = (radius * 0.1, radius * 0.065, radius * 0.04)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # 外の淡い青 → 青白い筋 → 白い芯の順に重ねる。外の青は上に置いて赤を冷ややかに寄せ
    # （加算だと赤と混ざって紫になる）、筋は加算で重なるほどまぶしくする
    for path, w in zip(paths, widths):
        _stroke(painter, path, _alpha(GLOW, 80 * f), w * 4.0)
    painter.setCompositionMode(_PLUS)
    for path, w in zip(paths, widths):
        _stroke(painter, path, _alpha(MID, 200 * f), w * 1.1)
    painter.setCompositionMode(_OVER)
    for path, w in zip(paths, widths):
        _stroke(painter, path, _alpha(WHITE, 255 * f), max(1.0, w * 0.45))


def _paint_flash(
    painter: QPainter, point: QPointF, outward: float, radius: float, since: float, seed: int
) -> None:
    """板が心臓に触れた所の、まぶしい放電の光。小さな放電の筋がぱちぱちと出ては消える。"""
    tick = int(since * CRACKLE_HZ)
    rng = random.Random(seed * 53 + tick)
    f = min(1.0, since / 0.006 + 0.2) * (
        0.85 * math.exp(-since / 0.06) + 0.25 * math.exp(-since / 0.1)
    )
    f *= (0.82 + 0.18 * rng.random()) * min(1.0, (FLASH_S - since) / 0.08)
    reach = radius * (1.5 + 0.3 * rng.random())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setCompositionMode(_PLUS)
    glow = QRadialGradient(point, reach)
    glow.setColorAt(0.0, QColor(255, 255, 255, int(255 * min(1.0, f))))
    glow.setColorAt(0.12, QColor(215, 235, 255, int(240 * min(1.0, f))))
    glow.setColorAt(0.4, QColor(110, 175, 255, int(120 * f)))
    glow.setColorAt(1.0, QColor(70, 140, 255, 0))
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(point, reach, reach)
    # 小さな放電の筋: 触れた所から心臓の側と上下へ短く跳ねる
    inward = 0.0 if outward < 0 else math.pi
    arcs = QPainterPath()
    for _ in range(7):
        heading = inward + rng.uniform(-1.6, 1.6)
        n = rng.randint(2, 4)
        _add(arcs, _walk(point, heading, None, n, radius * rng.uniform(0.22, 0.34), rng, 0.6))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _stroke(painter, arcs, _alpha(MID, 220 * f), radius * 0.11)
    painter.setCompositionMode(_OVER)
    _stroke(painter, arcs, _alpha(WHITE, 255 * min(1.0, f)), max(1.0, radius * 0.04))
    # 芯: まぶしい白（白い背景の上でも光って見えるよう、加算でなく上に置く）
    core = radius * 0.22 * math.sqrt(min(1.0, f))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_alpha(WHITE, 255 * min(1.0, f * 1.4)))
    painter.drawEllipse(point, core, core)


def _paint_hot_rim(
    painter: QPainter,
    center: QPointF,
    tilt: float,
    outward: float,
    radius: float,
    squash: float,
    since: float,
) -> None:
    """ショックの直後、板の心臓の側の縁が青白く光って冷めていく。"""
    heat = math.exp(-since / 0.18) * min(1.0, (HOT_S - since) / 0.15)
    painter.save()
    painter.translate(center)
    painter.rotate(tilt)
    rx, ry = radius * squash, radius
    hot = QRadialGradient(QPointF(-outward * rx * 0.9, 0.0), ry * 1.1)
    hot.setColorAt(0.0, _alpha(MID, 230 * heat))
    hot.setColorAt(0.5, _alpha(GLOW, 120 * heat))
    hot.setColorAt(1.0, _alpha(GLOW, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(hot))
    painter.setCompositionMode(_PLUS)
    painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
    painter.restore()
