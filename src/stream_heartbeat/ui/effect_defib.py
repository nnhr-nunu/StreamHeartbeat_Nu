"""除細動器: 見ている人（視聴者）が手前から心臓をはさむ、先端の円い金属の板（パドル）2 本。

開胸の手術で心臓に直に当てる型（内部パドル）。磨いた鋼の円い板が心臓の左右の側面に当たり、
鋼の柄は外へ出てから窓の下（視聴者の側）へ曲がり、黒いゴムの握りが窓の外へ抜ける。
右の握りに放電のボタン。ショックの見せ方は effect_defib_shock、金属の塗り方は effect_defib_metal。
レントゲンのスタイルでは金属が白く写り、握りの樹脂は淡く透ける。
"""

from __future__ import annotations

import math

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
from stream_heartbeat.ui.effect_defib_metal import (
    RUBBER_EDGE,
    STEEL_EDGE,
    chrome_stops,
    paint_ribs,
    paint_steel_disc,
    rubber_stops,
    shaded_tube,
    tube_edges,
)
from stream_heartbeat.ui.effect_defib_shock import (
    SHOCK_S,
    contact_points,
    paint_shock_over,
    paint_shock_under,
)
from stream_heartbeat.ui.effects import BODY_HALF, HeartFrame

# パドルをレントゲンの写り方で描くスタイル
XRAY_STYLES = frozenset({"xray", "xray_heart"})
# 板の半径（心臓の半径に対する割合）と、板を斜めから見たときの幅の割合
DISC_R = 0.3
DISC_SQUASH = 0.46
# 板が心臓に当たる所（胴の真ん中から見た向き。右から反時計回りの度）と、板の傾き（度）
CONTACTS = ((190.0, -8.0), (-8.0, 8.0))
# 柄の太さ（板の半径に対する割合。窓の下ほど手前なので太い）と、握りの太さ・始まる所（柄の割合）
ROD_W = (0.19, 0.27)
HANDLE_W = (0.5, 0.66)
HANDLE_FROM = 0.56
# 柄と握りの継ぎ目の金属の輪（握りの太さに対する倍率）
COLLAR_W = 1.12
# びくりで板が外へ跳ねる量（心臓の半径に対する割合）
RECOIL = 0.06
# 心臓の輪郭をなぞる点の数（電流と光を心臓の中だけに描く）
OUTLINE_STEPS = 48

BUTTON = QColor(236, 164, 38)
BUTTON_RIM = QColor(120, 72, 12)
# レントゲンでの写り方（金属は白く、樹脂は淡く透ける）
XRAY_METAL = QColor(232, 238, 246)
XRAY_METAL_EDGE = QColor(170, 184, 204)
XRAY_GRIP = QColor(130, 140, 154, 70)

Disc = tuple[QPointF, float, float]


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
    seed: int = 0,
    haze: bool = False,
) -> None:
    """心臓をはさむパドルと、ショックの光・電流・火花を描く。

    since はショックからの秒（演出の外なら None）、kick はびくりの揺れ（-1〜1）。
    model は Blender の心臓か（形が縮むので、板も表面と一緒に寄る）。
    clip を渡すとその中だけに描く（レントゲン1・2 は写真の枠の中だけに写る）。
    seed はショックごとに変える数（火花の散り方が毎回変わる）。haze は煙を出すか。
    """
    painter.save()
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if clip is not None:
        painter.setClipPath(clip)
    rim, scale = _rim(frame, cycle, model)
    discs = _disc_places(frame, rim, scale, kick)
    radius = frame.radius * DISC_R
    if since is not None and since >= SHOCK_S:
        since = None
    contacts = contact_points(discs, radius, DISC_SQUASH)
    if since is not None:
        outline = _outline(frame, rim, scale)
        body = frame.half_w
        paint_shock_under(painter, outline, frame.center, body, contacts, radius, since, seed)
    for k, (center, tilt, outward) in enumerate(discs):
        _paint_paddle(painter, rect, frame, center, tilt, outward, radius, xray, button=k == 1)
    if since is not None:
        paint_shock_over(
            painter, discs, contacts, radius, DISC_SQUASH, since, seed, haze=haze and not xray
        )
    painter.restore()


def _rim(frame: HeartFrame, cycle: CardiacCycle, model: bool) -> tuple[tuple[float, ...], float]:
    """胴の輪郭（手で掴むときと同じ形）と、輪郭の長さを画面の px に直す倍率。"""
    rim, half, k = BODY_RIM, BODY_HALF, 1.0 - 0.04 * cycle.squeeze
    weights = current_weights(cycle) if model else None
    if weights is not None:
        # Blender の心臓は形そのものが縮む（輪郭も今の形から出す）
        rim, half, k = model_rim(weights), MODEL_HALF, 1.0
    return rim, frame.half_w / half[0] * k


