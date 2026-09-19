"""視聴者向けの同期文字とスタイル名。"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from stream_heartbeat.config import (
    ARRHYTHMIA_TEXT,
    BEAT_TEXT_ANGLE_JITTER_DEG,
    BEAT_TEXT_JITTER,
    BURST_FADE_IN_S,
    BURST_FADE_OUT_S,
    BURST_HOLD_S,
    DEFAULT_BEAT_TEXT_TILT,
    DEFAULT_BEAT_TEXT_X,
    DEFAULT_BEAT_TEXT_Y,
    HEART_CENTER,
    INNER_MARGIN,
    MAX_BURSTS,
    MAX_RIPPLES,
    RIPPLE_R0,
    RIPPLE_R1,
    RIPPLE_S,
)

HeartStyle = str
RNG = Callable[[], float]


def burst_font_px(min_side: float, scale: float) -> int:
    base = max(22, int(min_side * 0.06))
    return max(8, int(base * max(0.25, min(3.0, scale))))


def burst_opacity(burst_alpha: float, opacity: float) -> float:
    return max(0.0, min(1.0, burst_alpha * max(0.0, min(1.0, opacity))))


def lean_angle_deg(
    pos: tuple[float, float],
    tilt: float,
    *,
    wobble: float = 0.5,
    center: tuple[float, float] = HEART_CENTER,
) -> float:
    """文字の足元が心臓中心を向く角度。tilt=0 で直立。"""
    amount = max(0.0, min(1.0, tilt))
    tx, ty = pos
    cx, cy = center
    radial = math.degrees(math.atan2(tx - cx, cy - ty))
    jitter = (wobble - 0.5) * 2.0 * BEAT_TEXT_ANGLE_JITTER_DEG
    return (radial + jitter) * amount


@dataclass
class FloatBurst:
    text: str
    pos: tuple[float, float]
    alpha: float
    angle: float = 0.0


@dataclass
class Ripple:
    radius: float
    alpha: float


class OverlayState:
    def __init__(self, rng: RNG | None = None) -> None:
        self._rng = rng if rng is not None else (lambda: 0.5)
        self._items: list[tuple[str, float, float, float, float]] = []
        self._ripples: list[float] = []

    def _point(
        self,
        origin: tuple[float, float] | None = None,
        jitter: float | None = None,
    ) -> tuple[float, float]:
        ox, oy = origin if origin is not None else (DEFAULT_BEAT_TEXT_X, DEFAULT_BEAT_TEXT_Y)
        spread = BEAT_TEXT_JITTER if jitter is None else max(0.0, jitter)
        x = ox + (self._rng() - 0.5) * 2.0 * spread
        y = oy + (self._rng() - 0.5) * 2.0 * spread
        lo, hi = INNER_MARGIN * 0.5, 1.0 - INNER_MARGIN * 0.5
        return (max(lo, min(hi, x)), max(lo, min(hi, y)))

    def on_beat(
        self,
        t: float,
        text: str,
        origin: tuple[float, float] | None = None,
        jitter: float | None = None,
        tilt: float | None = None,
    ) -> None:
        x, y = self._point(origin, jitter)
        amount = DEFAULT_BEAT_TEXT_TILT if tilt is None else tilt
        angle = lean_angle_deg((x, y), amount, wobble=self._rng())
        self._items.append((text, x, y, t, angle))
        self._items = self._items[-MAX_BURSTS:]

    def on_arrhythmia(self, t: float) -> None:
        self.on_beat(t, ARRHYTHMIA_TEXT)

    def on_ripple(self, t: float) -> None:
        self._ripples.append(t)
        self._ripples = self._ripples[-MAX_RIPPLES:]

    def bursts_at(self, t: float) -> list[FloatBurst]:
        total = BURST_FADE_IN_S + BURST_HOLD_S + BURST_FADE_OUT_S
        out: list[FloatBurst] = []
        for text, x, y, start, angle in self._items:
            age = t - start
            if age < 0 or age > total:
                continue
            if age < BURST_FADE_IN_S:
                alpha = age / BURST_FADE_IN_S
            elif age < BURST_FADE_IN_S + BURST_HOLD_S:
                alpha = 1.0
            else:
                alpha = 1.0 - (age - BURST_FADE_IN_S - BURST_HOLD_S) / BURST_FADE_OUT_S
            out.append(
                FloatBurst(
                    text=text,
                    pos=(x, y),
                    alpha=max(0.0, min(1.0, alpha)),
                    angle=angle,
                )
            )
        return out

    def ripples_at(self, t: float) -> list[Ripple]:
        out: list[Ripple] = []
        for start in self._ripples:
            for delay in (0.0, 0.12):
                age = t - start - delay
                if age < 0 or age > RIPPLE_S:
                    continue
                progress = age / RIPPLE_S
                radius = RIPPLE_R0 + (RIPPLE_R1 - RIPPLE_R0) * progress
                if delay > 0:
                    radius *= 0.88
                out.append(Ripple(radius=radius, alpha=max(0.0, 1.0 - progress)))
        return out
