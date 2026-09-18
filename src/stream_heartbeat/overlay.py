"""視聴者向けの同期文字とスタイル名。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from stream_heartbeat.config import (
    ARRHYTHMIA_TEXT,
    BURST_FADE_IN_S,
    BURST_FADE_OUT_S,
    BURST_HOLD_S,
    INNER_MARGIN,
    MAX_BURSTS,
)

HeartStyle = str
RNG = Callable[[], float]


def burst_font_px(min_side: float, scale: float) -> int:
    base = max(22, int(min_side * 0.06))
    return max(8, int(base * max(0.25, min(3.0, scale))))


def burst_opacity(burst_alpha: float, opacity: float) -> float:
    return max(0.0, min(1.0, burst_alpha * max(0.0, min(1.0, opacity))))


@dataclass
class FloatBurst:
    text: str
    pos: tuple[float, float]
    alpha: float


class OverlayState:
    def __init__(self, rng: RNG | None = None) -> None:
        self._rng = rng if rng is not None else (lambda: 0.5)
        self._items: list[tuple[str, float, float, float]] = []

    def _point(self) -> tuple[float, float]:
        span = 1.0 - 2 * INNER_MARGIN
        return (
            INNER_MARGIN + self._rng() * span,
            INNER_MARGIN + self._rng() * span,
        )

    def on_beat(self, t: float, text: str) -> None:
        x, y = self._point()
        self._items.append((text, x, y, t))
        self._items = self._items[-MAX_BURSTS:]

    def on_arrhythmia(self, t: float) -> None:
        self.on_beat(t, ARRHYTHMIA_TEXT)

    def bursts_at(self, t: float) -> list[FloatBurst]:
        total = BURST_FADE_IN_S + BURST_HOLD_S + BURST_FADE_OUT_S
        out: list[FloatBurst] = []
        for text, x, y, start in self._items:
            age = t - start
            if age < 0 or age > total:
                continue
            if age < BURST_FADE_IN_S:
                alpha = age / BURST_FADE_IN_S
            elif age < BURST_FADE_IN_S + BURST_HOLD_S:
                alpha = 1.0
            else:
                alpha = 1.0 - (age - BURST_FADE_IN_S - BURST_HOLD_S) / BURST_FADE_OUT_S
            out.append(FloatBurst(text=text, pos=(x, y), alpha=max(0.0, min(1.0, alpha))))
        return out
