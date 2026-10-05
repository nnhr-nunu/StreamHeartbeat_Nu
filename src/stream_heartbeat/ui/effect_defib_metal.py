"""除細動器のパドルの塗り方: 磨いた鋼の棒と円い板、黒いゴムの握り。

鋼は、まわりの部屋（左手前の縦長の窓・右の細い窓・天井の明かり・暗い床）の映り込みで塗る。
明るい所と暗い所の境がくっきりしているほど、硬く磨いた金属に見える。棒は曲がっているので、
短い区間ごとに向きに合わせた映り込みの帯を塗る（帯は向き ANGLE_STEP° ごとに作り置く）。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

# 鋼の色（映り込みの明るさ 0 → 0.5 → 1 → 1.5 で 暗 → 中 → 明 → 白）
STEEL_DARK = (20, 23, 29)
STEEL_MID = (112, 120, 133)
STEEL_LIGHT = (222, 229, 239)
STEEL_EDGE = QColor(12, 14, 18)
# ゴムの握り（つやの少ない黒）
RUBBER_DARK = (10, 11, 14)
RUBBER_LIGHT = (92, 98, 110)
RUBBER_EDGE = QColor(4, 5, 7)
# 見る向きと光の向き（画面の右・下・手前が +）
_LIGHT = (-0.5, -0.62, 0.6)
# 帯を作り置く向きの刻み（度）と、棒の太さの向きに色を置く所（1 が片側の縁、-1 が反対の縁）
ANGLE_STEP = 5
_ACROSS = (
    1.0, 0.97, 0.9, 0.79, 0.65, 0.5, 0.34, 0.19, 0.06, -0.06, -0.19, -0.34, -0.5, -0.65, -0.79,
    -0.9, -0.97, -1.0,
)  # fmt: skip
# 板の縁の厚み（横幅に対する割合）
THICK = 0.2
# 板の外側の面の上下の色（上は明るい天井、真ん中で地平線のようにくっきり暗くなり、下は暗い床）
FACE_STOPS = (
    (0.0, (128, 136, 149)),
    (0.3, (184, 192, 204)),
    (0.47, (226, 232, 241)),
    (0.5, (64, 70, 81)),
    (0.72, (30, 34, 41)),
    (0.88, (88, 95, 108)),
    (1.0, (36, 40, 48)),
)
# 窓の映り込み（面を斜めに走るくっきりした帯）: 帯の真ん中の高さ・太さ（縦の半径に対する割合）・濃さ
WINDOWS = ((-0.42, 0.26, 175), (-0.02, 0.07, 130))
WINDOW_SLANT = 0.9


def _unit(x: float, y: float, z: float) -> tuple[float, float, float]:
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    return x / n, y / n, z / n


_L = _unit(*_LIGHT)


def _smooth(e0: float, e1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def _band(x: float, lo: float, hi: float, soft: float) -> float:
    return _smooth(lo - soft, lo + soft, x) * (1.0 - _smooth(hi - soft, hi + soft, x))


def _env(rx: float, ry: float, rz: float) -> float:
    """向き (rx, ry, rz) に映る部屋の明るさ（0 が暗い床、1 を超えると窓の光）。"""
    up = -ry
    az = math.degrees(math.atan2(rx, rz))
    if up >= 0.0:
        # 地平線のすぐ上が明るく、上ほど暗い天井。天井の真ん中に明かり
        v = 0.28 + 0.6 * math.exp(-up / 0.1) + 0.8 * _band(up, 0.55, 0.92, 0.05)
    else:
        v = 0.06 + 0.1 * math.exp(up / 0.08)
    if -0.35 < up < 0.95:
        v += 1.0 * _band(az, -64.0, -38.0, 3.0) + 0.55 * _band(az, 47.0, 59.0, 2.5)
    return v


def _reflect(nx: float, ny: float, nz: float) -> tuple[float, float, float]:
    """手前から見たとき、向き (nx, ny, nz) の面に映る向き。"""
    return 2.0 * nz * nx, 2.0 * nz * ny, 2.0 * nz * nz - 1.0


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(*(int(round(x + (y - x) * t)) for x, y in zip(a, b)))


def steel(v: float) -> QColor:
    """映り込みの明るさ v の鋼の色。"""
    if v <= 0.5:
        return _mix(STEEL_DARK, STEEL_MID, v / 0.5)
    if v <= 1.0:
        return _mix(STEEL_MID, STEEL_LIGHT, (v - 0.5) / 0.5)
    return _mix(STEEL_LIGHT, (255, 255, 255), (v - 1.0) / 0.5)


def _across(angle_bin: int) -> list[tuple[float, float, float, float]]:
    """太さの向きが angle_bin の棒の、帯の位置（0〜1）と面の向き。"""
    ang = math.radians(angle_bin * ANGLE_STEP)
    nx, ny = math.cos(ang), math.sin(ang)
    out: list[tuple[float, float, float, float]] = []
    for c in _ACROSS:
        nz = math.sqrt(max(0.0, 1.0 - c * c))
        out.append(((1.0 - c) * 0.5, nx * c, ny * c, nz))
    return out


@lru_cache(maxsize=256)
def chrome_stops(angle_bin: int) -> tuple[tuple[float, QColor], ...]:
    """磨いた鋼の棒の、太さの向きの色の帯。"""
    return tuple((u, steel(_env(*_reflect(nx, ny, nz)))) for u, nx, ny, nz in _across(angle_bin))


@lru_cache(maxsize=256)
def rubber_stops(angle_bin: int) -> tuple[tuple[float, QColor], ...]:
    """ゴムの握りの、太さの向きの色の帯（光の側がぼんやり明るく、細い弱いつや）。"""
    out: list[tuple[float, QColor]] = []
    for u, nx, ny, nz in _across(angle_bin):
        diffuse = max(0.0, nx * _L[0] + ny * _L[1] + nz * _L[2])
        rx, ry, rz = _reflect(nx, ny, nz)
        gloss = max(0.0, rx * _L[0] + ry * _L[1] + rz * _L[2]) ** 14
        out.append((u, _mix(RUBBER_DARK, RUBBER_LIGHT, 0.12 + 0.4 * diffuse + 0.55 * gloss)))
    return tuple(out)


def _normals(pts: list[QPointF]) -> list[QPointF]:
    out: list[QPointF] = []
    for i in range(len(pts)):
        a = pts[max(0, i - 1)]
        b = pts[min(len(pts) - 1, i + 1)]
        tx, ty = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(tx, ty) or 1.0
        out.append(QPointF(-ty / length, tx / length))
    return out


def tube_edges(pts: list[QPointF], w0: float, w1: float) -> tuple[list[QPointF], list[QPointF]]:
    """線 pts を太さ w0 → w1 の帯にしたときの、両側の縁。"""
    normals = _normals(pts)
    last = max(1, len(pts) - 1)
    left: list[QPointF] = []
    right: list[QPointF] = []
    for i, (p, nrm) in enumerate(zip(pts, normals)):
        half = (w0 + (w1 - w0) * i / last) * 0.5
        left.append(p + nrm * half)
        right.append(p - nrm * half)
    return left, right


def shaded_tube(
    painter: QPainter,
    pts: list[QPointF],
    w0: float,
    w1: float,
    stops: Callable[[int], tuple[tuple[float, QColor], ...]],
    edge: QColor,
) -> None:
    """線 pts に沿った丸い棒（太さ w0 → w1）を、区間の向きに合わせた帯で塗り、縁を細く締める。"""
    if len(pts) < 2:
        return
    left, right = tube_edges(pts, w0, w1)
    bins: list[int] = []
    for i in range(len(pts) - 1):
        a, b = left[i] + left[i + 1], right[i] + right[i + 1]
        angle = math.degrees(math.atan2(a.y() - b.y(), a.x() - b.x()))
        bins.append(int(round(angle / ANGLE_STEP)) % (360 // ANGLE_STEP))
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    # 区間どうしの継ぎ目に隙間を出さないよう、面はぼかさずに塗り、縁の線でなめらかにする。
    # 同じ向きの区間が続く所は 1 枚にまとめて塗る
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    i = 0
    while i < len(bins):
        j = i
        while j + 1 < len(bins) and bins[j + 1] == bins[i]:
            j += 1
        k = (i + j + 1) // 2
        grad = QLinearGradient(left[k], right[k])
        grad.setStops(list(stops(bins[i])))
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(QPolygonF(left[i : j + 2] + right[i : j + 2][::-1]))
        i = j + 1
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(edge, max(1.0, min(w0, w1) * 0.07))
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolyline(QPolygonF(left))
    painter.drawPolyline(QPolygonF(right))
    painter.restore()


def paint_ribs(painter: QPainter, pts: list[QPointF], w0: float, w1: float, every: float) -> None:
    """ゴムの握りの滑り止めの溝（every px ごと）。"""
    left, right = tube_edges(pts, w0 * 0.86, w1 * 0.86)
    dark = QPen(QColor(0, 0, 0, 150), max(1.0, w0 * 0.07))
    light = QPen(QColor(150, 158, 172, 55), max(1.0, w0 * 0.05))
    run = 0.0
    for i in range(1, len(pts)):
        run += math.hypot(pts[i].x() - pts[i - 1].x(), pts[i].y() - pts[i - 1].y())
        if run < every:
            continue
        run = 0.0
        a, b = left[i], right[i]
        shift = (pts[i] - pts[i - 1]) * 0.35
        painter.setPen(dark)
        painter.drawLine(a, b)
        painter.setPen(light)
        painter.drawLine(a + shift, b + shift)


def paint_steel_disc(
    painter: QPainter, center: QPointF, tilt: float, outward: float, radius: float, squash: float
) -> None:
    """斜めから見た、磨いた鋼の円い板（外側の面と、心臓の側に見える縁の厚み）。

    板の絵は大きさと向きが同じなら変わらないので、作り置いた絵を置く（毎コマ描くと重い）。
    """
    device = painter.device()
    dpr = device.devicePixelRatioF() if device is not None else 1.0
    image = _disc_image(round(radius * 4.0) / 4.0, tilt, outward, squash, dpr)
    side = image.width() / dpr
    painter.drawImage(QRectF(center.x() - side * 0.5, center.y() - side * 0.5, side, side), image)


@lru_cache(maxsize=8)
def _disc_image(radius: float, tilt: float, outward: float, squash: float, dpr: float) -> QImage:
    side = math.ceil((radius * 2.0 + 6.0) * dpr)
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(dpr, dpr)
    painter.translate(side / dpr * 0.5, side / dpr * 0.5)
    painter.rotate(tilt)
    _draw_disc(painter, outward, radius, squash)
    painter.end()
    image.setDevicePixelRatio(dpr)
    return image


def _draw_disc(painter: QPainter, outward: float, radius: float, squash: float) -> None:
    """板の真ん中を原点に、傾きを付けた座標で板を描く。"""
    rx, ry = radius * squash, radius
    back = QPointF(-outward * rx * THICK, 0.0)
    # 縁の厚み: 横に寝た円柱の帯（上が明るく、真ん中でくっきり暗くなる）
    rim = QPainterPath()
    rim.addEllipse(back, rx, ry)
    rim.addRect(QRectF(min(back.x(), 0.0), -ry, abs(back.x()), ry * 2.0))
    rim = rim.simplified()
    grad = QLinearGradient(QPointF(0.0, -ry), QPointF(0.0, ry))
    grad.setStops(list(chrome_stops(270 // ANGLE_STEP)))
    painter.setPen(QPen(STEEL_EDGE, max(1.0, rx * 0.05)))
    painter.setBrush(QBrush(grad))
    painter.drawPath(rim)
    # 心臓の赤が縁に薄く映る
    painter.setPen(Qt.PenStyle.NoPen)
    red = QLinearGradient(QPointF(back.x() - outward * rx, 0.0), QPointF(0.0, 0.0))
    red.setColorAt(0.0, QColor(150, 30, 30, 90))
    red.setColorAt(1.0, QColor(150, 30, 30, 0))
    painter.setBrush(QBrush(red))
    painter.drawPath(rim)
    # 外側の面: 上下の映り込み → 斜めに走る窓の映り込み → 回しながら磨いた細かな筋
    face = QLinearGradient(QPointF(0.0, -ry), QPointF(0.0, ry))
    for u, rgb in FACE_STOPS:
        face.setColorAt(u, QColor(*rgb))
    painter.setBrush(QBrush(face))
    painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
    disc = QPainterPath()
    disc.addEllipse(QPointF(0.0, 0.0), rx, ry)
    slant = WINDOW_SLANT * outward
    for middle, thick, alpha in WINDOWS:
        top, bottom = (middle - thick * 0.5) * ry, (middle + thick * 0.5) * ry
        band = QPainterPath()
        band.addPolygon(
            QPolygonF(
                [
                    QPointF(-rx * 2.0, top - slant * rx * 2.0),
                    QPointF(rx * 2.0, top + slant * rx * 2.0),
                    QPointF(rx * 2.0, bottom + slant * rx * 2.0),
                    QPointF(-rx * 2.0, bottom - slant * rx * 2.0),
                ]
            )
        )
        # 帯の縁はぼかさない（硬い面の映り込みはくっきりしている）。上の縁ほど明るい
        shine = QLinearGradient(QPointF(0.0, top), QPointF(0.0, bottom))
        shine.setColorAt(0.0, QColor(255, 255, 255, alpha))
        shine.setColorAt(1.0, QColor(255, 255, 255, alpha // 3))
        painter.setBrush(QBrush(shine))
        painter.drawPath(band.intersected(disc))
    spun = QConicalGradient(QPointF(0.0, 0.0), 20.0)
    for k in range(9):
        spun.setColorAt(k / 8, QColor(255, 255, 255, 34) if k % 2 == 0 else QColor(0, 0, 0, 30))
    brush = QBrush(spun)
    brush.setTransform(QTransform().scale(squash, 1.0))
    painter.setBrush(brush)
    painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
    # 面の縁の面取り: 光の側（上・外）は明るく、反対は暗く細い線
    inner = QRectF(-rx * 0.86, -ry * 0.86, rx * 1.72, ry * 1.72)
    width = max(1.0, rx * 0.06)
    for color, start in ((QColor(250, 252, 255, 210), 60), (QColor(8, 10, 14, 170), 240)):
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(inner, int(start * 16), int(150 * 16))
    # 光の小さな照り（硬い面ほど小さく鋭い）: にじみの小さい光と、芯のくっきりした点
    glint = QPointF(outward * rx * 0.3, -ry * 0.55)
    halo = QRadialGradient(glint, ry * 0.13)
    halo.setColorAt(0.0, QColor(255, 255, 255, 170))
    halo.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(halo))
    painter.drawEllipse(glint, ry * 0.13, ry * 0.13)
    painter.setBrush(QColor(255, 255, 255, 245))
    painter.drawEllipse(glint, rx * 0.11, ry * 0.035)
    # 外の縁を締める線と、心臓へ向く縁の細い光
    painter.setPen(QPen(STEEL_EDGE, max(1.0, rx * 0.05)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(0.0, 0.0), rx, ry)
    pen = QPen(QColor(244, 247, 252), max(1.0, rx * 0.07))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    box = QRectF(back.x() - rx, -ry, rx * 2.0, ry * 2.0)
    painter.drawArc(box, int((90 if outward > 0 else -90) * 16), int(180 * 16))
