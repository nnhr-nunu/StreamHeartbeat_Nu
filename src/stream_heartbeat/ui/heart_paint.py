"""配信用キャンバスの心臓・文字。緑はクロマキー専用。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.config import CHROMA_HEX
from stream_heartbeat.overlay import FloatBurst
from stream_heartbeat.ui.heart_realistic import paint_realistic

CHROMA = QColor(CHROMA_HEX)
TEXT_COLOR = QColor(255, 236, 180)
BPM_COLOR = QColor(255, 255, 255)


def _heart_path(cx: float, cy: float, size: float) -> QPainterPath:
    s = size
    path = QPainterPath()
    path.moveTo(cx, cy + 0.38 * s)
    path.cubicTo(cx + 1.02 * s, cy - 0.08 * s, cx + 0.52 * s, cy - 0.92 * s, cx, cy - 0.32 * s)
    path.cubicTo(cx - 0.52 * s, cy - 0.92 * s, cx - 1.02 * s, cy - 0.08 * s, cx, cy + 0.38 * s)
    path.closeSubpath()
    return path


def paint_heart(
    painter: QPainter,
    rect: QRectF,
    *,
    style: str,
    scale: float,
    opacity: float,
    cycle: CardiacCycle,
    ecg_phase: float,
) -> None:
    painter.save()
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if style == "ecg":
        _paint_ecg(painter, rect, cycle, ecg_phase)
    elif style == "cute":
        _paint_cute(painter, rect, scale, cycle)
    elif style == "mech":
        _paint_mech(painter, rect, scale, cycle)
    else:
        paint_realistic(painter, rect, scale=scale, cycle=cycle)
    painter.restore()


def _paint_cute(painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    size = min(rect.width(), rect.height()) * 0.36 * scale
    painter.save()
    painter.translate(cx, cy)
    painter.scale(1.0 + 0.10 * cycle.waist, 1.0 - 0.16 * cycle.squeeze)
    painter.translate(-cx, -cy)
    path = _heart_path(cx, cy, size)
    painter.setBrush(QColor(255, 118, 168))
    painter.setPen(QPen(QColor(255, 64, 122), max(3.0, size * 0.04)))
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 210))
    painter.drawEllipse(QPointF(cx - 0.16 * size, cy - 0.12 * size), size * 0.07, size * 0.09)
    painter.drawEllipse(QPointF(cx + 0.12 * size, cy - 0.12 * size), size * 0.07, size * 0.09)
    painter.setBrush(QColor(40, 24, 48))
    painter.drawEllipse(QPointF(cx - 0.16 * size, cy - 0.11 * size), size * 0.03, size * 0.04)
    painter.drawEllipse(QPointF(cx + 0.12 * size, cy - 0.11 * size), size * 0.03, size * 0.04)
    if cycle.eject > 0.2:
        painter.setBrush(QColor(255, 80, 130, int(180 * cycle.eject)))
        painter.drawEllipse(
            QPointF(cx, cy - 0.62 * size),
            size * 0.08 * cycle.eject,
            size * 0.12 * cycle.eject,
        )
    painter.restore()


def _paint_mech(painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    size = min(rect.width(), rect.height()) * 0.34 * scale
    painter.save()
    painter.translate(cx, cy)
    painter.scale(cycle.waist, 0.92 + 0.08 * (1.0 - cycle.squeeze))
    painter.translate(-cx, -cy)
    path = _heart_path(cx, cy, size)
    painter.setBrush(QColor(28, 38, 52))
    painter.setPen(QPen(QColor(0, 210, 255), max(2.5, size * 0.03)))
    painter.drawPath(path)
    glow = QRadialGradient(QPointF(cx, cy), size * 0.28)
    glow.setColorAt(0.0, QColor(0, 255, 210, int(80 + 140 * cycle.squeeze)))
    glow.setColorAt(1.0, QColor(0, 80, 90, 0))
    painter.setBrush(glow)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(cx, cy), size * 0.20, size * 0.20)
    painter.setPen(QPen(QColor(0, 210, 255, 180), 1.5))
    for i in range(6):
        ang = i * math.pi / 3 + cycle.eject * 0.8
        painter.drawLine(
            QPointF(cx + math.cos(ang) * size * 0.12, cy + math.sin(ang) * size * 0.12),
            QPointF(cx + math.cos(ang) * size * 0.28, cy + math.sin(ang) * size * 0.28),
        )
    if cycle.eject > 0.15:
        painter.setPen(QPen(QColor(255, 90, 40, int(220 * cycle.eject)), 3))
        painter.drawLine(
            QPointF(cx + 0.08 * size, cy - 0.34 * size),
            QPointF(cx + 0.42 * size, cy - 0.62 * size),
        )
    painter.restore()


def _paint_ecg(painter: QPainter, rect: QRectF, cycle: CardiacCycle, phase: float) -> None:
    painter.setPen(QPen(QColor(18, 22, 70), 3))
    mid = rect.center().y()
    left = rect.left()
    width = rect.width()
    path = QPainterPath()
    samples = 180
    for i in range(samples + 1):
        u = (i / samples + phase) % 1.0
        y = mid - _ecg_y(u) * rect.height() * 0.22 * (0.65 + 0.35 * max(cycle.squeeze, cycle.eject))
        x = left + width * i / samples
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    painter.drawPath(path)


def _ecg_y(u: float) -> float:
    if 0.10 <= u < 0.18:
        return 0.22 * math.sin(math.pi * (u - 0.10) / 0.08)
    if 0.22 <= u < 0.24:
        return -0.18
    if 0.24 <= u < 0.28:
        peak = 0.26
        return 1.0 - abs(u - peak) / 0.02
    if 0.28 <= u < 0.31:
        return -0.28 * (1.0 - (u - 0.28) / 0.03)
    if 0.42 <= u < 0.58:
        return 0.32 * math.sin(math.pi * (u - 0.42) / 0.16)
    return 0.0


def paint_bursts(painter: QPainter, rect: QRectF, bursts: list[FloatBurst]) -> None:
    font = QFont()
    font.setPixelSize(max(22, int(min(rect.width(), rect.height()) * 0.06)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(TEXT_COLOR)
    for burst in bursts:
        painter.setOpacity(burst.alpha)
        x = rect.left() + burst.pos[0] * rect.width()
        y = rect.top() + burst.pos[1] * rect.height()
        painter.drawText(int(x), int(y), burst.text)


def paint_bpm(painter: QPainter, rect: QRectF, bpm: int) -> None:
    painter.setOpacity(1.0)
    font = QFont()
    font.setPixelSize(max(28, int(min(rect.width(), rect.height()) * 0.08)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(BPM_COLOR)
    painter.drawText(
        rect.adjusted(0, 0, 0, -16),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
        str(bpm),
    )
