"""除細動器のショックの見せ方。

空中を飛ぶ稲妻ではなく、本物の放電に寄せる: 板が心臓に触れた所が一瞬白く光り、電流が心臓の表面を
枝分かれしながら走って、心臓が内側から青白く光る。触れた所からは火花が飛び散って落ち、
少しあとから薄い煙が立ちのぼる（背景がクロマキーの緑のときは、煙が緑に濁るので出さない）。
窓全体は光らせず、点滅もさせない（光るのは心臓と板のまわりだけ）。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

# 見せ方の長さ（秒）: 触れた所の光・表面を走る電流・心臓の光・板の熱・火花・煙
FLASH_S = 0.09
CURRENT_S = 0.18
GLOW_S = 0.32
HOT_S = 0.5
SPARK_S = 0.7
SMOKE_S = 2.4
SHOCK_S = SMOKE_S
# 電流の形を変える速さ（1 秒あたり）
CRACKLE_HZ = 40.0

GLOW = QColor(110, 180, 255)
MID = QColor(176, 220, 255)
WHITE = QColor(255, 255, 255)
SPARK_HOT = (255, 251, 236)
SPARK_WARM = (255, 206, 110)
SPARK_COOL = (255, 128, 36)
SMOKE = QColor(178, 178, 184)

Disc = tuple[QPointF, float, float]


def contact_points(discs: list[Disc], radius: float, squash: float) -> list[QPointF]:
    """左右の板が心臓に触れている所（板の心臓の側の縁）。"""
    return [
        QPointF(center.x() - outward * radius * squash * 0.7, center.y())
        for center, _tilt, outward in discs
    ]


def paint_shock_under(
    painter: QPainter,
    outline: QPainterPath,
    center: QPointF,
    body: float,
    contacts: list[QPointF],
    radius: float,
    since: float,
    seed: int,
) -> None:
    """パドルより奥: 心臓が内側から光り、表面を電流が走る（どちらも心臓の輪郭の中だけ）。

    center は胴の真ん中、body は胴の半分の幅（px）。
    """
    if since >= max(GLOW_S, CURRENT_S):
        return
    painter.save()
    painter.setClipPath(outline, Qt.ClipOperation.IntersectClip)
    if since < GLOW_S:
        _paint_glow(painter, outline, center, body, since)
    if since < CURRENT_S:
        _paint_current(painter, contacts, radius, since, seed)
    painter.restore()


def paint_shock_over(
    painter: QPainter,
    discs: list[Disc],
    contacts: list[QPointF],
    radius: float,
    squash: float,
    since: float,
    seed: int,
    *,
    haze: bool,
) -> None:
    """パドルより手前: 板の熱・触れた所の光・火花・煙。"""
    if since < HOT_S:
        for center, tilt, outward in discs:
            _paint_hot_rim(painter, center, tilt, outward, radius, squash, since)
    if since < FLASH_S:
        for k, point in enumerate(contacts):
            _paint_flash(painter, point, radius, since, seed * 13 + k)
    if since < SPARK_S:
        for k, (point, (_c, _t, outward)) in enumerate(zip(contacts, discs)):
            _paint_sparks(painter, point, outward, radius, since, seed * 7919 + k * 31)
    if haze and since < SMOKE_S:
        for k, point in enumerate(contacts):
            _paint_smoke(painter, point, radius, since, seed * 4241 + k * 17)


def _alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out


def _paint_glow(
    painter: QPainter, outline: QPainterPath, center: QPointF, body: float, since: float
) -> None:
    """電流が通った心臓が、内側から青白く光って引いていく。"""
    g = math.exp(-since / 0.07) * min(1.0, since / 0.012 + 0.3)
    # 輪郭は形のおおよそなので、縁の手前で消す（心臓の外へはみ出して光らない）
    glow = QRadialGradient(center, body)
    glow.setColorAt(0.0, QColor(225, 240, 255, int(120 * g)))
    glow.setColorAt(0.45, QColor(170, 210, 255, int(75 * g)))
    glow.setColorAt(0.8, QColor(140, 195, 255, int(20 * g)))
    glow.setColorAt(1.0, QColor(120, 180, 255, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(glow))
    painter.drawPath(outline)


def _walk(
    start: QPointF, goal: QPointF, steps: int, step: float, rng: random.Random
) -> list[QPointF]:
    """start から goal の方へ、折れ曲がりながら進む電流の筋。"""
    pts = [start]
    p = start
    for _ in range(steps):
        dx, dy = goal.x() - p.x(), goal.y() - p.y()
        heading = math.atan2(dy, dx) + rng.uniform(-0.75, 0.75)
        p = QPointF(p.x() + math.cos(heading) * step, p.y() + math.sin(heading) * step)
        pts.append(p)
    return pts


def _stroke(painter: QPainter, pts: list[QPointF], color: QColor, width: float) -> None:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    painter.drawPath(path)


def _paint_current(
    painter: QPainter, contacts: list[QPointF], radius: float, since: float, seed: int
) -> None:
    """左右の触れた所から、心臓の表面を枝分かれしながら走る電流。形はぱちぱちと変わる。"""
    # 一瞬で広がり、細かくまたたきながら弱まる
    reach = min(1.0, since / 0.035)
    tick = int(since * CRACKLE_HZ)
    rng = random.Random(seed * 101 + tick)
    fade = math.exp(-max(0.0, since - 0.03) / 0.06) * (0.7 + 0.3 * rng.random())
    a, b = contacts
    span = math.hypot(b.x() - a.x(), b.y() - a.y()) or 1.0
    mid = QPointF((a.x() + b.x()) * 0.5, (a.y() + b.y()) * 0.5)
    step = span / 13.0
    for start in (a, b):
        for trunk in range(3):
            goal = QPointF(
                mid.x(), mid.y() + (trunk - 1) * span * 0.32 + rng.uniform(-0.1, 0.1) * span
            )
            pts = _walk(start, goal, max(1, int(7 * reach)), step, rng)
            width = radius * (0.1 if trunk == 1 else 0.07)
            _stroke(painter, pts, _alpha(GLOW, 80 * fade), width * 2.6)
            _stroke(painter, pts, _alpha(MID, 190 * fade), width)
            _stroke(painter, pts, _alpha(WHITE, 255 * fade), max(1.0, width * 0.3))
            # 枝: 筋の途中から横へ短く逸れる
            for root in pts[2:-1]:
                if rng.random() > 0.45:
                    continue
                angle = rng.uniform(0.0, 2.0 * math.pi)
                tip = QPointF(
                    root.x() + math.cos(angle) * step * 3, root.y() + math.sin(angle) * step * 3
                )
                twig = _walk(root, tip, rng.randint(2, 4), step * 0.7, rng)
                _stroke(painter, twig, _alpha(MID, 150 * fade), width * 0.5)
                _stroke(painter, twig, _alpha(WHITE, 210 * fade), max(1.0, width * 0.18))


def _paint_flash(painter: QPainter, point: QPointF, radius: float, since: float, seed: int) -> None:
    """板が心臓に触れた所の、まぶしい放電の光。"""
    rng = random.Random(seed * 53 + int(since * CRACKLE_HZ))
    f = math.exp(-since / 0.03) * (0.75 + 0.25 * rng.random())
    reach = radius * (0.9 + 0.3 * rng.random())
    glow = QRadialGradient(point, reach)
    glow.setColorAt(0.0, QColor(255, 255, 255, int(255 * f)))
    glow.setColorAt(0.18, QColor(225, 242, 255, int(230 * f)))
    glow.setColorAt(0.5, QColor(140, 195, 255, int(90 * f)))
    glow.setColorAt(1.0, QColor(110, 180, 255, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(point, reach, reach)


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
    heat = math.exp(-since / 0.12)
    painter.save()
    painter.translate(center)
    painter.rotate(tilt)
    rx, ry = radius * squash, radius
    hot = QRadialGradient(QPointF(-outward * rx * 0.9, 0.0), ry)
    hot.setColorAt(0.0, _alpha(MID, 200 * heat))
    hot.setColorAt(0.5, _alpha(GLOW, 90 * heat))
    hot.setColorAt(1.0, _alpha(GLOW, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(hot))
    painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
    painter.restore()


def _spark_color(age: float) -> QColor:
    """火花の色（白 → 黄 → 橙と冷めていく）。age は 0〜1。"""
    if age < 0.35:
        a, b, t = SPARK_HOT, SPARK_WARM, age / 0.35
    else:
        a, b, t = SPARK_WARM, SPARK_COOL, (age - 0.35) / 0.65
    return QColor(*(int(x + (y - x) * t) for x, y in zip(a, b)))


def _paint_sparks(
    painter: QPainter, point: QPointF, outward: float, radius: float, since: float, seed: int
) -> None:
    """触れた所から飛び散り、弧を描いて落ちる火花（動いた跡を短い筋で引く）。"""
    rng = random.Random(seed)
    gravity = radius * 34.0
    for _ in range(22):
        life = rng.uniform(0.25, 0.65)
        speed = radius * rng.uniform(4.0, 13.0)
        # 心臓とは反対の側・上へ多く飛ぶ
        angle = rng.uniform(-2.2, 0.35)
        vx = math.cos(angle) * speed * outward
        vy = math.sin(angle) * speed
        delay = rng.uniform(0.0, 0.04)
        t = since - delay
        if t <= 0.0 or t >= life:
            continue
        age = t / life
        tail = max(0.0, t - 0.028)

        def at(s: float, vx: float = vx, vy: float = vy) -> QPointF:
            return QPointF(point.x() + vx * s, point.y() + vy * s + 0.5 * gravity * s * s)

        color = _spark_color(age)
        color.setAlpha(int(255 * (1.0 - age) ** 0.6))
        pen = QPen(color, max(1.2, radius * 0.07 * (1.0 - 0.5 * age)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(at(tail), at(t))
        if age < 0.4:
            # 飛び出したばかりの火花は、頭が白く光る
            head = QPen(_alpha(WHITE, 255 * (1.0 - age / 0.4)), max(1.2, radius * 0.1))
            head.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(head)
            painter.drawPoint(at(t))


def _paint_smoke(painter: QPainter, point: QPointF, radius: float, since: float, seed: int) -> None:
    """触れた所から、少し遅れて立ちのぼる薄い煙。"""
    rng = random.Random(seed)
    painter.setPen(Qt.PenStyle.NoPen)
    for _ in range(7):
        start = rng.uniform(0.05, 0.45)
        life = rng.uniform(1.2, 1.9)
        rise = radius * rng.uniform(1.4, 2.4)
        sway = radius * rng.uniform(0.15, 0.4)
        phase = rng.uniform(0.0, 2.0 * math.pi)
        u = (since - start) / life
        if u <= 0.0 or u >= 1.0:
            continue
        x = point.x() + math.sin(phase + u * 4.0) * sway * u
        y = point.y() - rise * (1.0 - (1.0 - u) ** 2)
        size = radius * (0.18 + 0.75 * u)
        alpha = 46 * math.sin(math.pi * min(1.0, u * 1.6)) * (1.0 - u)
        puff = QRadialGradient(QPointF(x, y), size)
        puff.setColorAt(0.0, _alpha(SMOKE, alpha))
        puff.setColorAt(1.0, _alpha(SMOKE, 0))
        painter.setBrush(QBrush(puff))
        painter.drawEllipse(QPointF(x, y), size, size)
