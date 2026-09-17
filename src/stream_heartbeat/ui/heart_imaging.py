"""心エコー・MRI・胸部レントゲン。緑は使わない。測定値は出さない。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QTransform,
)

from stream_heartbeat.clock import CardiacCycle

ECHO_DARK = QColor(12, 16, 22)
ECHO_MYO = QColor(118, 132, 148)
ECHO_BRIGHT = QColor(214, 224, 236)
ECHO_CAVITY = QColor(8, 10, 16)
MRI_BG = QColor(48, 4, 10)
MRI_LUNG = QColor(28, 2, 8)
MRI_TISSUE = QColor(176, 18, 42)
MRI_BLOOD = QColor(255, 92, 110)
MRI_HIGH = QColor(255, 168, 176)
XRAY_BONE = QColor(186, 198, 210)
XRAY_RIB = QColor(158, 172, 188)
XRAY_HEART = QColor(52, 58, 70)
XRAY_SOFT = QColor(18, 22, 28)

_SPECKLE: QImage | None = None
_MRI_GRAIN: QImage | None = None


def _speckle() -> QImage:
    global _SPECKLE
    if _SPECKLE is None:
        _SPECKLE = _noise_image(QColor(228, 234, 242), 142)
    return _SPECKLE


def _mri_grain() -> QImage:
    global _MRI_GRAIN
    if _MRI_GRAIN is None:
        _MRI_GRAIN = _noise_image(QColor(255, 140, 150), 150)
    return _MRI_GRAIN


def _noise_image(color: QColor, threshold: int) -> QImage:
    image = QImage(192, 192, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    cr, cg, cb = color.red(), color.green(), color.blue()
    for y in range(192):
        for x in range(192):
            n = x * 1664525 + y * 1013904223 + 2246822519
            n = (n ^ (n >> 13)) * 1274126177
            n = (n >> 16) & 255
            if n < threshold:
                continue
            alpha = min(255, (n - threshold + 8) * 5)
            image.setPixelColor(x, y, QColor(cr, cg, cb, alpha))
    return image


def paint_echo(painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle) -> None:
    cx = rect.center().x()
    size = min(rect.width(), rect.height()) * 0.42 * scale
    apex = QPointF(cx, rect.center().y() - size * 0.72)
    radius = size * 1.72
    half = 36.0
    sector = _sector_path(apex, radius, half)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ECHO_DARK)
    painter.drawPath(sector)
    painter.setClipPath(sector)

    myo = QRadialGradient(QPointF(cx, apex.y() + radius * 0.58), radius * 0.62)
    myo.setColorAt(0.0, QColor(86, 98, 112))
    myo.setColorAt(0.55, ECHO_MYO)
    myo.setColorAt(1.0, QColor(28, 34, 44))
    painter.setBrush(myo)
    painter.drawPath(_echo_myocardium(cx, apex.y(), radius, size, cycle))

    vent = 1.0 - 0.26 * cycle.squeeze
    atria = 1.0 + 0.14 * cycle.squeeze - 0.08 * cycle.fill
    painter.setBrush(ECHO_CAVITY)
    lv = _echo_chamber(
        cx + size * 0.12,
        apex.y() + radius * 0.50,
        size * 0.20 * vent,
        size * 0.28 * vent,
    )
    rv = _echo_chamber(
        cx - size * 0.13,
        apex.y() + radius * 0.48,
        size * 0.14 * vent,
        size * 0.22 * vent,
    )
    la = _echo_chamber(
        cx + size * 0.10,
        apex.y() + radius * 0.74,
        size * 0.13 * atria,
        size * 0.10 * atria,
    )
    ra = _echo_chamber(
        cx - size * 0.10,
        apex.y() + radius * 0.73,
        size * 0.11 * atria,
        size * 0.09 * atria,
    )
    painter.drawPath(lv)
    painter.drawPath(rv)
    painter.drawPath(la)
    painter.drawPath(ra)

    painter.setPen(QPen(QColor(190, 200, 212, 140), max(1.4, size * 0.012)))
    septum = QPainterPath()
    septum.moveTo(cx - size * 0.01, apex.y() + radius * 0.30)
    septum.cubicTo(
        cx + size * 0.03,
        apex.y() + radius * 0.46,
        cx + size * 0.02,
        apex.y() + radius * 0.60,
        cx,
        apex.y() + radius * 0.70,
    )
    painter.drawPath(septum)

    painter.setOpacity(0.42 + 0.10 * cycle.sheen)
    painter.setBrush(QBrush(_speckle()))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(sector)
    painter.setOpacity(1.0)

    painter.setClipping(False)
    painter.setPen(QPen(QColor(80, 92, 108, 120), 1.0))
    for i in range(3):
        t = 0.42 + i * 0.18
        painter.drawArc(
            QRectF(
                apex.x() - radius * t,
                apex.y() - radius * t,
                radius * 2 * t,
                radius * 2 * t,
            ),
            int((270 - half) * 16),
            int(2 * half * 16),
        )
    painter.restore()


def paint_mri(painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    w = min(rect.width(), rect.height()) * 0.78 * scale
    h = w * 0.90
    torso = _torso_path(cx, cy, w, h)
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    fill = QLinearGradient(QPointF(cx, cy - h * 0.5), QPointF(cx, cy + h * 0.5))
    fill.setColorAt(0.0, QColor(214, 40, 62))
    fill.setColorAt(0.42, MRI_TISSUE)
    fill.setColorAt(1.0, MRI_BG)
    painter.setBrush(fill)
    painter.drawPath(torso)
    painter.setClipPath(torso)

    painter.setBrush(MRI_LUNG)
    painter.drawPath(_lung(cx - w * 0.22, cy - h * 0.08, w * 0.24, h * 0.36, left=True))
    painter.drawPath(_lung(cx + w * 0.24, cy - h * 0.08, w * 0.23, h * 0.35, left=False))
    painter.setPen(QPen(QColor(60, 8, 16, 120), max(1.0, w * 0.006)))
    for i in range(5):
        yy = cy - h * 0.22 + i * h * 0.06
        painter.drawLine(QPointF(cx - w * 0.08, cy - h * 0.04), QPointF(cx - w * 0.32, yy))
        painter.drawLine(QPointF(cx + w * 0.10, cy - h * 0.04), QPointF(cx + w * 0.34, yy))

    painter.save()
    painter.translate(cx + w * 0.02, cy - h * 0.04)
    painter.scale(0.92 + 0.08 * cycle.waist, cycle.apex)
    painter.translate(-(cx + w * 0.02), -(cy - h * 0.04))
    heart = _mri_heart(cx + w * 0.02, cy - h * 0.04, w)
    blood = QRadialGradient(QPointF(cx + w * 0.05, cy - h * 0.08), w * 0.24)
    blood.setColorAt(0.0, MRI_HIGH)
    blood.setColorAt(0.4, MRI_BLOOD)
    blood.setColorAt(1.0, QColor(130, 10, 28))
    painter.setBrush(blood)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(heart)
    painter.setBrush(QColor(255, 214, 218, int(90 + 80 * cycle.fill)))
    painter.drawEllipse(
        QPointF(cx + w * 0.07, cy - h * 0.05),
        w * (0.055 - 0.02 * cycle.squeeze),
        w * (0.07 - 0.025 * cycle.squeeze),
    )
    painter.restore()

    painter.setClipPath(torso)
    painter.setOpacity(0.22)
    painter.setBrush(QBrush(_mri_grain()))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(torso)
    painter.setOpacity(1.0)
    painter.setPen(QPen(QColor(70, 0, 12, 40), 1.0))
    for i in range(8):
        y = cy - h * 0.46 + h * i / 7.0
        painter.drawLine(QPointF(cx - w * 0.48, y), QPointF(cx + w * 0.48, y))
    painter.restore()


def paint_xray(painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    s = min(rect.width(), rect.height()) * 0.46 * scale
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(XRAY_SOFT)
    painter.drawEllipse(QPointF(cx, cy + s * 0.04), s * 0.78, s * 0.98)

    bone_pen = QPen(XRAY_BONE, max(4.0, s * 0.05))
    bone_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(bone_pen)
    painter.drawLine(QPointF(cx, cy - s * 0.78), QPointF(cx, cy + s * 0.82))
    painter.setBrush(QColor(XRAY_BONE.red(), XRAY_BONE.green(), XRAY_BONE.blue(), 160))
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(7):
        y = cy - s * 0.62 + i * s * 0.16
        painter.drawRoundedRect(QRectF(cx - s * 0.055, y, s * 0.11, s * 0.07), 4, 4)

    painter.setPen(
        QPen(
            QColor(XRAY_RIB.red(), XRAY_RIB.green(), XRAY_RIB.blue(), 170),
            max(2.2, s * 0.026),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    for i in range(8):
        y = cy - s * 0.64 + i * s * 0.12
        width = s * (0.38 + 0.10 * math.sin(i * 0.55))
        drop = s * 0.11 + i * s * 0.01
        _rib(painter, cx, y, width, drop, left=True)
        _rib(painter, cx, y, width, drop, left=False)

    clav_pen = QPen(XRAY_BONE, max(2.4, s * 0.03))
    clav_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(clav_pen)
    clav_y = cy - s * 0.68
    painter.drawLine(QPointF(cx - s * 0.06, clav_y), QPointF(cx - s * 0.58, clav_y - s * 0.05))
    painter.drawLine(QPointF(cx + s * 0.06, clav_y), QPointF(cx + s * 0.58, clav_y - s * 0.05))

    painter.translate(cx + s * 0.12, cy + s * 0.04)
    beat = 1.0 - 0.14 * cycle.squeeze + 0.07 * cycle.fill
    painter.scale(beat * (0.96 + 0.04 * cycle.waist), beat * cycle.apex)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(XRAY_HEART.red(), XRAY_HEART.green(), XRAY_HEART.blue(), 210))
    painter.drawPath(_xray_heart(0.0, 0.0, s))
    if cycle.eject > 0.18:
        painter.setBrush(QColor(96, 108, 124, int(80 * cycle.eject)))
        painter.drawEllipse(
            QPointF(s * 0.10, -s * 0.30),
            s * 0.055 * cycle.eject,
            s * 0.07 * cycle.eject,
        )
    painter.restore()


def _rib(painter: QPainter, cx: float, y: float, width: float, drop: float, *, left: bool) -> None:
    sign = -1.0 if left else 1.0
    path = QPainterPath()
    path.moveTo(cx + sign * width * 0.06, y)
    path.cubicTo(
        cx + sign * width * 0.50,
        y + drop * 0.15,
        cx + sign * width,
        y + drop,
        cx + sign * width * 0.82,
        y + drop * 1.4,
    )
    painter.drawPath(path)


def _sector_path(apex: QPointF, radius: float, half_deg: float) -> QPainterPath:
    bounds = QRectF(apex.x() - radius, apex.y() - radius, radius * 2, radius * 2)
    path = QPainterPath()
    path.moveTo(apex)
    path.arcTo(bounds, 270.0 - half_deg, 2.0 * half_deg)
    path.closeSubpath()
    return path


def _echo_myocardium(
    cx: float,
    apex_y: float,
    radius: float,
    size: float,
    cycle: CardiacCycle,
) -> QPainterPath:
    s = size * (0.92 + 0.08 * cycle.waist)
    cy = apex_y + radius * 0.58
    path = QPainterPath()
    path.moveTo(cx, cy + 0.46 * s)
    path.cubicTo(
        cx + 0.58 * s,
        cy + 0.22 * s,
        cx + 0.62 * s,
        cy - 0.18 * s,
        cx + 0.28 * s,
        cy - 0.42 * s,
    )
    path.cubicTo(
        cx + 0.08 * s,
        cy - 0.58 * s,
        cx - 0.10 * s,
        cy - 0.46 * s,
        cx - 0.16 * s,
        cy - 0.18 * s,
    )
    path.cubicTo(
        cx - 0.38 * s,
        cy - 0.52 * s,
        cx - 0.62 * s,
        cy - 0.10 * s,
        cx - 0.48 * s,
        cy + 0.18 * s,
    )
    path.cubicTo(
        cx - 0.30 * s,
        cy + 0.42 * s,
        cx - 0.12 * s,
        cy + 0.50 * s,
        cx,
        cy + 0.46 * s,
    )
    path.closeSubpath()
    return path


def _echo_chamber(cx: float, cy: float, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    t = QTransform()
    t.translate(cx, cy)
    t.rotate(-12)
    t.translate(-cx, -cy)
    return t.map(path)


def _torso_path(cx: float, cy: float, w: float, h: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx - w * 0.42, cy - h * 0.34)
    path.cubicTo(
        cx - w * 0.50,
        cy - h * 0.50,
        cx - w * 0.22,
        cy - h * 0.56,
        cx - w * 0.10,
        cy - h * 0.48,
    )
    path.lineTo(cx + w * 0.08, cy - h * 0.48)
    path.cubicTo(
        cx + w * 0.26,
        cy - h * 0.56,
        cx + w * 0.54,
        cy - h * 0.46,
        cx + w * 0.46,
        cy - h * 0.30,
    )
    path.cubicTo(
        cx + w * 0.52,
        cy - h * 0.02,
        cx + w * 0.48,
        cy + h * 0.24,
        cx + w * 0.42,
        cy + h * 0.48,
    )
    path.lineTo(cx - w * 0.40, cy + h * 0.48)
    path.cubicTo(
        cx - w * 0.50,
        cy + h * 0.16,
        cx - w * 0.52,
        cy - h * 0.08,
        cx - w * 0.42,
        cy - h * 0.34,
    )
    path.closeSubpath()
    return path


def _lung(cx: float, cy: float, rx: float, ry: float, *, left: bool) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), rx, ry)
    t = QTransform()
    t.translate(cx, cy)
    t.rotate(-18 if left else 16)
    t.translate(-cx, -cy)
    return t.map(path)


def _mri_heart(cx: float, cy: float, w: float) -> QPainterPath:
    s = w * 0.36
    path = QPainterPath()
    path.moveTo(cx + 0.04 * s, cy + 0.40 * s)
    path.cubicTo(
        cx + 0.58 * s,
        cy + 0.22 * s,
        cx + 0.66 * s,
        cy - 0.12 * s,
        cx + 0.32 * s,
        cy - 0.36 * s,
    )
    path.cubicTo(
        cx + 0.12 * s,
        cy - 0.54 * s,
        cx - 0.08 * s,
        cy - 0.42 * s,
        cx - 0.10 * s,
        cy - 0.16 * s,
    )
    path.cubicTo(
        cx - 0.28 * s,
        cy - 0.50 * s,
        cx - 0.62 * s,
        cy - 0.28 * s,
        cx - 0.48 * s,
        cy + 0.08 * s,
    )
    path.cubicTo(
        cx - 0.34 * s,
        cy + 0.34 * s,
        cx - 0.08 * s,
        cy + 0.44 * s,
        cx + 0.04 * s,
        cy + 0.40 * s,
    )
    path.closeSubpath()
    return path


def _xray_heart(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx - 0.16 * s, cy - 0.20 * s)
    path.cubicTo(
        cx - 0.24 * s,
        cy - 0.46 * s,
        cx + 0.10 * s,
        cy - 0.50 * s,
        cx + 0.26 * s,
        cy - 0.24 * s,
    )
    path.cubicTo(
        cx + 0.52 * s,
        cy + 0.02 * s,
        cx + 0.46 * s,
        cy + 0.40 * s,
        cx + 0.14 * s,
        cy + 0.50 * s,
    )
    path.cubicTo(
        cx - 0.16 * s,
        cy + 0.54 * s,
        cx - 0.46 * s,
        cy + 0.24 * s,
        cx - 0.36 * s,
        cy + 0.02 * s,
    )
    path.cubicTo(
        cx - 0.30 * s,
        cy - 0.10 * s,
        cx - 0.20 * s,
        cy - 0.14 * s,
        cx - 0.16 * s,
        cy - 0.20 * s,
    )
    path.closeSubpath()
    return path
