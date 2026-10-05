"""除細動器: 見ている人（視聴者）が手前から心臓をはさむ、先端の円い金属の板（パドル）2 本。

開胸の手術で心臓に直に当てる型（内部パドル）。円い板が心臓の左右の側面に当たり、金属の柄は
外へ出てから窓の下（視聴者の側）へ曲がり、黒い握りが窓の外へ抜ける。右の握りに放電のボタン。
ショックの瞬間は板の間に稲妻が走り、心臓のまわりが一瞬光る（窓全体は光らせず、点滅もしない）。
レントゲンのスタイルでは金属が白く写り、握りの樹脂は淡く透ける。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.grip_pose import BODY_RIM, rim_at
from stream_heartbeat.render.model_body import MODEL_HALF, current_weights, model_rim
from stream_heartbeat.ui.effects import BODY_HALF, HeartFrame

# パドルをレントゲンの写り方で描くスタイル
XRAY_STYLES = frozenset({"xray", "xray_heart"})
# 板の半径（心臓の半径に対する割合）と、板を斜めから見たときの幅の割合
DISC_R = 0.3
DISC_SQUASH = 0.46
# 板が心臓に当たる所（胴の真ん中から見た向き。右から反時計回りの度）と、板の傾き（度）
CONTACTS = ((190.0, -8.0), (-8.0, 8.0))
# 柄の太さ（板の半径に対する割合。窓の下ほど手前なので太い）と、握りの太さ・始まる所（柄の割合）
ROD_W = (0.16, 0.24)
HANDLE_W = (0.5, 0.66)
HANDLE_FROM = 0.56
# ショックの見せ方の長さ（秒）: 稲妻・火花・心臓のまわりの光・板の熱
ARC_S = 0.3
SPARK_S = 0.22
GLOW_S = 0.35
HOT_S = 0.6
# びくりで板が外へ跳ねる量（心臓の半径に対する割合）
RECOIL = 0.06

METAL_LIGHT = QColor(238, 241, 246)
METAL_MID = QColor(166, 172, 182)
METAL_DARK = QColor(96, 102, 114)
GRIP = QColor(34, 38, 46)
GRIP_SHINE = QColor(98, 104, 118, 150)
BUTTON = QColor(236, 164, 38)
BUTTON_RIM = QColor(120, 72, 12)
# レントゲンでの写り方（金属は白く、樹脂は淡く透ける）
XRAY_METAL = QColor(232, 238, 246)
XRAY_METAL_EDGE = QColor(170, 184, 204)
XRAY_GRIP = QColor(130, 140, 154, 70)
ARC_GLOW = QColor(110, 180, 255)
ARC_MID = QColor(170, 218, 255)
SPARK = QColor(255, 238, 196)
WHITE = QColor(255, 255, 255)


def paint_defibrillator(
    painter: QPainter,
    rect: QRectF,
    frame: HeartFrame,
    cycle: CardiacCycle,
    *,
    since: float | None,
    kick: float = 0.0,
    xray: bool = False,
    model: bool = False,
    opacity: float = 1.0,
    clip: QPainterPath | None = None,
) -> None:
    """心臓をはさむパドルと、ショックの稲妻・光を描く。

    since はショックからの秒（演出の外なら None）、kick はびくりの揺れ（-1〜1）。
    model は Blender の心臓か（形が縮むので、板も表面と一緒に寄る）。
    clip を渡すとその中だけに描く（レントゲン1・2 は写真の枠の中だけに写る）。
    """
    painter.save()
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if clip is not None:
        painter.setClipPath(clip)
    discs = _disc_places(frame, cycle, kick, model)
    if since is not None and since < GLOW_S:
        _paint_glow(painter, frame, since)
    radius = frame.radius * DISC_R
    for k, (center, tilt, outward) in enumerate(discs):
        _paint_paddle(painter, rect, frame, center, tilt, outward, radius, xray, button=k == 1)
        if since is not None and since < HOT_S:
            _paint_hot_disc(painter, center, tilt, radius, since)
    if since is not None and since < ARC_S:
        _paint_arcs(painter, discs, radius, since)
    if since is not None and since < SPARK_S:
        _paint_sparks(painter, discs, radius, since)
    painter.restore()


def _disc_places(
    frame: HeartFrame, cycle: CardiacCycle, kick: float, model: bool
) -> list[tuple[QPointF, float, float]]:
    """左右の板の真ん中・傾き（度）・外向き（左 -1 / 右 1）。

    板は胴の輪郭（手で掴むときと同じ形）に当て、心臓の表面と一緒に動く。
    """
    rim, half, k = BODY_RIM, BODY_HALF, 1.0 - 0.04 * cycle.squeeze
    weights = current_weights(cycle) if model else None
    if weights is not None:
        # Blender の心臓は形そのものが縮む（輪郭も今の形から出す）
        rim, half, k = model_rim(weights), MODEL_HALF, 1.0
    # 輪郭の長さ（形の座標）→ 画面の px
    px = frame.half_w / half[0]
    out: list[tuple[QPointF, float, float]] = []
    for deg, tilt in CONTACTS:
        phi = math.atan2(math.sin(math.radians(deg)), math.cos(math.radians(deg)))
        reach = rim_at(phi, rim) * px * k
        outward = -1.0 if math.cos(phi) < 0.0 else 1.0
        # 板は当たる所から少し外に置き、心臓の縁に半分ほど重ねる
        shift = frame.radius * (DISC_R * DISC_SQUASH * 0.35 + RECOIL * kick)
        center = QPointF(
            frame.center.x() + math.cos(phi) * reach + outward * shift,
            frame.center.y() - math.sin(phi) * reach - frame.radius * RECOIL * 0.5 * abs(kick),
        )
        out.append((center, tilt, outward))
    return out


def _bezier(p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, n: int) -> list[QPointF]:
    pts: list[QPointF] = []
    for i in range(n + 1):
        u = i / n
        a, b, c, d = (1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u**2, u**3
        pts.append(
            QPointF(
                a * p0.x() + b * p1.x() + c * p2.x() + d * p3.x(),
                a * p0.y() + b * p1.y() + c * p2.y() + d * p3.y(),
            )
        )
    return pts


def _normals(pts: list[QPointF]) -> list[QPointF]:
    out: list[QPointF] = []
    for i in range(len(pts)):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        tx, ty = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(tx, ty) or 1.0
        out.append(QPointF(-ty / length, tx / length))
    return out


def _tube(pts: list[QPointF], w0: float, w1: float, side: float = 0.0) -> QPolygonF:
    """線 pts を太さ w0 → w1 の帯にする。side は帯を法線の向きへずらす量（太さに対する割合）。"""
    normals = _normals(pts)
    left: list[QPointF] = []
    right: list[QPointF] = []
    last = max(1, len(pts) - 1)
    for i, (p, nrm) in enumerate(zip(pts, normals)):
        half = (w0 + (w1 - w0) * i / last) * 0.5
        mid = p + nrm * (side * half * 2.0)
        left.append(mid + nrm * half)
        right.append(mid - nrm * half)
    return QPolygonF(left + right[::-1])


def _paint_paddle(
    painter: QPainter,
    rect: QRectF,
    frame: HeartFrame,
    disc: QPointF,
    tilt: float,
    outward: float,
    radius: float,
    xray: bool,
    *,
    button: bool,
) -> None:
    """1 本のパドル: 柄 → 握り → 板の順に描く（板が柄の付け根を隠す）。"""
    reach = frame.radius
    start = QPointF(disc.x() + outward * radius * DISC_SQUASH * 0.55, disc.y())
    end = QPointF(
        frame.center.x() + outward * (frame.half_w * 1.25 + reach * 0.55),
        max(rect.bottom() + reach * 0.4, disc.y() + reach * 1.2),
    )
    c1 = QPointF(start.x() + outward * reach * 0.55, start.y() - reach * 0.05)
    c2 = QPointF(end.x(), start.y() + (end.y() - start.y()) * 0.35)
    path = _bezier(start, c1, c2, end, 40)
    # 窓の外まで真っすぐ伸ばす（握りの端を見せない）
    path.append(QPointF(end.x(), end.y() + reach * 2.0))
    cut = int(len(path) * HANDLE_FROM)
    rod, grip = path[: cut + 1], path[cut:]
    rod_w = (radius * ROD_W[0], radius * ROD_W[1])
    grip_w = (radius * HANDLE_W[0], radius * HANDLE_W[1])
    painter.setPen(Qt.PenStyle.NoPen)
    # 金属の柄。明るい側（左上）に細い光を重ねて丸い棒に見せる
    if xray:
        painter.setBrush(XRAY_METAL_EDGE)
        painter.drawPolygon(_tube(rod, rod_w[0] * 1.5, rod_w[1] * 1.5))
        painter.setBrush(XRAY_METAL)
        painter.drawPolygon(_tube(rod, *rod_w))
    else:
        painter.setBrush(METAL_DARK)
        painter.drawPolygon(_tube(rod, *rod_w))
        painter.setBrush(METAL_MID)
        painter.drawPolygon(_tube(rod, rod_w[0] * 0.7, rod_w[1] * 0.7, side=-0.12 * outward))
        painter.setBrush(METAL_LIGHT)
        painter.drawPolygon(_tube(rod, rod_w[0] * 0.22, rod_w[1] * 0.22, side=-0.22 * outward))
    # 握り（樹脂）と、柄との継ぎ目の金属の輪
    if xray:
        painter.setBrush(XRAY_GRIP)
        painter.drawPolygon(_tube(grip, *grip_w))
    else:
        painter.setBrush(GRIP)
        painter.drawPolygon(_tube(grip, *grip_w))
        painter.setBrush(GRIP_SHINE)
        painter.drawPolygon(_tube(grip, grip_w[0] * 0.18, grip_w[1] * 0.18, side=-0.28 * outward))
    collar = grip[:4]
    painter.setBrush(XRAY_METAL if xray else METAL_MID)
    painter.drawPolygon(_tube(collar, grip_w[0] * 1.12, grip_w[0] * 1.12))
    if button and not xray:
        spot = grip[min(len(grip) - 1, len(grip) // 4)]
        r = grip_w[0] * 0.3
        painter.setPen(QPen(BUTTON_RIM, max(1.0, r * 0.25)))
        painter.setBrush(BUTTON)
        painter.drawEllipse(spot, r, r)
        painter.setPen(Qt.PenStyle.NoPen)
    _paint_disc(painter, disc, tilt, outward, radius, xray)


def _paint_disc(
    painter: QPainter, center: QPointF, tilt: float, outward: float, radius: float, xray: bool
) -> None:
    """斜めから見た円い金属の板。心臓へ向く面の縁が明るく光る。"""
    painter.save()
    painter.translate(center)
    painter.rotate(tilt)
    rx, ry = radius * DISC_SQUASH, radius
    if xray:
        glow = QRadialGradient(QPointF(0.0, 0.0), ry * 1.25)
        glow.setColorAt(
            0.75, QColor(XRAY_METAL_EDGE.red(), XRAY_METAL_EDGE.green(), XRAY_METAL_EDGE.blue(), 90)
        )
        glow.setColorAt(
            1.0, QColor(XRAY_METAL_EDGE.red(), XRAY_METAL_EDGE.green(), XRAY_METAL_EDGE.blue(), 0)
        )
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(0.0, 0.0), rx * 1.25, ry * 1.25)
        painter.setBrush(XRAY_METAL)
        painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
        painter.restore()
        return
    # 縁（厚み）→ 外側の面（ふくらんだ裏）→ 光
    painter.setBrush(METAL_DARK)
    painter.drawEllipse(QPointF(-outward * rx * 0.12, 0.0), rx, ry)
    shade = QRadialGradient(QPointF(outward * rx * 0.25, -ry * 0.35), ry * 1.15)
    shade.setColorAt(0.0, METAL_LIGHT)
    shade.setColorAt(0.55, METAL_MID)
    shade.setColorAt(1.0, METAL_DARK)
    painter.setBrush(QBrush(shade))
    painter.drawEllipse(QPointF(outward * rx * 0.05, 0.0), rx * 0.9, ry * 0.94)
    # 心臓へ向く縁の細い光
    pen = QPen(METAL_LIGHT, max(1.0, rx * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    box = QRectF(-rx * 1.0 - outward * rx * 0.12, -ry, rx * 2.0, ry * 2.0)
    start = 90 if outward > 0 else -90
    painter.drawArc(box, int(start * 16), int(180 * 16))
    painter.restore()


def _paint_hot_disc(
    painter: QPainter, center: QPointF, tilt: float, radius: float, since: float
) -> None:
    """ショックの直後、板が青白く光って冷めていく。"""
    heat = math.exp(-since / 0.15)
    painter.save()
    painter.translate(center)
    painter.rotate(tilt)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ARC_MID.red(), ARC_MID.green(), ARC_MID.blue(), int(150 * heat)))
    painter.drawEllipse(QPointF(0.0, 0.0), radius * DISC_SQUASH, radius)
    painter.restore()


def _paint_glow(painter: QPainter, frame: HeartFrame, since: float) -> None:
    """ショックの瞬間、心臓のまわりだけが一瞬光る（窓の縁までは届かない）。"""
    g = math.exp(-since / 0.08)
    reach = frame.radius * 2.2
    glow = QRadialGradient(frame.center, reach)
    glow.setColorAt(0.0, QColor(215, 235, 255, int(150 * g)))
    glow.setColorAt(0.45, QColor(170, 210, 255, int(70 * g)))
    glow.setColorAt(1.0, QColor(170, 210, 255, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(frame.center, reach, reach)


def _bolt(a: QPointF, b: QPointF, bulge: float, rng: random.Random) -> list[QPointF]:
    """a から b へ走る稲妻の折れ線。bulge だけ横へふくらみ、細かくぎざぎざに折れる。"""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    pts: list[QPointF] = []
    wander = 0.0
    n = 18
    for i in range(n + 1):
        u = i / n
        arch = 4.0 * u * (1.0 - u) * bulge
        if 0 < i < n:
            wander = wander * 0.55 + rng.uniform(-1.0, 1.0) * length * 0.05
        else:
            wander = 0.0
        off = arch + wander
        pts.append(QPointF(a.x() + dx * u + nx * off, a.y() + dy * u + ny * off))
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


def _paint_arcs(
    painter: QPainter, discs: list[tuple[QPointF, float, float]], radius: float, since: float
) -> None:
    """左右の板の間に走る稲妻。コマごとに形が変わり、少しずつ弱まって消える。"""
    fade = 1.0 - since / ARC_S
    (left, _, _), (right, _, _) = discs
    a = QPointF(left.x() + radius * DISC_SQUASH * 0.5, left.y())
    b = QPointF(right.x() - radius * DISC_SQUASH * 0.5, right.y())
    span = math.hypot(b.x() - a.x(), b.y() - a.y())
    tick = int(since * 60.0)
    for k, bulge in enumerate((-0.22, 0.03, 0.24)):
        rng = random.Random(tick * 31 + k)
        flicker = fade * (0.65 + 0.35 * rng.random())
        pts = _bolt(a, b, bulge * span, rng)
        _stroke(painter, pts, _alpha(ARC_GLOW, 70 * flicker), radius * 0.32)
        _stroke(painter, pts, _alpha(ARC_MID, 170 * flicker), radius * 0.1)
        _stroke(painter, pts, _alpha(WHITE, 255 * flicker), max(1.2, radius * 0.03))
        # 枝: 途中から短く横へ逸れる
        for _ in range(2):
            root = pts[rng.randrange(3, len(pts) - 3)]
            angle = rng.uniform(0.0, 2.0 * math.pi)
            tip = QPointF(
                root.x() + math.cos(angle) * span * 0.14, root.y() + math.sin(angle) * span * 0.14
            )
            twig = _bolt(root, tip, 0.0, rng)[:10]
            _stroke(painter, twig, _alpha(ARC_MID, 150 * flicker), radius * 0.05)
            _stroke(painter, twig, _alpha(WHITE, 220 * flicker), max(1.0, radius * 0.02))


def _paint_sparks(
    painter: QPainter, discs: list[tuple[QPointF, float, float]], radius: float, since: float
) -> None:
    """板の縁から外へ飛ぶ火花。"""
    life = 1.0 - since / SPARK_S
    for k, (center, _tilt, outward) in enumerate(discs):
        rng = random.Random(k * 97 + 5)
        for _ in range(10):
            # 心臓とは反対の側へ多く飛ぶ
            angle = rng.uniform(-1.3, 1.3) + (0.0 if outward > 0 else math.pi)
            far = radius * rng.uniform(0.9, 1.7) * (0.6 + 0.6 * (1.0 - life))
            near = far * 0.55
            ux, uy = math.cos(angle), math.sin(angle)
            pen = QPen(_alpha(SPARK, 255 * life), max(1.0, radius * 0.035))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(center.x() + ux * near, center.y() + uy * near),
                QPointF(center.x() + ux * far, center.y() + uy * far),
            )


def _alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out
