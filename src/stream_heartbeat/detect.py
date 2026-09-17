"""心音の型とピーク検出。"""

from __future__ import annotations

import math
import wave
from collections import deque
from pathlib import Path

from stream_heartbeat.config import MAX_BPM

THUD_SECONDS = 0.09
BRIGHTNESS_MAX = 0.82
ZCR_MAX = 0.22
CORR_MIN = 0.45
BUNDLED_CORR_MIN = 0.08
ENV_ABS_MIN = 0.008
NOISE_INIT = 0.01
PAIR_SECONDS = 0.36
DEFAULT_INTERVAL = 0.8


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
    db = [y - mb for y in bb]
    dot = sum(x * y for x, y in zip(da, db))
    na = math.sqrt(sum(x * x for x in da))
    nb = math.sqrt(sum(y * y for y in db))
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
    if peak < ENV_ABS_MIN:
        return []
    thuds: list[list[float]] = []
    last_i = -10**9
    floor = max(peak * 0.35, ENV_ABS_MIN)
    for i, value in enumerate(env):
        if value < floor:
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


class CalibrationTemplate:
    def __init__(self, wave: list[float], waves: list[list[float]] | None = None) -> None:
        self.wave = wave
        self.waves = waves if waves else [wave]

    @classmethod
    def from_sessions(
        cls,
        sessions: list[list[float]],
        sample_rate: float = 16000.0,
    ) -> CalibrationTemplate | None:
        thuds: list[list[float]] = []
        for session in sessions:
            thuds.extend(extract_thuds(session, sample_rate))
        if not thuds:
            return None
        thuds.sort(key=lambda item: -_rms(item))
        picked = thuds[:8]
        length = max(len(s) for s in picked)
        acc = [0.0] * length
        for thud in picked:
            for i in range(length):
                j = min(len(thud) - 1, int(i * len(thud) / length))
                acc[i] += thud[j]
        scale = max(len(picked), 1)
        return cls([x / scale for x in acc], picked)

    def score(self, window: list[float]) -> float:
        return max(_cosine_demean(window, wave) for wave in self.waves)


class HeartSoundDetector:
    def __init__(
        self,
        template: CalibrationTemplate | None = None,
        corr_min: float = CORR_MIN,
    ) -> None:
        self.template = template
        self.corr_min = corr_min
        self.min_interval = 60.0 / MAX_BPM
        self._last_beat = -1e9
        self._last_interval = DEFAULT_INTERVAL
        self._prev_env = 0.0
        self._noise = NOISE_INIT
        self._peak = 0.04
        self._lp = 0.0
        self._hp = 0.0
        self._buf: deque[float] = deque()
        self._sumsq = 0.0

    def _refractory(self) -> float:
        pair = min(PAIR_SECONDS, 0.45 * self._last_interval)
        if self._last_interval >= 0.5:
            pair = max(pair, 0.32)
        return max(self.min_interval, pair)

    def feed(self, samples: list[float], t: float, sample_rate: float = 16000.0) -> list[float]:
        hits: list[float] = []
        dt = 1.0 / sample_rate if sample_rate else 0.001
        win = max(16, int(THUD_SECONDS * sample_rate))
        lp_a = 1.0 - math.exp(-2.0 * math.pi * 180.0 / max(sample_rate, 1.0))
        hp_a = 1.0 - math.exp(-2.0 * math.pi * 18.0 / max(sample_rate, 1.0))
        a_up = 1.0 - math.exp(-dt / 6.0)
        a_dn = 1.0 - math.exp(-dt / 0.25)
        peak_decay = math.exp(-dt / 2.2)
        for i, sample in enumerate(samples):
            self._lp += lp_a * (sample - self._lp)
            self._hp += hp_a * (self._lp - self._hp)
            band = self._lp - self._hp
            self._buf.append(band)
            self._sumsq += band * band
            if len(self._buf) > win:
                old = self._buf.popleft()
                self._sumsq -= old * old
            if len(self._buf) < win:
                continue
            if self._sumsq < 0.0:
                self._sumsq = 0.0
            env = math.sqrt(self._sumsq / win)
            if env < self._noise:
                self._noise += a_dn * (env - self._noise)
            else:
                self._noise += a_up * (env - self._noise)
            self._noise = max(self._noise, 1e-4)
            self._peak *= peak_decay
            self._peak = max(self._peak, env)
            denom = max(self._peak, self._noise * 4.0, 0.012)
            norm = env / denom
            onset = norm >= 0.42 and env > self._prev_env * 1.12 and self._prev_env <= env
            rising = norm >= 0.42 and self._prev_env < 0.42 * denom
            self._prev_env = 0.82 * self._prev_env + 0.18 * env
            sample_t = t + i * dt
            if not (onset or rising):
                continue
            if sample_t - self._last_beat < self._refractory():
                continue
            window = list(self._buf)
            if not looks_like_thud(window):
                continue
            if self.template is not None and self.corr_min > 0:
                if self.template.score(window) < self.corr_min:
                    continue
            if self._last_beat > -1e8:
                gap = sample_t - self._last_beat
                if gap > self.min_interval:
                    self._last_interval = 0.7 * self._last_interval + 0.3 * gap
            self._last_beat = sample_t
            hits.append(sample_t)
        return hits
