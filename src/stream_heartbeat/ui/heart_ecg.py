"""心電図モニター風の描画。QRS は実際に拍を拾った瞬間に出る。

モニターと同じく、光点が左から右へ掃引し、右端で左へ戻る。光点の前は消えている。
緑の背景に載せるので波形は赤橙。緑は使わない。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

from stream_heartbeat.clock import BeatClock

ECG_COLOR = QColor(255, 72, 48)
ECG_GLOW = QColor(150, 22, 12)
ECG_HEAD = QColor(255, 226, 210)
ECG_PEN_MIN = 8
SWEEP_SECONDS = 4.0
SAMPLES = 480
CHUNK = 24
ERASE_FRACTION = 0.06


def ecg_value(dt: float, interval: float) -> float:
    """拍の起点から dt 秒後の波の高さ。R 波の頂点を 1.0 とする。

    心音の起点は QRS の直後なので、QRS を起点直前に置く。P 波は次の拍の手前。
    """
    if dt < 0.0:
        return 0.0
    q = -0.15 * _gauss(dt, 0.012, 0.006)
    r = 1.0 * _gauss(dt, 0.028, 0.009)
    s = -0.28 * _gauss(dt, 0.050, 0.010)
    t_center = 0.20 + 0.16 * math.sqrt(max(0.3, min(1.6, interval)))
    t_wave = 0.30 * _gauss(dt, t_center, 0.045 + 0.02 * interval)
    p_center = interval - 0.14
    p_wave = 0.14 * _gauss(dt, p_center, 0.025) if interval > 0.36 else 0.0
    return q + r + s + t_wave + p_wave


def _gauss(x: float, mu: float, sigma: float) -> float:
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z)


def paint_ecg(painter: QPainter, rect: QRectF, clock: BeatClock, now: float) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    mid = rect.center().y() + rect.height() * 0.04
    amp = rect.height() * 0.30
    left = rect.left() + rect.width() * 0.02
    span = rect.width() * 0.96
    width = max(ECG_PEN_MIN, int(rect.height() * 0.014))
    interval = clock.interval()
    head_u = (now / SWEEP_SECONDS) % 1.0
    base_opacity = painter.opacity()

    def point_at(i: int) -> tuple[QPointF, float]:
        u = i / SAMPLES
        back = (head_u - u) % 1.0
        tau = now - back * SWEEP_SECONDS
        value = ecg_value(tau - clock.origin_before(tau), interval)
        return QPointF(left + span * u, mid - value * amp), back

    glow_pen = QPen(ECG_GLOW, width * 2.6)
    glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen = QPen(ECG_COLOR, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    for start in range(0, SAMPLES, CHUNK):
        path = QPainterPath()
        backs: list[float] = []
        for i in range(start, min(SAMPLES, start + CHUNK) + 1):
            point, back = point_at(i)
            backs.append(back)
            if i == start:
                path.moveTo(point)
            else:
                path.lineTo(point)
        age = sum(backs) / len(backs)
        if age > 1.0 - ERASE_FRACTION:
            continue
        # 掃引が古いほど薄く。光点の直前は消える
        alpha = 0.35 + 0.65 * (1.0 - age) ** 0.6
        painter.setOpacity(base_opacity * alpha * 0.6)
        painter.setPen(glow_pen)
        painter.drawPath(path)
        painter.setOpacity(base_opacity * alpha)
        painter.setPen(pen)
        painter.drawPath(path)

    head_point, _ = point_at(int(head_u * SAMPLES))
    age_since_beat = now - clock.origin_before(now)
    flash = max(0.0, 1.0 - age_since_beat / 0.30)
    radius = width * (2.2 + 3.0 * flash)
    halo = QRadialGradient(head_point, radius)
    halo.setColorAt(0.0, QColor(ECG_HEAD.red(), ECG_HEAD.green(), ECG_HEAD.blue(), 255))
    halo.setColorAt(0.4, QColor(ECG_COLOR.red(), ECG_COLOR.green(), ECG_COLOR.blue(), 200))
    halo.setColorAt(1.0, QColor(ECG_COLOR.red(), ECG_COLOR.green(), ECG_COLOR.blue(), 0))
    painter.setOpacity(base_opacity)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(halo)
    painter.drawEllipse(head_point, radius, radius)
    painter.restore()
