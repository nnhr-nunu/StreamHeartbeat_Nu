"""レントゲン・MRI の背景と前景。心臓本体は立体描画が担う。

背景（backdrop）は心臓より先に、前景（overlay）は心臓のあとに描く。
レントゲンでは肋骨が心臓の影に重なり、MRI では粒子と走査線が全体に乗る。
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
    QRadialGradient,
    QTransform,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.ui.noise_images import grain_tile, lung_tile

XRAY_BG = QColor(6, 7, 9)
XRAY_SOFT = QColor(26, 30, 36)
XRAY_LUNG = QColor(14, 16, 20)
XRAY_BONE = QColor(190, 200, 212)
XRAY_RIB = QColor(150, 162, 178)
XRAY_HEART = QColor(96, 104, 116)
MRI_BG = QColor(4, 4, 6)
MRI_TISSUE = QColor(122, 34, 44)
MRI_BLOOD = QColor(255, 120, 132)
MRI_FAT = QColor(210, 150, 140)
PANEL_RADIUS_RATIO = 0.035


def panel_rect(rect: QRectF) -> QRectF:
    side = min(rect.width(), rect.height()) * 0.96
    return QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)


def _panel_path(rect: QRectF) -> QPainterPath:
    radius = min(rect.width(), rect.height()) * PANEL_RADIUS_RATIO
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


# ---------------------------------------------------------------- レントゲン


def paint_xray_backdrop(painter: QPainter, rect: QRectF, scale: float) -> None:
    panel = panel_rect(rect)
    cx = panel.center().x()
    cy = panel.center().y()
    s = panel.height() * 0.5
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(XRAY_BG)
    painter.drawPath(_panel_path(panel))
    painter.setClipPath(_panel_path(panel))

    # 胸郭の軟部組織。中央が少し明るく縁が暗い
    soft = QRadialGradient(QPointF(cx, cy + s * 0.1), s * 1.15)
    soft.setColorAt(0.0, QColor(40, 44, 52))
    soft.setColorAt(0.6, XRAY_SOFT)
    soft.setColorAt(1.0, QColor(12, 13, 16))
    painter.setBrush(soft)
    painter.drawPath(_torso(cx, cy, s))

    # 肺野。黒く、もやと血管影
    for left in (True, False):
        lung = _lung(cx, cy, s, left=left)
        painter.setBrush(XRAY_LUNG)
        painter.drawPath(lung)
        painter.save()
        painter.setClipPath(lung, Qt.ClipOperation.IntersectClip)
        painter.setOpacity(0.35)
        painter.setBrush(QBrush(lung_tile(1 if left else 2)))
        painter.drawPath(lung)
        painter.restore()

    # 横隔膜のドームと胃泡
    painter.setBrush(QColor(52, 56, 64))
    dome = QPainterPath()
    dome.moveTo(cx - s * 0.98, cy + s * 0.95)
    dome.cubicTo(
        cx - s * 0.80, cy + s * 0.42, cx - s * 0.30, cy + s * 0.45, cx - s * 0.02, cy + s * 0.70
    )
    dome.cubicTo(
        cx + s * 0.25, cy + s * 0.50, cx + s * 0.80, cy + s * 0.48, cx + s * 0.98, cy + s * 0.95
    )
    dome.closeSubpath()
    painter.drawPath(dome)

    # 脊柱。椎体が心臓の影に淡く透ける
    spine_pen = QPen(QColor(48, 52, 62), max(4.0, s * 0.11))
    spine_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(spine_pen)
    painter.drawLine(QPointF(cx, cy - s * 0.96), QPointF(cx, cy + s * 0.96))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(84, 90, 104, 120))
    step = s * 0.115
    y = cy - s * 0.88
    while y < cy + s * 0.9:
        painter.drawRoundedRect(QRectF(cx - s * 0.045, y, s * 0.09, step * 0.6), 3, 3)
        y += step
    painter.restore()
    del scale


def paint_xray_overlay(painter: QPainter, rect: QRectF, cycle: CardiacCycle) -> None:
    panel = panel_rect(rect)
    cx = panel.center().x()
    cy = panel.center().y()
    s = panel.height() * 0.5
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setClipPath(_panel_path(panel))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

    # 肋骨。後ろの弓は淡く、前の弓はやや明るい。どちらも心臓の影より弱い
    for i in range(7):
        y = cy - s * 0.74 + i * s * 0.19
        width = s * (0.72 + 0.14 * math.sin(0.6 + i * 0.45))
        alpha_back = 42 + int(10 * math.sin(i))
        alpha_front = 54
        for left in (True, False):
            _rib(painter, cx, y, width, s * 0.30, left=left, front=False, alpha=alpha_back, s=s)
            _rib(
                painter,
                cx,
                y + s * 0.24,
                width * 0.92,
                s * 0.22,
                left=left,
                front=True,
                alpha=alpha_front,
                s=s,
            )

    # 鎖骨
    clav = QPen(
        QColor(XRAY_BONE.red(), XRAY_BONE.green(), XRAY_BONE.blue(), 70), max(3.0, s * 0.04)
    )
    clav.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(clav)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for sign in (-1.0, 1.0):
        path = QPainterPath(QPointF(cx + sign * s * 0.08, cy - s * 0.80))
        path.cubicTo(
            cx + sign * s * 0.35,
            cy - s * 0.90,
            cx + sign * s * 0.62,
            cy - s * 0.86,
            cx + sign * s * 0.92,
            cy - s * 0.72,
        )
        painter.drawPath(path)

    # 呼吸のようにごく僅かに揺れるフィルム粒子
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    brush = QBrush(grain_tile(3, QColor(200, 210, 224), 176))
    brush.setTransform(QTransform().translate(int(cycle.age * 60) % 256, int(cycle.age * 37) % 256))
    painter.setOpacity(0.18)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(brush)
    painter.drawRect(panel)

    # 周辺減光
    painter.setOpacity(1.0)
    vignette = QRadialGradient(panel.center(), panel.width() * 0.72)
    vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
    vignette.setColorAt(0.75, QColor(0, 0, 0, 0))
    vignette.setColorAt(1.0, QColor(0, 0, 0, 160))
    painter.setBrush(vignette)
    painter.drawRect(panel)
    painter.restore()


def _rib(
    painter: QPainter,
    cx: float,
    y: float,
    width: float,
    drop: float,
    *,
    left: bool,
    front: bool,
    alpha: int,
    s: float,
) -> None:
    sign = -1.0 if left else 1.0
    color = XRAY_BONE if front else XRAY_RIB
    pen = QPen(
        QColor(color.red(), color.green(), color.blue(), alpha),
        max(3.0, s * (0.040 if front else 0.034)),
    )
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    if front:
        path.moveTo(cx + sign * width * 0.98, y - drop * 0.4)
        path.cubicTo(
            cx + sign * width * 0.80,
            y + drop * 0.55,
            cx + sign * width * 0.45,
            y + drop * 0.95,
            cx + sign * width * 0.12,
            y + drop * 1.05,
        )
    else:
        path.moveTo(cx + sign * s * 0.07, y)
        path.cubicTo(
            cx + sign * width * 0.45,
            y - drop * 0.35,
            cx + sign * width * 0.95,
            y + drop * 0.20,
            cx + sign * width * 0.98,
            y + drop * 0.85,
        )
    painter.drawPath(path)
    # 骨の中の髄は少し暗い
    inner = QPen(QColor(0, 0, 0, alpha // 3), pen.widthF() * 0.35)
    inner.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    painter.setPen(inner)
    painter.drawPath(path)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)


def _torso(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx - s * 0.62, cy - s * 0.98)
    path.cubicTo(
        cx - s * 1.10, cy - s * 0.60, cx - s * 1.05, cy + s * 0.60, cx - s * 0.98, cy + s * 1.05
    )
    path.lineTo(cx + s * 0.98, cy + s * 1.05)
    path.cubicTo(
        cx + s * 1.05, cy + s * 0.60, cx + s * 1.10, cy - s * 0.60, cx + s * 0.62, cy - s * 0.98
    )
    path.closeSubpath()
    return path


def _lung(cx: float, cy: float, s: float, *, left: bool) -> QPainterPath:
    sign = -1.0 if left else 1.0
    path = QPainterPath()
    path.moveTo(cx + sign * s * 0.12, cy - s * 0.78)
    path.cubicTo(
        cx + sign * s * 0.55,
        cy - s * 1.02,
        cx + sign * s * 0.95,
        cy - s * 0.55,
        cx + sign * s * 0.92,
        cy + s * 0.10,
    )
    path.cubicTo(
        cx + sign * s * 0.90,
        cy + s * 0.50,
        cx + sign * s * 0.65,
        cy + s * 0.68,
        cx + sign * s * 0.40,
        cy + s * 0.62,
    )
    path.cubicTo(
        cx + sign * s * 0.20,
        cy + s * 0.40,
        cx + sign * s * 0.12,
        cy - s * 0.10,
        cx + sign * s * 0.12,
        cy - s * 0.78,
    )
    path.closeSubpath()
    return path


# ---------------------------------------------------------------- MRI


def paint_mri_backdrop(painter: QPainter, rect: QRectF, scale: float) -> None:
    panel = panel_rect(rect)
    cx = panel.center().x()
    cy = panel.center().y()
    s = panel.height() * 0.5
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(MRI_BG)
    painter.drawPath(_panel_path(panel))
    painter.setClipPath(_panel_path(panel))

    # 胸壁の断面。皮下脂肪が明るく、筋が暗い
    body = QPainterPath()
    body.addEllipse(QPointF(cx, cy + s * 0.06), s * 0.98, s * 0.80)
    fat = QRadialGradient(QPointF(cx, cy + s * 0.06), s * 0.98)
    fat.setColorAt(0.0, QColor(22, 8, 10))
    fat.setColorAt(0.82, QColor(28, 9, 12))
    fat.setColorAt(0.92, QColor(MRI_FAT.red(), MRI_FAT.green(), MRI_FAT.blue(), 90))
    fat.setColorAt(1.0, QColor(MRI_FAT.red(), MRI_FAT.green(), MRI_FAT.blue(), 30))
    painter.setBrush(fat)
    painter.drawPath(body)

    # 肺は信号がなく黒
    painter.setBrush(QColor(2, 2, 3))
    for sign in (-1.0, 1.0):
        lung = QPainterPath()
        lung.addEllipse(QPointF(cx + sign * s * 0.50, cy + s * 0.04), s * 0.34, s * 0.54)
        t = QTransform()
        t.translate(cx + sign * s * 0.50, cy + s * 0.04)
        t.rotate(-sign * 14)
        t.translate(-(cx + sign * s * 0.50), -(cy + s * 0.04))
        painter.drawPath(t.map(lung))

    # 脊椎と大動脈の断面（下方）
    painter.setBrush(QColor(MRI_TISSUE.red(), MRI_TISSUE.green(), MRI_TISSUE.blue(), 170))
    painter.drawEllipse(QPointF(cx, cy + s * 0.66), s * 0.13, s * 0.11)
    painter.setBrush(QColor(60, 16, 20))
    painter.drawEllipse(QPointF(cx, cy + s * 0.60), s * 0.05, s * 0.045)
    painter.setBrush(QColor(MRI_BLOOD.red(), MRI_BLOOD.green(), MRI_BLOOD.blue(), 110))
    painter.drawEllipse(QPointF(cx - s * 0.20, cy + s * 0.58), s * 0.06, s * 0.06)
    painter.restore()
    del scale


def paint_mri_overlay(painter: QPainter, rect: QRectF, cycle: CardiacCycle) -> None:
    panel = panel_rect(rect)
    painter.save()
    painter.setClipPath(_panel_path(panel))
    painter.setPen(Qt.PenStyle.NoPen)
    frame = int(cycle.age * 24)
    grain = QBrush(grain_tile(5 + frame % 3, QColor(255, 150, 160), 168))
    grain.setTransform(QTransform().translate((frame * 13) % 256, (frame * 5) % 256))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.setOpacity(0.22)
    painter.setBrush(grain)
    painter.drawRect(panel)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

    # 走査線
    painter.setOpacity(0.28)
    painter.setPen(QPen(QColor(0, 0, 0, 120), 1.0))
    y = panel.top()
    while y < panel.bottom():
        painter.drawLine(QPointF(panel.left(), y), QPointF(panel.right(), y))
        y += 3.0

    painter.setOpacity(1.0)
    vignette = QRadialGradient(panel.center(), panel.width() * 0.75)
    vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
    vignette.setColorAt(0.7, QColor(0, 0, 0, 0))
    vignette.setColorAt(1.0, QColor(0, 0, 0, 190))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(vignette)
    painter.drawRect(panel)
    painter.restore()


# ------------------------------------------------- 立体描画が使えないときの代替


def paint_xray_flat_heart(
    painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle
) -> None:
    panel = panel_rect(rect)
    cx = panel.center().x() + panel.width() * 0.05
    cy = panel.center().y() + panel.height() * 0.06
    s = panel.height() * 0.30 * scale / 0.7
    painter.save()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.translate(cx, cy)
    painter.scale(1.0 - 0.10 * cycle.squeeze, cycle.apex * 0.5 + 0.5)
    painter.setPen(Qt.PenStyle.NoPen)
    shade = QRadialGradient(QPointF(0, 0), s)
    shade.setColorAt(0.0, QColor(XRAY_HEART.red(), XRAY_HEART.green(), XRAY_HEART.blue(), 200))
    shade.setColorAt(1.0, QColor(XRAY_HEART.red(), XRAY_HEART.green(), XRAY_HEART.blue(), 40))
    painter.setBrush(shade)
    painter.drawEllipse(QPointF(0, 0), s * 0.9, s)
    painter.restore()


def paint_mri_flat_heart(
    painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle
) -> None:
    panel = panel_rect(rect)
    cx = panel.center().x()
    cy = panel.center().y() - panel.height() * 0.04
    s = panel.height() * 0.30 * scale / 0.7
    painter.save()
    painter.translate(cx, cy)
    painter.scale(1.0 - 0.14 * cycle.squeeze, cycle.apex * 0.6 + 0.4)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(MRI_TISSUE)
    painter.drawEllipse(QPointF(0, 0), s * 0.95, s)
    painter.setBrush(MRI_BLOOD)
    painter.drawEllipse(QPointF(s * 0.2, 0), s * 0.36 * (1.0 - 0.3 * cycle.squeeze), s * 0.5)
    painter.drawEllipse(
        QPointF(-s * 0.35, s * 0.05), s * 0.22 * (1.0 - 0.3 * cycle.squeeze), s * 0.4
    )
    painter.restore()
