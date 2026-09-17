"""心音の型とピーク検出。"""

from __future__ import annotations

import math

from stream_heartbeat.config import MAX_BPM


def envelope_rms(samples: list[float], hop: int) -> list[float]:
    if hop <= 0:
        return []
    out: list[float] = []
    width = max(hop, 8)
    i = 0
    while i + width <= len(samples):
        chunk = samples[i : i + width]
        out.append(math.sqrt(sum(x * x for x in chunk) / len(chunk)))
        i += hop
    return out


def _cosine_demean(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    aa = a[:n]
    bb = b[:n]
    ma = sum(aa) / n
    mb = sum(bb) / n
    da = [x - ma for x in aa]
    db = [x - mb for x in bb]
    dot = sum(x * y for x, y in zip(da, db))
    na = math.sqrt(sum(x * x for x in da))
    nb = math.sqrt(sum(x * x for x in db))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


class CalibrationTemplate:
    def __init__(self, wave: list[float]) -> None:
        self.wave = wave

    @classmethod
    def from_sessions(cls, sessions: list[list[float]]) -> CalibrationTemplate:
        if not sessions:
            return cls([1.0])
        length = max(len(s) for s in sessions)
        acc = [0.0] * length
        for session in sessions:
            if not session:
                continue
            for i in range(length):
                src = i * len(session) / length
                j = min(len(session) - 1, int(src))
                acc[i] += session[j]
        scale = max(len(sessions), 1)
        return cls([x / scale for x in acc])


class HeartSoundDetector:
    def __init__(self, template: CalibrationTemplate | None = None) -> None:
        self.template = template
        self.min_interval = 60.0 / MAX_BPM
        self._last_beat = -1e9
        self._prev_env = 0.0
        self._buf: list[float] = []

    def feed(self, samples: list[float], t: float, sample_rate: float = 16000.0) -> list[float]:
        if self.template is not None:
            corr = _cosine_demean(samples, self.template.wave)
            if corr > 0.6 and t - self._last_beat >= self.min_interval:
                self._last_beat = t
                return [t]
            return []

        hits: list[float] = []
        dt = 1.0 / sample_rate if sample_rate else 0.001
        for i, sample in enumerate(samples):
            self._buf.append(sample)
            if len(self._buf) > 64:
                self._buf = self._buf[-64:]
            if len(self._buf) < 20:
                continue
            env = math.sqrt(sum(x * x for x in self._buf[-20:]) / 20)
            onset = env > 0.25 and self._prev_env <= 0.25
            self._prev_env = env
            sample_t = t + i * dt
            if onset and sample_t - self._last_beat >= self.min_interval:
                self._last_beat = sample_t
                hits.append(sample_t)
        return hits
