"""配信用キャンバスの心臓・文字。緑はクロマキー専用。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from stream_heartbeat.config import CHROMA_HEX
from stream_heartbeat.overlay import FloatBurst

CHROMA = QColor(CHROMA_HEX)
TEXT_COLOR = QColor(255, 236, 180)
BPM_COLOR = QColor(255, 255, 255)


def _heart_path(cx: float, cy: float, size: float) -> QPainterPath:
    s = size
    path = QPainterPath()
    path.moveTo(cx, cy + 0.35 * s)
    path.cubicTo(cx + 0.95 * s, cy - 0.15 * s, cx + 0.5 * s, cy - 0.85 * s, cx, cy - 0.35 * s)
    path.cubicTo(cx - 0.5 * s, cy - 0.85 * s, cx - 0.95 * s, cy - 0.15 * s, cx, cy + 0.35 * s)
    path.closeSubpath()
    return path


def paint_heart(
    painter: QPainter,
    rect: QRectF,
    *,
    style: str,
    scale: float,
    opacity: float,
    pulse: float,
    ecg_phase: float,
) -> None:
    painter.save()
    painter.setOpacity(max(0.05, min(1.0, opacity)))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    cx = rect.center().x()
    cy = rect.center().y()
    size = min(rect.width(), rect.height()) * 0.38 * scale * (0.82 + 0.18 * pulse)
    if style == "ecg":
        _paint_ecg(painter, rect, pulse, ecg_phase)
        painter.restore()
        return
    path = _heart_path(cx, cy, size)
    if style == "cute":
        painter.setBrush(QColor(255, 130, 170))
        painter.setPen(QPen(QColor(255, 80, 130), 3))
        painter.drawPath(path)
    elif style == "mech":
        painter.setBrush(QColor(36, 48, 64))
        painter.setPen(QPen(QColor(0, 210, 255), 3))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(0, 210, 255), 1))
        painter.drawEllipse(QPointF(cx, cy), size * 0.18, size * 0.18)
    else:
        grad = QLinearGradient(cx - size, cy - size, cx + size, cy + size)
        grad.setColorAt(0.0, QColor(210, 50, 60))
        grad.setColorAt(0.45, QColor(140, 18, 28))
        grad.setColorAt(1.0, QColor(70, 8, 14))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(90, 10, 16), 2))
        painter.drawPath(path)
        painter.setBrush(QColor(255, 180, 160, 90))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx - size * 0.18, cy - size * 0.22), size * 0.16, size * 0.12)
    painter.restore()


def _paint_ecg(painter: QPainter, rect: QRectF, pulse: float, phase: float) -> None:
    painter.setPen(QPen(QColor(20, 20, 80), 4))
    mid = rect.center().y()
    w = rect.width()
    path = QPainterPath()
    path.moveTo(rect.left(), mid)
    spike = 80.0 * pulse
    x0 = rect.left() + (phase % 1.0) * w
    path.lineTo(x0 - 24, mid)
    path.lineTo(x0 - 8, mid)
    path.lineTo(x0, mid - spike)
    path.lineTo(x0 + 10, mid + spike * 0.35)
    path.lineTo(x0 + 22, mid)
    path.lineTo(rect.right(), mid)
    painter.drawPath(path)


def paint_bursts(painter: QPainter, rect: QRectF, bursts: list[FloatBurst]) -> None:
    painter.setPen(TEXT_COLOR)
    for burst in bursts:
        painter.setOpacity(burst.alpha)
        x = rect.left() + burst.pos[0] * rect.width()
        y = rect.top() + burst.pos[1] * rect.height()
        painter.drawText(int(x), int(y), burst.text)


def paint_bpm(painter: QPainter, rect: QRectF, bpm: int) -> None:
    painter.setOpacity(1.0)
    painter.setPen(BPM_COLOR)
    painter.drawText(
        rect.adjusted(0, 0, 0, -12),
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
        str(bpm),
    )
