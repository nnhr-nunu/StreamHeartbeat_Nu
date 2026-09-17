"""心エコー（心尖部四腔像）。扇の中に白黒の断層を描く。測定値は出さない。

上が心尖、下が心房。画面右が左心系。左右の室が縮み、房室弁が開閉し、
組織のスペックルは壁と一緒に内側へ寄る。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QTransform,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.ui.noise_images import speckle_tile, tissue_tile

ECHO_BG = QColor(4, 5, 8)
ECHO_MYO = QColor(126, 136, 148)
ECHO_BRIGHT = QColor(226, 232, 240)
ECHO_CAVITY = QColor(3, 4, 6)
ECHO_VALVE = QColor(240, 244, 250)
HALF_ANGLE_DEG = 40.0


def paint_echo(painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle) -> None:
    cx = rect.center().x()
    side = min(rect.width(), rect.height())
    size = side * 0.42 * scale / 0.7 * 0.7
    apex = QPointF(cx, rect.center().y() - side * 0.42)
    radius = side * 0.86
    sector = _sector_path(apex, radius, HALF_ANGLE_DEG)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ECHO_BG)
    painter.drawPath(sector)
    painter.setClipPath(sector)

    frame = int(cycle.age * 30.0)
    seed = frame % 3

    # 背景の弱いノイズ。近距離ほど濃い
    depth = QLinearGradient(apex, QPointF(apex.x(), apex.y() + radius))
    depth.setColorAt(0.0, QColor(26, 30, 38))
    depth.setColorAt(0.30, QColor(10, 12, 16))
    depth.setColorAt(1.0, QColor(5, 6, 9))
    painter.setBrush(depth)
    painter.drawPath(sector)
    bg_noise = QBrush(speckle_tile(seed))
    bg_noise.setTransform(QTransform().translate((frame * 11) % 256, (frame * 3) % 256))
    painter.setOpacity(0.22)
    painter.setBrush(bg_noise)
    painter.drawPath(sector)
    painter.setOpacity(1.0)

    _draw_heart_section(painter, cx, apex.y() + radius * 0.22, size, cycle, seed, frame)

    # 近距離の反響
    near = QRadialGradient(apex, radius * 0.18)
    near.setColorAt(0.0, QColor(210, 218, 230, 90))
    near.setColorAt(1.0, QColor(210, 218, 230, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(near)
    painter.drawPath(sector)
    painter.setClipping(False)

    painter.setPen(QPen(QColor(40, 46, 56), max(1.0, side * 0.003)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(sector)

    # 深さ目盛り（数値なし）
    painter.setPen(QPen(QColor(120, 130, 146, 150), max(1.0, side * 0.002)))
    tick_x = apex.x() + radius * math.sin(math.radians(HALF_ANGLE_DEG)) + side * 0.03
    for i in range(1, 10):
        y = apex.y() + radius * i / 10.0
        length = side * (0.022 if i % 5 == 0 else 0.011)
        painter.drawLine(QPointF(tick_x, y), QPointF(tick_x + length, y))
    painter.restore()


def _draw_heart_section(
    painter: QPainter,
    cx: float,
    top_y: float,
    s: float,
    cycle: CardiacCycle,
    seed: int,
    frame: int,
) -> None:
    sq = cycle.squeeze
    fill = cycle.fill
    vent = 1.0 - 0.30 * sq
    atr = 1.0 + 0.14 * sq - 0.10 * fill

    # 室の長さは縮んで短く、心尖はほぼ動かない
    v_len = s * 1.10 * (1.0 - 0.10 * sq)
    valve_y = top_y + v_len
    center = QPointF(cx, top_y + s * 0.62)

    septum = s * 0.07 + s * 0.03 * sq
    lv_w = s * 0.36 * vent
    rv_w = s * 0.27 * vent
    lv = _chamber(cx + septum * 0.5 + lv_w, top_y + v_len * 0.56, lv_w, v_len * 0.46, -4)
    rv = _chamber(cx - septum * 0.5 - rv_w, top_y + v_len * 0.62, rv_w, v_len * 0.37, 6)
    la_w = s * 0.34 * atr
    ra_w = s * 0.32 * atr
    la = _chamber(
        cx + s * 0.03 + la_w, valve_y + s * 0.06 + s * 0.34 * atr, la_w, s * 0.34 * atr, 0
    )
    ra = _chamber(
        cx - s * 0.03 - ra_w, valve_y + s * 0.06 + s * 0.32 * atr, ra_w, s * 0.32 * atr, 0
    )
    chambers = QPainterPath()
    for chamber in (lv, rv, la, ra):
        chambers = chambers.united(chamber)

    # 心筋。外形はひとつの丸い輪郭で、腔を抜いたところが壁になる
    wall = _outline(cx, top_y, s, v_len, atr, sq)
    tissue = wall.subtracted(chambers)

    painter.setPen(Qt.PenStyle.NoPen)
    tissue_brush = QBrush(tissue_tile(seed))
    shrink = 1.0 - 0.08 * sq
    t = QTransform()
    t.translate(center.x(), center.y())
    t.scale(shrink, shrink)
    t.translate(-center.x() + (frame * 5) % 64, -center.y())
    tissue_brush.setTransform(t)
    painter.setBrush(tissue_brush)
    painter.drawPath(tissue)

    # 深さで減衰し、心尖側の壁は明るい
    shade = QLinearGradient(QPointF(cx, top_y - s * 0.2), QPointF(cx, valve_y + s * 0.9))
    shade.setColorAt(0.0, QColor(255, 255, 255, 40))
    shade.setColorAt(0.5, QColor(0, 0, 0, 0))
    shade.setColorAt(1.0, QColor(0, 0, 0, 120))
    painter.setBrush(shade)
    painter.drawPath(tissue)

    # 心膜の明るい縁
    peri = QPen(QColor(215, 222, 232, 150), max(1.5, s * 0.02))
    painter.setPen(peri)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(wall)
    painter.setPen(Qt.PenStyle.NoPen)

    # 腔の中。血液は黒に近く、僅かな粒。壁との境目はにじむ
    painter.setBrush(ECHO_CAVITY)
    painter.drawPath(chambers)
    for width, alpha in ((0.05, 60), (0.03, 90), (0.015, 130)):
        blur = QPen(QColor(ECHO_MYO.red(), ECHO_MYO.green(), ECHO_MYO.blue(), alpha), s * width)
        painter.setPen(blur)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(chambers)
    painter.setPen(Qt.PenStyle.NoPen)
    blood = QBrush(speckle_tile((seed + 1) % 3))
    blood.setTransform(QTransform().translate((frame * 9) % 256, (frame * 4) % 256))
    painter.setOpacity(0.16 + 0.10 * cycle.eject)
    painter.setBrush(blood)
    painter.drawPath(chambers)
    painter.setOpacity(1.0)

    # 中隔の明るい芯
    septum_pen = QPen(QColor(200, 208, 220, 110), max(1.5, s * 0.02))
    septum_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(septum_pen)
    sp = QPainterPath(QPointF(cx - s * 0.02, top_y + v_len * 0.20))
    sp.cubicTo(
        cx + s * 0.02,
        top_y + v_len * 0.5,
        cx - s * 0.01,
        top_y + v_len * 0.8,
        cx,
        valve_y - s * 0.02,
    )
    painter.drawPath(sp)

    # 房室弁。充満で開いて室側へ倒れ、収縮で閉じて一線になる
    open_amt = max(0.0, min(1.0, fill * 1.5 - sq * 0.9))
    _valve(painter, cx + septum * 0.5 + lv_w, valve_y + s * 0.02, lv_w * 1.6, open_amt, s)
    _valve(painter, cx - septum * 0.5 - rv_w, valve_y + s * 0.05, rv_w * 1.6, open_amt, s)

    # 乳頭筋・肉柱
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(196, 204, 216, 200))
    lv_cx = cx + septum * 0.5 + lv_w
    painter.drawEllipse(QPointF(lv_cx + lv_w * 0.62, top_y + v_len * 0.66), s * 0.05, s * 0.07)
    painter.drawEllipse(QPointF(lv_cx - lv_w * 0.35, top_y + v_len * 0.72), s * 0.04, s * 0.06)
    rv_cx = cx - septum * 0.5 - rv_w
    for i in range(6):
        px = rv_cx - rv_w * (0.55 + 0.25 * math.sin(i * 1.9))
        py = top_y + v_len * (0.36 + i * 0.09)
        painter.drawEllipse(QPointF(px, py), s * 0.025, s * 0.032)
    # 右室の調節帯
    band = QPen(QColor(200, 208, 220, 160), max(1.5, s * 0.025))
    band.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(band)
    painter.drawLine(
        QPointF(rv_cx - rv_w * 0.9, top_y + v_len * 0.62),
        QPointF(rv_cx + rv_w * 0.9, top_y + v_len * 0.56),
    )


def _valve(painter: QPainter, x: float, y: float, span: float, open_amt: float, s: float) -> None:
    pen = QPen(ECHO_VALVE, max(1.8, s * 0.028))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    half = span * 0.5
    swing = math.radians(8.0 + 72.0 * open_amt)
    for sign in (-1.0, 1.0):
        base = QPointF(x + sign * half, y)
        length = half * 0.95
        tip = QPointF(base.x() - sign * length * math.cos(swing), y - length * math.sin(swing))
        ctrl = QPointF(
            (base.x() + tip.x()) * 0.5 - sign * half * 0.12,
            (base.y() + tip.y()) * 0.5 + half * 0.05,
        )
        path = QPainterPath(base)
        path.quadTo(ctrl, tip)
        painter.drawPath(path)


def _sector_path(apex: QPointF, radius: float, half_deg: float) -> QPainterPath:
    bounds = QRectF(apex.x() - radius, apex.y() - radius, radius * 2, radius * 2)
    path = QPainterPath()
    path.moveTo(apex)
    path.arcTo(bounds, 270.0 - half_deg, 2.0 * half_deg)
    path.closeSubpath()
    return path


def _chamber(cx: float, cy: float, rx: float, ry: float, tilt: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    t = QTransform()
    t.translate(cx, cy)
    t.rotate(tilt)
    t.translate(-cx, -cy)
    return t.map(path)


def _outline(
    cx: float, top_y: float, s: float, v_len: float, atr: float, sq: float
) -> QPainterPath:
    """心臓断面の外形。上が心尖、下が心房。収縮で壁が厚くなるぶん外形はあまり動かない。"""
    thick = s * (0.13 + 0.03 * sq)
    apex_y = top_y + v_len * 0.10 - thick
    av_y = top_y + v_len
    right = cx + s * 0.07 + s * 0.72 + thick * 0.6
    left = cx - s * 0.07 - s * 0.54 - thick * 0.6
    bottom = av_y + s * 0.06 + s * 0.70 * atr + s * 0.05
    path = QPainterPath(QPointF(cx + s * 0.16, apex_y))
    path.cubicTo(
        right - s * 0.05, apex_y + v_len * 0.10, right + s * 0.06, av_y - v_len * 0.35, right, av_y
    )
    path.cubicTo(right + s * 0.02, av_y + s * 0.45, cx + s * 0.55, bottom, cx + s * 0.05, bottom)
    path.cubicTo(cx - s * 0.45, bottom, left - s * 0.02, av_y + s * 0.45, left, av_y)
    path.cubicTo(
        left - s * 0.06,
        av_y - v_len * 0.35,
        left + s * 0.10,
        apex_y + v_len * 0.25,
        cx + s * 0.16,
        apex_y,
    )
    path.closeSubpath()
    return path
