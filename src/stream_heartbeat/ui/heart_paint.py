"""配信用キャンバスの 2D 描画と文字。緑はクロマキー専用。

立体で描くスタイル（リアル・機械・レントゲン・MRI）は heart_gl が担い、
ここは 2D スタイルと、立体が使えないときの代替、文字を担う。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from stream_heartbeat.clock import BeatClock, CardiacCycle
from stream_heartbeat.config import BACKDROP_COLORS, CHROMA_HEX
from stream_heartbeat.overlay import FloatBurst, Ripple, burst_font_px, burst_opacity
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
BPM_COLORS = (
    ("#FFFFFF", "白"),
    ("#FFECA0", "黄"),
    ("#111111", "黒"),
    ("#FF4D4D", "赤"),
)
BPM_OUTLINES = (
    ("#000000", "黒縁"),
    ("#FFFFFF", "白縁"),
    ("", "なし"),
)
BACKDROPS = (
    ("green", "緑（クロマキー）"),
    ("white", "白"),
    ("black", "黒"),
    ("transparent", "透明"),
)


def backdrop_color(key: str) -> QColor:
    if key == "transparent":
        return QColor(0, 0, 0, 0)
    return QColor(BACKDROP_COLORS.get(key, CHROMA_HEX))


def _draw_outlined_text(
    painter: QPainter,
    x: int,
    y: int,
    text: str,
    fill: QColor,
    outline: QColor | None,
) -> None:
    if outline is not None and outline.alpha() > 0:
        painter.setPen(outline)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            painter.drawText(x + dx, y + dy, text)
    painter.setPen(fill)
    painter.drawText(x, y, text)


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
    color: str = "#FF4D4D",
    outline: str = "#000000",
) -> None:
    font = QFont()
    font.setPixelSize(burst_font_px(min(rect.width(), rect.height()), scale))
    font.setBold(True)
    painter.setFont(font)
    fill = QColor(color) if QColor(color).isValid() else TEXT_COLOR
    ring = QColor(outline) if outline and QColor(outline).isValid() else None
    for burst in bursts:
        painter.save()
        painter.setOpacity(burst_opacity(burst.alpha, opacity))
        x = rect.left() + burst.pos[0] * rect.width()
        y = rect.top() + burst.pos[1] * rect.height()
        painter.translate(x, y)
        painter.rotate(burst.angle)
        _draw_outlined_text(painter, 0, 0, burst.text, fill, ring)
        painter.restore()
    painter.setOpacity(1.0)


def paint_ripples(painter: QPainter, rect: QRectF, ripples: list[Ripple]) -> None:
    side = min(rect.width(), rect.height())
    center = QPointF(rect.center())
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for ripple in ripples:
        painter.setOpacity(ripple.alpha)
        radius = ripple.radius * side
        painter.setPen(QPen(TEXT_COLOR, max(2.0, side * 0.01)))
        painter.drawEllipse(center, radius, radius)
    painter.setOpacity(1.0)
    painter.restore()


def paint_bpm(
    painter: QPainter,
    rect: QRectF,
    bpm: int,
    *,
    scale: float = 1.0,
    pos: tuple[float, float] = (0.5, 0.88),
    color: str = "#FFFFFF",
    outline: str = "#000000",
) -> None:
    painter.setOpacity(1.0)
    font = QFont()
    font.setPixelSize(max(28, int(min(rect.width(), rect.height()) * 0.08 * max(0.4, scale))))
    font.setBold(True)
    painter.setFont(font)
    fill = QColor(color) if QColor(color).isValid() else BPM_COLOR
    ring = QColor(outline) if outline and QColor(outline).isValid() else None
    text = str(bpm)
    metrics = painter.fontMetrics()
    x = int(rect.left() + pos[0] * rect.width() - metrics.horizontalAdvance(text) / 2)
    y = int(rect.top() + pos[1] * rect.height() + metrics.ascent() / 2)
    _draw_outlined_text(painter, x, y, text, fill, ring)
