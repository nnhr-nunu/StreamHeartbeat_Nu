"""リアル心臓：収縮と血液の押し出し。緑は使わない。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.motion import ejection_blobs

MUSCLE = QColor(168, 28, 36)
MUSCLE_DEEP = QColor(72, 8, 14)
FAT = QColor(196, 92, 78)
CHAMBER = QColor(48, 4, 10)
ARTERIAL = QColor(214, 24, 32)
ARTERIAL_GLOW = QColor(255, 70, 68)
AORTA = QColor(150, 32, 40)


def _myocardium(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx + 0.02 * s, cy + 0.46 * s)
    path.cubicTo(
        cx + 0.62 * s, cy + 0.18 * s, cx + 0.72 * s, cy - 0.18 * s, cx + 0.38 * s, cy - 0.42 * s
    )
    path.cubicTo(
        cx + 0.22 * s, cy - 0.62 * s, cx + 0.02 * s, cy - 0.50 * s, cx - 0.02 * s, cy - 0.32 * s
    )
    path.cubicTo(
        cx - 0.10 * s, cy - 0.58 * s, cx - 0.42 * s, cy - 0.58 * s, cx - 0.52 * s, cy - 0.28 * s
    )
    path.cubicTo(
        cx - 0.70 * s, cy + 0.02 * s, cx - 0.48 * s, cy + 0.28 * s, cx + 0.02 * s, cy + 0.46 * s
    )
    path.closeSubpath()
    return path


def _aorta(cx: float, cy: float, s: float, swell: float) -> QPainterPath:
    w = (0.07 + 0.045 * swell) * s
    path = QPainterPath()
    top = cy - 0.58 * s - 0.04 * s * swell
    path.moveTo(cx - 0.02 * s, cy - 0.34 * s)
    path.lineTo(cx - 0.02 * s - w * 0.35, top + 0.08 * s)
    path.cubicTo(
        cx + 0.12 * s,
        top - 0.12 * s,
        cx + 0.42 * s,
        top + 0.02 * s,
        cx + 0.52 * s,
        cy - 0.22 * s,
    )
    path.lineTo(cx + 0.52 * s - w * 0.2, cy - 0.18 * s)
    path.cubicTo(
        cx + 0.36 * s,
        top + 0.10 * s,
        cx + 0.10 * s,
        top + 0.02 * s,
        cx + 0.04 * s + w,
        cy - 0.32 * s,
    )
    path.closeSubpath()
    return path


def _draw_coronaries(painter: QPainter, cx: float, cy: float, s: float) -> None:
    """前下行・回旋・右冠が表面を走る。立体が使えないときの代替。"""
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(
        QPen(
            QColor(210, 36, 44),
            max(2.4, s * 0.03),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    lad = QPainterPath()
    lad.moveTo(cx - 0.06 * s, cy - 0.28 * s)
    lad.cubicTo(
        cx + 0.02 * s, cy - 0.02 * s, cx + 0.06 * s, cy + 0.18 * s, cx + 0.04 * s, cy + 0.38 * s
    )
    painter.drawPath(lad)
    rca = QPainterPath()
    rca.moveTo(cx - 0.16 * s, cy - 0.24 * s)
    rca.cubicTo(
        cx - 0.38 * s, cy - 0.06 * s, cx - 0.36 * s, cy + 0.16 * s, cx - 0.18 * s, cy + 0.28 * s
    )
    painter.drawPath(rca)
    lcx = QPainterPath()
    lcx.moveTo(cx - 0.04 * s, cy - 0.26 * s)
    lcx.cubicTo(
        cx + 0.22 * s, cy - 0.18 * s, cx + 0.32 * s, cy + 0.02 * s, cx + 0.24 * s, cy + 0.18 * s
    )
    painter.drawPath(lcx)
    painter.setPen(
        QPen(
            QColor(186, 28, 38),
            max(1.5, s * 0.016),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    diag = QPainterPath()
    diag.moveTo(cx + 0.0 * s, cy - 0.04 * s)
    diag.cubicTo(
        cx + 0.12 * s, cy + 0.02 * s, cx + 0.16 * s, cy + 0.12 * s, cx + 0.14 * s, cy + 0.22 * s
    )
    painter.drawPath(diag)


def paint_realistic(
    painter: QPainter,
    rect: QRectF,
    *,
    scale: float,
    cycle: CardiacCycle,
    look: str = "surgical",
) -> None:
    cx = rect.center().x()
    cy = rect.center().y() + rect.height() * 0.04
    size = min(rect.width(), rect.height()) * 0.42 * scale
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(cx, cy)
    painter.rotate(-12)
    painter.scale(cycle.waist, cycle.apex)
    painter.translate(-cx, -cy)

    shadow = QRadialGradient(QPointF(cx, cy + 0.28 * size), size * 0.7)
    shadow.setColorAt(0.0, QColor(40, 0, 0, 90))
    shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shadow)
    painter.drawEllipse(QPointF(cx, cy + 0.22 * size), size * 0.42, size * 0.18)

    muscle = _myocardium(cx, cy, size)
    fill = QRadialGradient(QPointF(cx - 0.08 * size, cy - 0.06 * size), size * 0.95)
    fill.setColorAt(0.0, QColor(210, 64, 70))
    fill.setColorAt(0.35, MUSCLE)
    fill.setColorAt(0.78, QColor(110, 16, 22))
    fill.setColorAt(1.0, MUSCLE_DEEP)
    painter.setBrush(fill)
    painter.setPen(QPen(QColor(58, 6, 10), max(2.0, size * 0.018)))
    painter.drawPath(muscle)

    chamber_w = size * (0.22 - 0.07 * cycle.squeeze)
    chamber_h = size * (0.26 - 0.11 * cycle.squeeze)
    chamber_grad = QRadialGradient(QPointF(cx + 0.04 * size, cy + 0.04 * size), size * 0.28)
    chamber_grad.setColorAt(0.0, QColor(90, 8, 16, int(160 + 70 * cycle.fill)))
    chamber_grad.setColorAt(1.0, QColor(CHAMBER.red(), CHAMBER.green(), CHAMBER.blue(), 40))
    painter.setBrush(chamber_grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx + 0.02 * size, cy + 0.06 * size), chamber_w, chamber_h)

    painter.setPen(QPen(QColor(96, 18, 24, 180), max(1.5, size * 0.012)))
    groove = QPainterPath()
    groove.moveTo(cx - 0.18 * size, cy - 0.22 * size)
    groove.cubicTo(
        cx - 0.02 * size,
        cy - 0.02 * size,
        cx + 0.10 * size,
        cy + 0.12 * size,
        cx + 0.08 * size,
        cy + 0.32 * size,
    )
    painter.drawPath(groove)

    sheen = QRadialGradient(
        QPointF(cx - 0.16 * size, cy - 0.18 * size),
        size * (0.22 + 0.08 * cycle.sheen),
    )
    sheen.setColorAt(0.0, QColor(255, 210, 190, int(70 + 80 * cycle.sheen)))
    sheen.setColorAt(1.0, QColor(255, 180, 160, 0))
    painter.setBrush(sheen)
    painter.drawEllipse(
        QPointF(cx - 0.16 * size, cy - 0.20 * size),
        size * 0.16,
        size * 0.11,
    )

    fat = QPainterPath()
    fat.addEllipse(QPointF(cx + 0.18 * size, cy - 0.08 * size), size * 0.10, size * 0.07)
    fat_alpha = 40 if look == "anatomy" else 70
    painter.setBrush(QColor(FAT.red(), FAT.green(), FAT.blue(), fat_alpha))
    painter.drawPath(fat)
    if look == "anatomy":
        _draw_coronaries(painter, cx, cy, size)

    aorta = _aorta(cx, cy, size, cycle.eject)
    aorta_grad = QLinearGradient(
        QPointF(cx, cy - 0.2 * size),
        QPointF(cx + 0.4 * size, cy - 0.5 * size),
    )
    aorta_grad.setColorAt(0.0, AORTA)
    aorta_grad.setColorAt(0.6, QColor(180, 36, 44))
    aorta_grad.setColorAt(1.0, QColor(120, 20, 28))
    painter.setBrush(aorta_grad)
    painter.setPen(QPen(QColor(70, 10, 14), max(1.5, size * 0.012)))
    painter.drawPath(aorta)

    origin_dt = cycle.age
    for x, y, radius, alpha in ejection_blobs(cycle.eject, origin_dt):
        px = cx + x * size
        py = cy + y * size
        blob = QRadialGradient(QPointF(px, py), max(2.0, radius * size * 2.2))
        glow_a = QColor(
            ARTERIAL_GLOW.red(),
            ARTERIAL_GLOW.green(),
            ARTERIAL_GLOW.blue(),
            int(230 * alpha),
        )
        art_a = QColor(ARTERIAL.red(), ARTERIAL.green(), ARTERIAL.blue(), int(200 * alpha))
        blob.setColorAt(0.0, glow_a)
        blob.setColorAt(0.45, art_a)
        blob.setColorAt(1.0, QColor(80, 0, 0, 0))
        painter.setBrush(blob)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(px, py), radius * size * 1.6, radius * size * 1.1)

    if cycle.eject > 0.35:
        spray = QRadialGradient(
            QPointF(cx + 0.48 * size, cy - 0.28 * size),
            size * 0.22 * cycle.eject,
        )
        spray.setColorAt(0.0, QColor(255, 48, 40, int(90 * cycle.eject)))
        spray.setColorAt(1.0, QColor(180, 0, 0, 0))
        painter.setBrush(spray)
        painter.drawEllipse(
            QPointF(cx + 0.50 * size, cy - 0.26 * size),
            size * 0.16 * cycle.eject,
            size * 0.10 * cycle.eject,
        )

    painter.restore()
