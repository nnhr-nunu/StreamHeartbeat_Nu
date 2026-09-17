"""心音を正本にした拍時計。"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from stream_heartbeat.config import (
    ARRHYTHMIA_COOLDOWN_S,
    ARRHYTHMIA_STREAK,
    ARRYTHMIA_DEVIATION,
    DEFAULT_BPM,
    LOST_INTERVALS,
    MAX_BPM,
    MIN_BPM,
    MISMATCH_BPM,
)


@dataclass(frozen=True)
class CardiacCycle:
    squeeze: float
    eject: float
    fill: float
    apex: float
    waist: float
    sheen: float
    age: float


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _envelope(dt: float, start: float, peak: float, end: float) -> float:
    if dt <= start or dt >= end:
        return 0.0
    if dt <= peak:
        return _smoothstep((dt - start) / max(peak - start, 1e-6))
    return _smoothstep(1.0 - (dt - peak) / max(end - peak, 1e-6))


class BeatClock:
    def __init__(self) -> None:
        self._beats: list[float] = []
        self._bpm = float(DEFAULT_BPM)
        self.detected = False
        self.oshilog_bpm: int | None = None
        self._wild = 0
        self._arrhythmia_until = -1e9
        self._last_event = 0.0

    @property
    def bpm(self) -> int:
        return int(round(self._bpm))

    def feed_beat(self, t: float) -> None:
        if self._beats:
            interval = t - self._beats[-1]
            if interval > 0:
                self._update_bpm(interval)
                median = self._median_interval()
                if median and abs(interval - median) / median > ARRYTHMIA_DEVIATION:
                    self._wild += 1
                else:
                    self._wild = 0
        self._beats.append(t)
        self._beats = self._beats[-24:]
        self.detected = True
        self._last_event = t

    def _update_bpm(self, interval: float) -> None:
        bpm = 60.0 / interval
        self._bpm = min(MAX_BPM, max(MIN_BPM, bpm))

    def _median_interval(self) -> float | None:
        if len(self._beats) < 3:
            return None
        gaps = [b - a for a, b in zip(self._beats[:-1], self._beats[1:])]
        return statistics.median(gaps)

    def interval(self) -> float:
        return 60.0 / self._bpm

    def lost_if_silent(self, t: float) -> None:
        if not self._beats:
            self.detected = False
            return
        if t - self._beats[-1] >= self.interval() * LOST_INTERVALS:
            self.detected = False

    def _pulse_origin(self, t: float) -> float:
        if self.detected and self._beats:
            return self._beats[-1]
        step = self.interval()
        last = self._beats[-1] if self._beats else 0.0
        if t <= last:
            return last
        n = math.floor((t - last) / step)
        return last + n * step

    def cycle(self, t: float) -> CardiacCycle:
        origin = self._pulse_origin(t)
        dt = max(0.0, t - origin)
        interval = self.interval()
        systole = min(0.34, max(0.20, interval * 0.36))
        squeeze = _envelope(dt, 0.0, 0.05, systole * 0.78)
        eject = _envelope(dt, 0.045, 0.11, systole)
        fill = _envelope(dt, systole * 0.55, systole + 0.04, min(interval * 0.92, systole + 0.28))
        apex = 1.0 - 0.24 * squeeze
        waist = 1.0 + 0.08 * squeeze
        sheen = _envelope(dt, 0.02, 0.07, 0.16)
        return CardiacCycle(
            squeeze=squeeze,
            eject=eject,
            fill=fill,
            apex=apex,
            waist=waist,
            sheen=sheen,
            age=dt,
        )

    def pulse_scale(self, t: float) -> float:
        beat = self.cycle(t)
        return 0.30 + 0.70 * max(beat.squeeze, beat.eject * 0.55)

    def pop_arrhythmia(self, t: float) -> bool:
        if self._wild < ARRHYTHMIA_STREAK:
            return False
        if t < self._arrhythmia_until:
            return False
        self._arrhythmia_until = t + ARRHYTHMIA_COOLDOWN_S
        self._wild = 0
        return True

    def bpm_mismatch(self) -> bool:
        if self.oshilog_bpm is None:
            return False
        return abs(self.bpm - int(self.oshilog_bpm)) >= MISMATCH_BPM