def _outline(frame: HeartFrame, rim: tuple[float, ...], scale: float) -> QPainterPath:
    """画面の上の、心臓の胴の輪郭。"""
    path = QPainterPath()
    for i in range(OUTLINE_STEPS):
        phi = -math.pi + 2.0 * math.pi * i / OUTLINE_STEPS
        reach = rim_at(phi, rim) * scale
        p = QPointF(
            frame.center.x() + math.cos(phi) * reach, frame.center.y() - math.sin(phi) * reach
        )
        if i == 0:
            path.moveTo(p)
        else:
            path.lineTo(p)
    path.closeSubpath()
    return path


def _disc_places(
    frame: HeartFrame, rim: tuple[float, ...], scale: float, kick: float
) -> list[Disc]:
    """左右の板の真ん中・傾き（度）・外向き（左 -1 / 右 1）。

    板は胴の輪郭に当て、心臓の表面と一緒に動く。
    """
    out: list[Disc] = []
    for deg, tilt in CONTACTS:
        phi = math.atan2(math.sin(math.radians(deg)), math.cos(math.radians(deg)))
        reach = rim_at(phi, rim) * scale
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


def _band(pts: list[QPointF], w0: float, w1: float) -> QPolygonF:
    left, right = tube_edges(pts, w0, w1)
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
    """1 本のパドル: 柄 → 握り → 継ぎ目の輪 → 板の順に描く（板が柄の付け根を隠す）。"""
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
    collar = grip[:4]
    if xray:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(XRAY_METAL_EDGE)
        painter.drawPolygon(_band(rod, rod_w[0] * 1.5, rod_w[1] * 1.5))
        painter.setBrush(XRAY_METAL)
        painter.drawPolygon(_band(rod, *rod_w))
        painter.setBrush(XRAY_GRIP)
        painter.drawPolygon(_band(grip, *grip_w))
        painter.setBrush(XRAY_METAL)
        painter.drawPolygon(_band(collar, grip_w[0] * COLLAR_W, grip_w[0] * COLLAR_W))
        _paint_xray_disc(painter, disc, tilt, radius)
        return
    # 磨いた鋼の柄
    shaded_tube(painter, rod, *rod_w, chrome_stops, STEEL_EDGE)
    # ゴムの握り（滑り止めの溝）と、柄との継ぎ目の鋼の輪
    shaded_tube(painter, grip, *grip_w, rubber_stops, RUBBER_EDGE)
    paint_ribs(painter, grip[3:], *grip_w, every=grip_w[0] * 0.42)
    shaded_tube(
        painter, collar, grip_w[0] * COLLAR_W, grip_w[0] * COLLAR_W, chrome_stops, STEEL_EDGE
    )
    if button:
        spot = grip[min(len(grip) - 1, len(grip) // 4)]
        r = grip_w[0] * 0.3
        cap = QRadialGradient(QPointF(spot.x() - r * 0.3, spot.y() - r * 0.35), r * 1.2)
        cap.setColorAt(0.0, QColor(255, 226, 150))
        cap.setColorAt(0.5, BUTTON)
        cap.setColorAt(1.0, BUTTON_RIM)
        painter.setPen(QPen(BUTTON_RIM, max(1.0, r * 0.25)))
        painter.setBrush(QBrush(cap))
        painter.drawEllipse(spot, r, r)
    paint_steel_disc(painter, disc, tilt, outward, radius, DISC_SQUASH)


def _paint_xray_disc(painter: QPainter, center: QPointF, tilt: float, radius: float) -> None:
    """レントゲンに白く写る円い金属の板（縁がにじむ）。"""
    painter.save()
    painter.translate(center)
    painter.rotate(tilt)
    rx, ry = radius * DISC_SQUASH, radius
    edge = XRAY_METAL_EDGE
    glow = QRadialGradient(QPointF(0.0, 0.0), ry * 1.25)
    glow.setColorAt(0.75, QColor(edge.red(), edge.green(), edge.blue(), 90))
    glow.setColorAt(1.0, QColor(edge.red(), edge.green(), edge.blue(), 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(QPointF(0.0, 0.0), rx * 1.25, ry * 1.25)
    painter.setBrush(XRAY_METAL)
    painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
    painter.restore()
