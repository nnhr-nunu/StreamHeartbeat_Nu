"""かわいい2（令和っぽいかわいい）。ぷっくりしたシールのハート。

- 白いふちのシールが少し浮いた影を落とす。中はミルキーなピンクからラベンダーへ
- オーロラのような淡い虹色の照りがゆっくり流れ、ぷっくりした光と影で膨らみを出す
- 顔は点の目と小さな口、ほっぺに斜線（///）。拍でにこっと目を細める
- まわりに細い線のきらきら・小さなハートのシールが浮かび、拍で 2 つ飛び出す
- 拍ではゼリーのように潰れて、弾んで戻る
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QRadialGradient,
)

from stream_heartbeat.clock import CardiacCycle

REIWA_PINK = QColor(255, 186, 214)
REIWA_ROSE = QColor(250, 150, 200)
REIWA_LAVENDER = QColor(196, 178, 255)
REIWA_MINT = QColor(182, 244, 226)
REIWA_LEMON = QColor(255, 244, 176)
REIWA_INK = QColor(92, 66, 104)
REIWA_BLUSH = QColor(255, 132, 166)
REIWA_SHADOW = QColor(214, 196, 240)
STICKER_EDGE = QColor(200, 176, 232)
STICKER_WHITE = QColor(255, 255, 255)


def chubby_heart(cx: float, cy: float, s: float) -> QPainterPath:
    """ころんと丸いハート。下の先も丸い。"""
    path = QPainterPath(QPointF(cx, cy + 0.60 * s))
    path.cubicTo(
        cx + 0.14 * s, cy + 0.60 * s, cx + 0.88 * s, cy + 0.16 * s, cx + 0.88 * s, cy - 0.26 * s
    )
    path.cubicTo(cx + 0.88 * s, cy - 0.72 * s, cx + 0.34 * s, cy - 0.88 * s, cx, cy - 0.46 * s)
    path.cubicTo(
        cx - 0.34 * s, cy - 0.88 * s, cx - 0.88 * s, cy - 0.72 * s, cx - 0.88 * s, cy - 0.26 * s
    )
    path.cubicTo(cx - 0.88 * s, cy + 0.16 * s, cx - 0.14 * s, cy + 0.60 * s, cx, cy + 0.60 * s)
    path.closeSubpath()
    return path


def _outline(path: QPainterPath, width: float) -> QPainterPath:
    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    return stroker.createStroke(path).united(path)


def _jelly(cycle: CardiacCycle) -> tuple[float, float]:
    """拍の潰れと、そのあとの弾み（ゼリー）。横・縦の倍率。"""
    sq = cycle.squeeze
    age = cycle.age
    wobble = (
        math.exp(-age / 0.20) * math.sin(age * 2.0 * math.pi * 5.0) * 0.07 if age > 0.06 else 0.0
    )
    return 1.0 + 0.11 * sq + wobble, 1.0 - 0.13 * sq - wobble * 0.8


def _sparkle_path(x: float, y: float, r: float) -> QPainterPath:
    """4 つの先のきらきら（✦）。辺は内へ反る。"""
    path = QPainterPath(QPointF(x, y - r))
    k = r * 0.18
    path.quadTo(QPointF(x + k, y - k), QPointF(x + r, y))
    path.quadTo(QPointF(x + k, y + k), QPointF(x, y + r))
    path.quadTo(QPointF(x - k, y + k), QPointF(x - r, y))
    path.quadTo(QPointF(x - k, y - k), QPointF(x, y - r))
    path.closeSubpath()
    return path


def _sticker(painter: QPainter, shape: QPainterPath, fill: QColor, border: float) -> None:
    """白いふちの小さなシール。"""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(STICKER_WHITE)
    painter.drawPath(_outline(shape, border))
    painter.setBrush(fill)
    painter.drawPath(shape)


def _face(painter: QPainter, cx: float, cy: float, s: float, sq: float) -> None:
    ink = QColor(REIWA_INK)
    happy = sq > 0.35
    for sign in (-1.0, 1.0):
        ex = cx + sign * s * 0.21
        ey = cy - s * 0.04
        if happy:
            # にこっと細めた目（∩ の形）
            pen = QPen(ink, max(1.6, s * 0.035))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            arc = QPainterPath(QPointF(ex - s * 0.055, ey + s * 0.015))
            arc.quadTo(QPointF(ex, ey - s * 0.06), QPointF(ex + s * 0.055, ey + s * 0.015))
            painter.drawPath(arc)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            painter.drawEllipse(QPointF(ex, ey), s * 0.052, s * 0.068)
            painter.setBrush(QColor(255, 255, 255, 235))
            painter.drawEllipse(QPointF(ex - s * 0.016, ey - s * 0.024), s * 0.019, s * 0.019)
    # 小さな口（ひらいた u）
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(196, 70, 110))
    mouth = QPainterPath(QPointF(cx - s * 0.05, cy + s * 0.055))
    open_amt = 0.05 + 0.03 * sq
    mouth.cubicTo(
        QPointF(cx - s * 0.05, cy + s * (0.055 + open_amt * 1.6)),
        QPointF(cx + s * 0.05, cy + s * (0.055 + open_amt * 1.6)),
        QPointF(cx + s * 0.05, cy + s * 0.055),
    )
    mouth.closeSubpath()
    painter.drawPath(mouth)
    # ほっぺと斜線（///）
    for sign in (-1.0, 1.0):
        bx = cx + sign * s * 0.40
        by = cy + s * 0.07
        blush = QRadialGradient(QPointF(bx, by), s * 0.13)
        blush.setColorAt(
            0.0, QColor(REIWA_BLUSH.red(), REIWA_BLUSH.green(), REIWA_BLUSH.blue(), 170)
        )
        blush.setColorAt(1.0, QColor(REIWA_BLUSH.red(), REIWA_BLUSH.green(), REIWA_BLUSH.blue(), 0))
        painter.setBrush(blush)
        painter.drawEllipse(QPointF(bx, by), s * 0.13, s * 0.085)
        pen = QPen(QColor(255, 255, 255, 220), max(1.2, s * 0.018))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        for k in range(3):
            x = bx + (k - 1) * s * 0.045
            painter.drawLine(
                QPointF(x + s * 0.016, by - s * 0.03), QPointF(x - s * 0.016, by + s * 0.03)
            )
        painter.setPen(Qt.PenStyle.NoPen)


def _decorations(
    painter: QPainter, cx: float, cy: float, s: float, now: float, cycle: CardiacCycle
) -> None:
    """まわりに浮かぶ細い線のきらきらと、小さなハートのシール。拍で 2 つ飛び出す。"""
    spots = (
        (-1.12, -0.62, 0.11, REIWA_LEMON, 0.0),
        (1.10, -0.78, 0.085, REIWA_MINT, 1.7),
        (1.22, -0.05, 0.065, REIWA_LEMON, 3.1),
        (-1.20, 0.18, 0.06, REIWA_MINT, 4.4),
    )
    border = max(1.5, s * 0.028)
    for dx, dy, r, color, phase in spots:
        twinkle = 0.75 + 0.25 * math.sin(now * 2.6 + phase)
        x = cx + dx * s
        y = cy + dy * s + math.sin(now * 1.3 + phase) * s * 0.02
        _sticker(painter, _sparkle_path(x, y, r * s * twinkle), color, border)
    hearts = ((-0.98, -0.98, 0.10, REIWA_ROSE, 0.6), (0.86, 0.46, 0.08, REIWA_LAVENDER, 2.2))
    for dx, dy, r, color, phase in hearts:
        x = cx + dx * s
        y = cy + dy * s + math.sin(now * 1.1 + phase) * s * 0.025
        _sticker(painter, chubby_heart(x, y, r * s), color, border)
    # 拍で小さなハートが左右から飛び出してふわっと上へ
    if cycle.age < 0.9:
        u = cycle.age / 0.9
        alpha = max(0.0, 1.0 - u) ** 1.2
        for sign, color in ((-1.0, REIWA_PINK), (1.0, REIWA_LAVENDER)):
            x = cx + sign * s * (0.70 + 0.35 * u)
            y = cy - s * (0.55 + 0.55 * u)
            r = s * 0.10 * (0.6 + 0.5 * min(1.0, u * 4.0))
            painter.save()
            painter.setOpacity(painter.opacity() * alpha)
            _sticker(painter, chubby_heart(x, y, r), color, border)
            painter.restore()


def paint_cute_reiwa(
    painter: QPainter, rect: QRectF, scale: float, cycle: CardiacCycle, now: float = 0.0
) -> None:
    cx = rect.center().x()
    cy = rect.center().y()
    s = min(rect.width(), rect.height()) * 0.36 * scale
    sx, sy = _jelly(cycle)
    bob = math.sin(now * math.pi * 0.9) * s * 0.012
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _decorations(painter, cx, cy, s, now, cycle)

    # 下の先を床にして潰す（座っているように）
    foot = QPointF(cx, cy + 0.60 * s + bob)
    painter.translate(foot)
    painter.scale(sx, sy)
    painter.translate(-foot)
    heart = chubby_heart(cx, cy + bob, s)
    sticker = _outline(heart, s * 0.16)

    # シールの厚み（下へずらした不透明な影。半透明にするとクロマキーで縁が残る）
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(REIWA_SHADOW)
    painter.drawPath(sticker.translated(s * 0.015, s * 0.045))
    painter.setBrush(STICKER_WHITE)
    painter.drawPath(sticker)
    # 白いふちの外にごく細い線（白い背景でもシールの形が分かる）
    painter.setPen(QPen(STICKER_EDGE, max(1.0, s * 0.012)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(sticker)
    painter.setPen(Qt.PenStyle.NoPen)

    # 中身: ミルキーなピンクからラベンダーへ
    body = QLinearGradient(QPointF(cx - s * 0.8, cy - s * 0.7), QPointF(cx + s * 0.7, cy + s * 0.6))
    body.setColorAt(0.0, REIWA_PINK)
    body.setColorAt(0.55, REIWA_ROSE)
    body.setColorAt(1.0, REIWA_LAVENDER)
    painter.setBrush(body)
    painter.drawPath(heart)

    painter.save()
    painter.setClipPath(heart)
    # オーロラの照り: 淡い虹色の帯がゆっくり流れる
    drift = (now * 0.12) % 1.0
    band = QLinearGradient(
        QPointF(cx - s * (1.4 - 1.6 * drift), cy - s * 0.9),
        QPointF(cx + s * (0.2 + 1.6 * drift), cy + s * 0.5),
    )
    for at, color in (
        (0.0, REIWA_MINT),
        (0.35, REIWA_LEMON),
        (0.7, REIWA_LAVENDER),
        (1.0, REIWA_MINT),
    ):
        band.setColorAt(at, QColor(color.red(), color.green(), color.blue(), 70))
    painter.setBrush(band)
    painter.drawPath(heart)
    # ぷっくりした膨らみ: 右下に影、左上に柔らかい光
    shade = QRadialGradient(QPointF(cx + s * 0.35, cy + s * 0.35), s * 0.95)
    shade.setColorAt(0.0, QColor(150, 110, 210, 0))
    shade.setColorAt(0.6, QColor(150, 110, 210, 0))
    shade.setColorAt(1.0, QColor(150, 110, 210, 110))
    painter.setBrush(shade)
    painter.drawPath(heart)
    glow = QRadialGradient(QPointF(cx - s * 0.42, cy - s * 0.40), s * 0.55)
    glow.setColorAt(0.0, QColor(255, 255, 255, 200))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(glow)
    painter.drawPath(heart)
    painter.restore()

    # つや: 細い弧と小さな点
    pen = QPen(QColor(255, 255, 255, 235), max(2.0, s * 0.05))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    shine = QPainterPath(QPointF(cx - s * 0.70, cy - s * 0.22))
    shine.quadTo(QPointF(cx - s * 0.70, cy - s * 0.56), QPointF(cx - s * 0.42, cy - s * 0.62))
    painter.drawPath(shine)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawEllipse(QPointF(cx - s * 0.30, cy - s * 0.60), s * 0.035, s * 0.035)

    _face(painter, cx, cy + bob, s, cycle.squeeze)
    painter.restore()
