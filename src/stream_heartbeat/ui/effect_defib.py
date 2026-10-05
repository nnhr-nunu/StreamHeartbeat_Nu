"""除細動器: 見ている人（視聴者）が手前から心臓をはさむ、先端の円い金属の板（パドル）2 本。

開胸の手術で心臓に直に当てる型（内部パドル）。スプーンのような円い鋼の板が心臓の左右の側面に当たり、
板の下の縁から短い首で折れて、まっすぐな鋼の棒が窓の下の左右の角（視聴者の側）へ伸びる。
棒の先は黒い樹脂の握り（指を止めるつば・滑り止めの溝）で、窓の外へ抜ける。
右の握りに放電のボタン。ショックの見せ方は effect_defib_shock、金属の塗り方は effect_defib_metal。
レントゲンのスタイルでも同じ見た目で描く（白く写す描き方はしょぼく見えたのでやめた）。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.grip_pose import BODY_RIM, rim_at
from stream_heartbeat.render.model_body import MODEL_HALF, current_weights, model_rim
from stream_heartbeat.ui.effect_defib_metal import (
    RUBBER_EDGE,
    STEEL_EDGE,
    paint_flange,
    paint_ribs,
    paint_steel_disc,
    rubber_stops,
    shaded_tube,
    steel_stops,
)
from stream_heartbeat.ui.effect_defib_shock import (
    SHOCK_S,
    contact_points,
    paint_shock_over,
    paint_shock_under,
)
from stream_heartbeat.ui.effects import BODY_HALF, HeartFrame

# 板の半径（心臓の半径に対する割合）と、板を斜めから見たときの幅の割合
DISC_R = 0.3
DISC_SQUASH = 0.46
# 板が心臓に当たる所（胴の真ん中から見た向き。右から反時計回りの度）と、板の傾き（度）
CONTACTS = ((190.0, 6.0), (-8.0, -6.0))
# 棒の向き（真下から外へ倒す度）。窓の下の左右の角へ抜ける
SHAFT_TILT = 35.0
# 板の下の縁から棒までの首の長さ・棒の長さ（板の半径に対する割合）
NECK_LEN = 0.7
SHAFT_LEN = 2.3
# 太さ（板の半径に対する割合。窓の下ほど手前なので太い）: 棒・握りの先の細い所・握り
SHAFT_W = (0.27, 0.33)
NOSE_W = (0.4, 0.6)
NOSE_LEN = 0.55
HANDLE_W = (0.72, 1.05)
# 指を止めるつば（握りの太さに対する倍率）と厚み（握りの太さに対する割合）
FLANGE_W = 1.5
FLANGE_THICK = 0.3
# びくりで板が外へ跳ねる量（心臓の半径に対する割合）
RECOIL = 0.06
# 心臓の輪郭をなぞる点の数と縮める割合（電流と光を心臓の中だけに描く）
OUTLINE_STEPS = 48
OUTLINE_INSET = 0.9
# Blender の心臓は左下で輪郭がとくに外へはみ出すので、そこ（向き LOWER_LEFT の度）だけ深く縮める
LOWER_LEFT = -140.0
LOWER_LEFT_DENT = 0.2

BUTTON = QColor(236, 164, 38)
BUTTON_RIM = QColor(120, 72, 12)

Disc = tuple[QPointF, float, float]


def paint_defibrillator(
    painter: QPainter,
    rect: QRectF,
    frame: HeartFrame,
    cycle: CardiacCycle,
    *,
    since: float | None,
    kick: float = 0.0,
    model: bool = False,
    opacity: float = 1.0,
    seed: int = 0,
) -> None:
    """心臓をはさむパドルと、ショックの光・電流を描く。

    since はショックからの秒（演出の外なら None）、kick はびくりの揺れ（-1〜1）。
    model は Blender の心臓か（形が縮むので、板も表面と一緒に寄る）。
    seed はショックごとに変える数（電流の走り方が毎回変わる）。
    """
    painter.save()
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    rim, scale = _rim(frame, cycle, model)
    discs = _disc_places(frame, rim, scale, kick)
    radius = frame.radius * DISC_R
    if since is not None and since >= SHOCK_S:
        since = None
    contacts = contact_points(discs, radius, DISC_SQUASH)
    if since is not None:
        outline = _outline(frame, rim, scale, model)
        paint_shock_under(painter, outline, frame, contacts, radius, since, seed)
    for k, (center, tilt, outward) in enumerate(discs):
        _paint_paddle(painter, rect, center, tilt, outward, radius, button=k == 1)
    if since is not None:
        paint_shock_over(painter, discs, contacts, radius, DISC_SQUASH, since, seed)
    painter.restore()


def _rim(frame: HeartFrame, cycle: CardiacCycle, model: bool) -> tuple[tuple[float, ...], float]:
    """胴の輪郭（手で掴むときと同じ形）と、輪郭の長さを画面の px に直す倍率。"""
    rim, half, k = BODY_RIM, BODY_HALF, 1.0 - 0.04 * cycle.squeeze
    weights = current_weights(cycle) if model else None
    if weights is not None:
        # Blender の心臓は形そのものが縮む（輪郭も今の形から出す）
        rim, half, k = model_rim(weights), MODEL_HALF, 1.0
    return rim, frame.half_w / half[0] * k


def _outline(frame: HeartFrame, rim: tuple[float, ...], scale: float, model: bool) -> QPainterPath:
    """画面の上の、心臓の胴の輪郭（光を切り抜く形。少し内側へ縮める）。

    輪郭は形のおおよそで、心臓の外へはみ出す所がある。光が背景ににじまないよう
    OUTLINE_INSET だけ縮め、Blender の心臓では左下をさらに縮める
    （縁の手前で光が消えるのは、内側から光って見えるのと合う）。
    """
    path = QPainterPath()
    dent_at = math.radians(LOWER_LEFT)
    for i in range(OUTLINE_STEPS):
        phi = -math.pi + 2.0 * math.pi * i / OUTLINE_STEPS
        dent = LOWER_LEFT_DENT * max(0.0, math.cos(phi - dent_at)) ** 6 if model else 0.0
        reach = rim_at(phi, rim) * scale * OUTLINE_INSET * (1.0 - dent)
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


def _line(a: QPointF, b: QPointF, n: int) -> list[QPointF]:
    return [a + (b - a) * (i / n) for i in range(n + 1)]


def _paddle_path(
    rect: QRectF, disc: QPointF, tilt: float, outward: float, radius: float
) -> tuple[list[QPointF], list[QPointF], list[QPointF], QPointF]:
    """1 本のパドルの芯: 首と棒・握りの先の細い所・握り（窓の外まで）と、棒の向き。"""
    rx, ry = radius * DISC_SQUASH, radius
    t = math.radians(tilt)
    down = QPointF(-math.sin(t), math.cos(t))
    side = QPointF(math.cos(t), math.sin(t))
    # 板の下の縁（スプーンの柄の付け根）
    root = disc + down * (ry * 0.9) + side * (outward * rx * 0.1)
    a = math.radians(SHAFT_TILT)
    axis = QPointF(outward * math.sin(a), math.cos(a))
    # 首: 板の向きに少し下りてから、棒の向きへ折れる
    bend = root + down * (radius * NECK_LEN * 0.55) + axis * (radius * NECK_LEN * 0.6)
    neck = _bezier(
        root, root + down * (radius * NECK_LEN * 0.45), bend - axis * radius * 0.2, bend, 6
    )
    nose_at = bend + axis * (radius * SHAFT_LEN)
    rod = neck + _line(bend, nose_at, 6)[1:]
    grip_at = nose_at + axis * (radius * NOSE_LEN)
    nose = _line(nose_at, grip_at, 3)
    # 握りは窓の外まで真っすぐ伸ばす（握りの端を見せない）
    out_y = rect.bottom() + radius * 3.0
    length = max(radius * 4.0, (out_y - grip_at.y()) / max(0.2, axis.y()))
    grip = _line(grip_at, grip_at + axis * length, 64)
    return rod, nose, grip, axis


def _paint_paddle(
    painter: QPainter,
    rect: QRectF,
    disc: QPointF,
    tilt: float,
    outward: float,
    radius: float,
    *,
    button: bool,
) -> None:
    """1 本のパドル: 棒 → 握りの先 → つば → 握り → 板の順に描く（板が首の付け根を隠す）。"""
    rod, nose, grip, axis = _paddle_path(rect, disc, tilt, outward, radius)
    rod_w = (radius * SHAFT_W[0], radius * SHAFT_W[1])
    nose_w = (radius * NOSE_W[0], radius * NOSE_W[1])
    grip_w = (radius * HANDLE_W[0], radius * HANDLE_W[1])
    flange_w = grip_w[0] * FLANGE_W
    # ステンレスの棒（首から握りの先まで 1 本）
    shaded_tube(painter, rod, *rod_w, steel_stops, STEEL_EDGE)
    # 黒い樹脂: 握りの先の細い所 → 指を止めるつば → 滑り止めの溝の付いた握り
    shaded_tube(painter, nose, *nose_w, rubber_stops, RUBBER_EDGE)
    paint_flange(painter, grip[0], axis, flange_w, grip_w[0] * FLANGE_THICK)
    shaded_tube(painter, grip, *grip_w, rubber_stops, RUBBER_EDGE)
    paint_ribs(painter, grip[4:], *grip_w, every=grip_w[0] * 0.42)
    if button:
        spot = grip[0] + axis * (grip_w[0] * 0.75)
        r = grip_w[0] * 0.24
        cap = QRadialGradient(QPointF(spot.x() - r * 0.3, spot.y() - r * 0.35), r * 1.2)
        cap.setColorAt(0.0, QColor(255, 226, 150))
        cap.setColorAt(0.5, BUTTON)
        cap.setColorAt(1.0, BUTTON_RIM)
        painter.setPen(QPen(BUTTON_RIM, max(1.0, r * 0.25)))
        painter.setBrush(QBrush(cap))
        painter.drawEllipse(spot, r, r)
    paint_steel_disc(painter, disc, tilt, outward, radius, DISC_SQUASH)
