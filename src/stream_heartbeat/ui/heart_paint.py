"""配信用キャンバスの 2D 描画と文字。緑はクロマキー専用。

立体で描くスタイル（リアル・機械・レントゲン・MRI）は heart_gl が担い、
ここは 2D スタイルと、立体が使えないときの代替、文字を担う。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

from stream_heartbeat.clock import BeatClock, CardiacCycle
from stream_heartbeat.overlay import FloatBurst, burst_font_px, burst_opacity
from stream_heartbeat.ui.heart_cute import paint_cute
from stream_heartbeat.ui.heart_ecg import paint_ecg
from stream_heartbeat.ui.heart_echo import paint_echo
from stream_heartbeat.ui.heart_imaging import (
    paint_mri_backdrop,
    paint_mri_flat_heart,
    paint_mri_overlay,
    paint_xray_backdrop,
    paint_xray_flat_heart,
    paint_xray_overlay,
)
from stream_heartbeat.ui.heart_realistic import paint_realistic

TEXT_COLOR = QColor(255, 236, 180)
BPM_COLOR = QColor(255, 255, 255)

GL_STYLES = frozenset({"realistic", "mech", "xray", "mri"})
PANEL_STYLES = frozenset({"xray", "mri"})


def paint_backdrop(
    painter: QPainter, rect: QRectF, *, style: str, scale: float, opacity: float
) -> None:
    """立体心臓より先に描く背景。レントゲンと MRI のパネル。"""
    if style not in PANEL_STYLES:
        return
    painter.save()
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    if style == "xray":
        paint_xray_backdrop(painter, rect, scale)
    else:
        paint_mri_backdrop(painter, rect, scale)
    painter.restore()


def paint_overlay(
    painter: QPainter, rect: QRectF, *, style: str, opacity: float, cycle: CardiacCycle
) -> None:
    """立体心臓のあとに描く前景。肋骨・粒子。"""
    if style not in PANEL_STYLES:
        return
    painter.save()
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    if style == "xray":
        paint_xray_overlay(painter, rect, cycle)
    else:
        paint_mri_overlay(painter, rect, cycle)
    painter.restore()


def paint_heart(
    painter: QPainter,
    rect: QRectF,
    *,
    style: str,
    scale: float,
    opacity: float,
    cycle: CardiacCycle,
    clock: BeatClock | None = None,
    now: float = 0.0,
) -> None:
    """2D スタイル、または立体が使えないときの代替を描く。"""
    painter.save()
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if style == "ecg":
        paint_ecg(painter, rect, clock if clock is not None else BeatClock(), now)
    elif style == "cute":
        paint_cute(painter, rect, scale, cycle)
    elif style == "echo":
        paint_echo(painter, rect, scale, cycle)
    elif style == "xray":
        paint_xray_flat_heart(painter, rect, scale, cycle)
    elif style == "mri":
        paint_mri_flat_heart(painter, rect, scale, cycle)
    else:
        paint_realistic(painter, rect, scale=scale, cycle=cycle)
    painter.restore()


def paint_bursts(
    painter: QPainter,
    rect: QRectF,
    bursts: list[FloatBurst],
    *,
    scale: float = 1.0,
    opacity: float = 1.0,
) -> None:
    font = QFont()
    font.setPixelSize(burst_font_px(min(rect.width(), rect.height()), scale))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(TEXT_COLOR)
    for burst in bursts:
        painter.setOpacity(burst_opacity(burst.alpha, opacity))
        x = rect.left() + burst.pos[0] * rect.width()
        y = rect.top() + burst.pos[1] * rect.height()
        painter.drawText(int(x), int(y), burst.text)
    painter.setOpacity(1.0)


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
