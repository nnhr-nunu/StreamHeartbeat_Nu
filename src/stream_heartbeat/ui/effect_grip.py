"""心臓わしづかみ: ふつうの（レントゲンではない）手が、上から鷲の爪のように心臓を掴む絵。

手の座標は心臓の真ん中が原点、心臓の半径が 1、+y が画面の下。
腕は右上から入り、窓の上の外まで伸ばす。
手の甲は心臓の上に乗り、指 4 本は心臓の前を上から下へ這って指先が食い込む。親指は左の縁を回る。
鼓動では心臓に押し返されて揺れ、握ると指が締まり、関節と爪が白くなり、細かく震える。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.ui.effects import HeartFrame, beat_jolt

SKIN = QColor(234, 188, 152)
SKIN_LIGHT = QColor(250, 216, 188)
SKIN_SHADE = QColor(196, 136, 104)
SKIN_DEEP = QColor(160, 100, 76)
OUTLINE = QColor(128, 78, 58, 210)
CREASE = QColor(150, 92, 70, 170)
NAIL = QColor(246, 204, 198)
NAIL_TIP = QColor(253, 242, 236)
NAIL_PRESSED = QColor(252, 238, 232)
CONTACT = QColor(40, 10, 10, 70)


@dataclass(frozen=True)
class Digit:
    base: tuple[float, float]
    tip: tuple[float, float]
    # 中心線のふくらみ（心臓の丸みに沿って外へ弧を描く。+ で右）
    bow: float
    w_base: float
    w_tip: float
    # 関節のしわの位置（付け根 0 〜 先 1）
    joints: tuple[float, ...]


# 人差し指（左）から小指（右）。付け根（拳の山）から指先へ。親指は別
FINGERS = (
    Digit((-0.44, -0.47), (-0.64, 0.36), -0.16, 0.27, 0.23, (0.40, 0.70)),
    Digit((-0.15, -0.44), (-0.19, 0.47), -0.05, 0.29, 0.245, (0.40, 0.70)),
    Digit((0.15, -0.45), (0.26, 0.40), 0.07, 0.28, 0.235, (0.40, 0.70)),
    Digit((0.42, -0.50), (0.58, 0.18), 0.14, 0.24, 0.20, (0.38, 0.68)),
)
THUMB = Digit((-0.64, -1.04), (-0.98, -0.04), -0.10, 0.34, 0.28, (0.55,))
# 手の大きさ（心臓の半径に対して）と置き場所。心臓の下半分が見えるよう少し上に掴む
HAND_SIZE = 0.92
HAND_LIFT = 0.2
# 腕の傾き（右回りの度）。腕は右上から入る
HAND_TILT_DEG = 16.0
SLEEVE = QColor(44, 48, 64)
SLEEVE_LIGHT = QColor(74, 80, 102)


def paint_grip_hand(
    painter: QPainter,
    frame: HeartFrame,
    cycle: CardiacCycle,
    *,
    grip: float,
    time_s: float,
    opacity: float,
) -> None:
    """心臓を握る手を描く（心臓の後に描く）。grip は握る強さ 0〜1。"""
    radius = frame.radius
    if radius <= 1.0:
        return
    g = max(0.0, min(1.0, grip))
    jolt = beat_jolt(cycle.squeeze, cycle.fill)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    painter.translate(frame.center)
    painter.rotate(HAND_TILT_DEG)
    painter.scale(radius * HAND_SIZE, radius * HAND_SIZE)
    painter.translate(0.0, -HAND_LIFT)
    # 鼓動: ドッで心臓に押し返されて手が浮き、指が開く。握ると心臓へ食い込み、力んで細かく震える
    shake = 0.012 * g
    painter.translate(
        shake * math.sin(time_s * 53.0),
        -0.05 * jolt + 0.06 * g + shake * math.cos(time_s * 61.0),
    )
    painter.rotate(-1.4 * jolt)
    # 指の締まり: 握るほど内へ寄り、鼓動で少し押し広げられる
    close = 1.0 - 0.11 * g + 0.04 * jolt
    curl = 0.08 * g

    _paint_arm(painter, g)
    # 親指は手のひら側から回るので、ほかの指より奥
    _paint_digit(painter, _squeezed(THUMB, 1.0 - 0.06 * g, curl * 0.6), g, thumb=True)
    for digit in reversed(FINGERS):
        _paint_digit(painter, _squeezed(digit, close, curl), g)
    painter.restore()


def _squeezed(digit: Digit, close: float, curl: float) -> Digit:
    """握りで指を内へ寄せ、先を少し丸め込む（指先は上へ引き込まれる）。"""
    bx, by = digit.base
    tx, ty = digit.tip
    return Digit(
        (bx * close, by),
        (tx * close, ty - curl),
        digit.bow * close,
        digit.w_base * (1.0 + 0.6 * curl),
        digit.w_tip * (1.0 + 0.6 * curl),
        digit.joints,
    )


# ---------------------------------------------------------------- 手のひらと腕


def _arm_path() -> QPainterPath:
    """手の甲と腕（下の縁は拳の山。指の付け根に隠れる）。"""
    path = QPainterPath()
    path.moveTo(-0.64, -0.40)
    path.quadTo(-0.05, -0.30, 0.60, -0.44)
    path.cubicTo(0.72, -0.72, 0.58, -1.16, 0.42, -1.46)
    path.cubicTo(0.46, -2.10, 0.52, -3.00, 0.58, -6.0)
    path.lineTo(-0.52, -6.0)
    path.cubicTo(-0.46, -3.00, -0.40, -2.10, -0.43, -1.46)
    path.cubicTo(-0.62, -1.20, -0.80, -0.74, -0.64, -0.40)
    path.closeSubpath()
    return path


def _paint_arm(painter: QPainter, g: float) -> None:
    path = _arm_path()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(CONTACT)
    painter.drawPath(path.translated(0.03, 0.04))
    across = QLinearGradient(QPointF(-0.62, 0.0), QPointF(0.66, 0.0))
    across.setColorAt(0.0, SKIN_SHADE)
    across.setColorAt(0.32, SKIN_LIGHT)
    across.setColorAt(0.62, SKIN)
    across.setColorAt(1.0, SKIN_DEEP)
    painter.setPen(QPen(OUTLINE, 0.014))
    painter.setBrush(QBrush(across))
    painter.drawPath(path)
    # 拳の山（付け根の関節）の照り
    painter.setPen(Qt.PenStyle.NoPen)
    for digit in FINGERS:
        knuckle = QPointF(digit.base[0], digit.base[1] - 0.06)
        glow = QRadialGradient(knuckle, 0.16)
        alpha = int(90 + 110 * g)
        glow.setColorAt(0.0, QColor(255, 232, 212, alpha))
        glow.setColorAt(1.0, QColor(255, 232, 212, 0))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(knuckle, 0.16, 0.12)
    # 手の甲の筋（拳の山から手首へ）。力むほど浮く
    tendon = QColor(160, 104, 80, int(50 + 110 * g))
    painter.setPen(QPen(tendon, 0.014, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for digit in FINGERS:
        line = QPainterPath()
        line.moveTo(digit.base[0] * 0.9, digit.base[1] - 0.14)
        line.quadTo(digit.base[0] * 0.7, -1.0, digit.base[0] * 0.35, -1.36)
        painter.drawPath(line)
    # 手首のしわ
    painter.setPen(QPen(CREASE, 0.012))
    wrist = QPainterPath()
    wrist.moveTo(-0.38, -1.52)
    wrist.quadTo(0.0, -1.46, 0.38, -1.52)
    painter.drawPath(wrist)
    _paint_sleeve(painter)


def _paint_sleeve(painter: QPainter) -> None:
    """腕の途中から先は服の袖（腕が長く伸びすぎて見えないように）。"""
    sleeve = QPainterPath()
    sleeve.moveTo(-0.62, -2.30)
    sleeve.quadTo(0.02, -2.18, 0.66, -2.34)
    sleeve.lineTo(0.74, -6.0)
    sleeve.lineTo(-0.66, -6.0)
    sleeve.closeSubpath()
    cloth = QLinearGradient(QPointF(-0.66, 0.0), QPointF(0.74, 0.0))
    cloth.setColorAt(0.0, SLEEVE)
    cloth.setColorAt(0.35, SLEEVE_LIGHT)
    cloth.setColorAt(1.0, SLEEVE)
    painter.setPen(QPen(QColor(24, 26, 36), 0.014))
    painter.setBrush(QBrush(cloth))
    painter.drawPath(sleeve)
    painter.setPen(QPen(QColor(24, 26, 36, 200), 0.012))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    cuff = QPainterPath()
    cuff.moveTo(-0.63, -2.46)
    cuff.quadTo(0.02, -2.34, 0.67, -2.50)
    painter.drawPath(cuff)


# ---------------------------------------------------------------- 指


def _bezier(p0: QPointF, c: QPointF, p1: QPointF, t: float) -> tuple[QPointF, QPointF]:
    """2 次ベジェの点と向き（長さ 1）。"""
    u = 1.0 - t
    point = p0 * (u * u) + c * (2.0 * u * t) + p1 * (t * t)
    d = (c - p0) * (2.0 * u) + (p1 - c) * (2.0 * t)
    length = math.hypot(d.x(), d.y()) or 1.0
    return point, QPointF(d.x() / length, d.y() / length)


def _digit_geometry(digit: Digit) -> tuple[QPolygonF, list[tuple[QPointF, QPointF, float]]]:
    """指の輪郭と、中心線に沿った（点・向き・太さ）。"""
    p0 = QPointF(*digit.base)
    p1 = QPointF(*digit.tip)
    mid = (p0 + p1) * 0.5
    along = p1 - p0
    length = math.hypot(along.x(), along.y()) or 1.0
    normal = QPointF(-along.y() / length, along.x() / length)
    # bow は画面の右を + にそろえる（指が上向きなので左手側の法線は -x）
    sign = 1.0 if normal.x() >= 0.0 else -1.0
    ctrl = mid + normal * (digit.bow * sign)
    spine: list[tuple[QPointF, QPointF, float]] = []
    steps = 18
    for i in range(steps + 1):
        t = i / steps
        point, direction = _bezier(p0, ctrl, p1, t)
        width = digit.w_base + (digit.w_tip - digit.w_base) * t
        # 関節のあたりは少し太い
        for joint in digit.joints:
            width *= 1.0 + 0.05 * math.exp(-(((t - joint) / 0.06) ** 2))
        spine.append((point, direction, width))
    left: list[QPointF] = []
    right: list[QPointF] = []
    for point, direction, width in spine:
        side = QPointF(-direction.y(), direction.x()) * (width * 0.5)
        left.append(point + side)
        right.append(point - side)
    outline = QPolygonF()
    for p in left:
        outline.append(p)
    _cap(outline, spine[-1], forward=True)
    for p in reversed(right):
        outline.append(p)
    _cap(outline, spine[0], forward=False)
    return outline, spine


def _cap(poly: QPolygonF, end: tuple[QPointF, QPointF, float], *, forward: bool) -> None:
    """指先・付け根の丸み（半円）。"""
    point, direction, width = end
    r = width * 0.5
    ahead = direction if forward else direction * -1.0
    side = QPointF(-direction.y(), direction.x())
    if not forward:
        side = side * -1.0
    for k in range(1, 12):
        a = math.pi * k / 12.0
        poly.append(point + side * (r * math.cos(a)) + ahead * (r * math.sin(a)))


def _paint_digit(painter: QPainter, digit: Digit, g: float, *, thumb: bool = False) -> None:
    outline, spine = _digit_geometry(digit)
    path = QPainterPath()
    path.addPolygon(outline)
    path.closeSubpath()
    # 心臓に落ちる影（小さく寄せる。緑の背景に広く落とすとクロマキーで縁が残る）
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(CONTACT)
    painter.drawPath(path.translated(0.02, 0.03))
    # 指先が食い込んだくぼみ
    tip_point, tip_dir, tip_w = spine[-1]
    dent_at = tip_point + tip_dir * (tip_w * 0.35)
    dent = QRadialGradient(dent_at, tip_w * 0.8)
    dent.setColorAt(0.0, QColor(30, 0, 0, int(80 + 70 * g)))
    dent.setColorAt(1.0, QColor(30, 0, 0, 0))
    painter.setBrush(QBrush(dent))
    painter.drawEllipse(dent_at, tip_w * 0.8, tip_w * 0.6)

    # 光は左上から。指の向きによらず画面の左の縁から右の縁へ塗る
    mid_point, mid_dir, mid_w = spine[len(spine) // 2]
    side = QPointF(-mid_dir.y(), mid_dir.x()) * (mid_w * 0.5)
    left, right = mid_point + side, mid_point - side
    if left.x() > right.x():
        left, right = right, left
    across = QLinearGradient(left, right)
    across.setColorAt(0.0, SKIN_SHADE)
    across.setColorAt(0.36, SKIN_LIGHT)
    across.setColorAt(0.62, SKIN)
    across.setColorAt(1.0, SKIN_DEEP)
    painter.setPen(QPen(OUTLINE, 0.013))
    painter.setBrush(QBrush(across))
    painter.drawPath(path)

    for joint in digit.joints:
        _paint_joint(painter, spine, joint, g, double=not thumb and joint < 0.5)
    _paint_nail(painter, spine, g, thumb=thumb)


def _at(spine: list[tuple[QPointF, QPointF, float]], t: float) -> tuple[QPointF, QPointF, float]:
    index = max(0, min(len(spine) - 1, round(t * (len(spine) - 1))))
    return spine[index]


def _paint_joint(
    painter: QPainter,
    spine: list[tuple[QPointF, QPointF, float]],
    t: float,
    g: float,
    *,
    double: bool,
) -> None:
    point, direction, width = _at(spine, t)
    side = QPointF(-direction.y(), direction.x())
    # 握ると関節の出っ張りが白む
    glow = QRadialGradient(point, width * 0.5)
    alpha = int(60 + 120 * g)
    glow.setColorAt(0.0, QColor(255, 236, 222, alpha))
    glow.setColorAt(1.0, QColor(255, 236, 222, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(point, width * 0.5, width * 0.42)
    painter.setPen(QPen(CREASE, 0.011, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    offsets = (-0.022, 0.018) if double else (0.0,)
    for off in offsets:
        center = point + direction * off
        crease = QPainterPath()
        crease.moveTo(center + side * (width * 0.30))
        crease.quadTo(center + direction * 0.028, center - side * (width * 0.30))
        painter.drawPath(crease)


def _paint_nail(
    painter: QPainter,
    spine: list[tuple[QPointF, QPointF, float]],
    g: float,
    *,
    thumb: bool,
) -> None:
    tip_point, tip_dir, tip_w = spine[-1]
    length = tip_w * (0.78 if thumb else 0.72)
    width = tip_w * 0.62
    center = tip_point - tip_dir * (length * 0.5 - tip_w * 0.36)
    angle = math.degrees(math.atan2(tip_dir.y(), tip_dir.x()))
    painter.save()
    painter.translate(center)
    painter.rotate(angle)
    body = QRectF(-length * 0.5, -width * 0.5, length, width)
    # 握ると爪の下の血が引いて白くなる
    base = _mix(NAIL, NAIL_PRESSED, g)
    fill = QLinearGradient(QPointF(-length * 0.5, 0.0), QPointF(length * 0.5, 0.0))
    fill.setColorAt(0.0, _mix(base, SKIN_SHADE, 0.25))
    fill.setColorAt(0.7, base)
    fill.setColorAt(0.84, NAIL_TIP)
    fill.setColorAt(1.0, NAIL_TIP)
    painter.setPen(QPen(QColor(170, 110, 96, 190), 0.009))
    painter.setBrush(QBrush(fill))
    painter.drawRoundedRect(body, width * 0.45, width * 0.45)
    # つや
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 120))
    painter.drawEllipse(QPointF(-length * 0.05, -width * 0.18), length * 0.22, width * 0.1)
    painter.restore()


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )
