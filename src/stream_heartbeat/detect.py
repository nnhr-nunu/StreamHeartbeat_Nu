"""心音の型とピーク検出。高い短い音（指パッチン等）は捨てる。"""

from __future__ import annotations

import math
import wave
from pathlib import Path

from stream_heartbeat.config import MAX_BPM, MIN_BPM

THUD_SECONDS = 0.09
BRIGHTNESS_MAX = 0.82
ZCR_MAX = 0.22
CORR_MIN = 0.45


def envelope_rms(samples: list[float], hop: int) -> list[float]:
    if hop <= 0:
        return []
    out: list[float] = []
    width = max(hop, 8)
    i = 0
    while i + width <= len(samples):
        chunk = samples[i : i + width]
        out.append(_rms(chunk))
        i += hop
    return out


def _rms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / len(samples))


def zero_crossing_rate(samples: list[float]) -> float:
    if len(samples) < 2:
        return 0.0
    crosses = 0
    for a, b in zip(samples, samples[1:]):
        if a == 0 or b == 0:
            continue
        if (a > 0) != (b > 0):
            crosses += 1
    return crosses / (len(samples) - 1)


def brightness(samples: list[float]) -> float:
    if len(samples) < 3:
        return 0.0
    diffs = [samples[i] - samples[i - 1] for i in range(1, len(samples))]
    return _rms(diffs) / (_rms(samples) + 1e-9)


def looks_like_thud(samples: list[float]) -> bool:
    if len(samples) < 8:
        return False
    return brightness(samples) <= BRIGHTNESS_MAX and zero_crossing_rate(samples) <= ZCR_MAX


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


def extract_thuds(samples: list[float], sample_rate: float) -> list[list[float]]:
    if not samples or sample_rate <= 0:
        return []
    hop = max(1, int(0.01 * sample_rate))
    width = max(hop, int(THUD_SECONDS * sample_rate))
    env = envelope_rms(samples, hop)
    if not env:
        return []
    peak = max(env)
    if peak < 0.04:
        return []
    thuds: list[list[float]] = []
    last_i = -width
    for i, value in enumerate(env):
        if value < peak * 0.45:
            continue
        center = i * hop
        if center - last_i < int(sample_rate * 60.0 / MAX_BPM):
            continue
        start = max(0, center - width // 2)
        end = min(len(samples), start + width)
        chunk = samples[start:end]
        if looks_like_thud(chunk):
            thuds.append(chunk)
            last_i = center
    return thuds


class CalibrationTemplate:
    def __init__(self, wave: list[float]) -> None:
        self.wave = wave

    @classmethod
    def from_sessions(
        cls,
        sessions: list[list[float]],
        sample_rate: float = 16000.0,
    ) -> CalibrationTemplate:
        thuds: list[list[float]] = []
        for session in sessions:
            thuds.extend(extract_thuds(session, sample_rate) or ([session] if session else []))
        if not thuds:
            return cls([1.0])
        length = max(len(s) for s in thuds)
        acc = [0.0] * length
        for thud in thuds:
            for i in range(length):
                j = min(len(thud) - 1, int(i * len(thud) / length))
                acc[i] += thud[j]
        scale = max(len(thuds), 1)
        return cls([x / scale for x in acc])


def load_wav_mono(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("16bit WAV only")
    samples: list[float] = []
    step = channels * 2
    for i in range(0, len(frames) - 1, step):
        raw = int.from_bytes(frames[i : i + 2], "little", signed=True)
        samples.append(raw / 32768.0)
    return samples


class HeartSoundDetector:
    def __init__(self, template: CalibrationTemplate | None = None) -> None:
        self.template = template
        self.min_interval = 60.0 / MAX_BPM
        self._last_beat = -1e9
        self._prev_env = 0.0
        self._lp = 0.0
        self._hp = 0.0
        self._buf: list[float] = []

    def feed(self, samples: list[float], t: float, sample_rate: float = 16000.0) -> list[float]:
        hits: list[float] = []
        dt = 1.0 / sample_rate if sample_rate else 0.001
        win = max(16, int(THUD_SECONDS * sample_rate))
        lp_a = 1.0 - math.exp(-2.0 * math.pi * 180.0 / max(sample_rate, 1.0))
        hp_a = 1.0 - math.exp(-2.0 * math.pi * 18.0 / max(sample_rate, 1.0))
        for i, sample in enumerate(samples):
            self._lp += lp_a * (sample - self._lp)
            self._hp += hp_a * (self._lp - self._hp)
            band = self._lp - self._hp
            self._buf.append(band)
            if len(self._buf) > win * 3:
                self._buf = self._buf[-win * 3 :]
            if len(self._buf) < win:
                continue
            window = self._buf[-win:]
            env = _rms(window)
            onset = env > 0.045 and env > self._prev_env * 1.35 and self._prev_env <= env
            rising = env > 0.045 and self._prev_env <= 0.045 * 1.05
            self._prev_env = 0.85 * self._prev_env + 0.15 * env
            sample_t = t + i * dt
            if not (onset or rising):
                continue
            if sample_t - self._last_beat < self.min_interval:
                continue
            if sample_t - self._last_beat < 60.0 / MIN_BPM and env < 0.08:
                continue
            if not looks_like_thud(window):
                continue
            if self.template is not None:
                corr = _cosine_demean(window, self.template.wave)
                if corr < CORR_MIN:
                    continue
            self._last_beat = sample_t
            hits.append(sample_t)
        return hits
