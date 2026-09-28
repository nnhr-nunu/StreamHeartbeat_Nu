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
# 覚えた型との照合は時間合わせが無く、本物の拍を落とすだけだったので止めている（D-2 で作り直す）
BUNDLED_CORR_MIN = 0.0
ENV_ABS_MIN = 0.008
NOISE_INIT = 0.01
PAIR_SECONDS = 0.36
DEFAULT_INTERVAL = 0.8
# 数秒ぶんの音の強弱の繰り返しから1拍の長さを測る（2音目を別の拍と数えないため）
RHYTHM_RATE = 50.0
RHYTHM_SECONDS = 6.0
RHYTHM_MIN_SECONDS = 3.0
RHYTHM_MAX_LAG = 2.0
RHYTHM_EVERY = 0.5
RHYTHM_CONF = 0.25
RHYTHM_PICK = 0.75
RHYTHM_ALTERNATE = 0.12
# クリック拍に合わせて倍にするのは、倍がクリック拍の ±20% に入るときだけ
# （運動後の速い拍を半分にしない）
RHYTHM_HINT_BAND = math.log(1.2)
# 176 BPM を超える候補で、倍の長さもほぼ同じ強さなら倍を1拍とする
# （速い拍や失神前後では、ドッとクンがほぼ等間隔に並んで半分の長さに見える）
RHYTHM_FAST_LAG = 0.34
RHYTHM_FAST_MARGIN = 0.3
RHYTHM_GUARD = 0.55
RHYTHM_CAP = 1.6
# 音の大きさは鳴り始めでなく山で比べる（鳴り始めはどの音も閾値ちょうどで差が出ない）。
# 山を待つのはこの秒数まで。拍の時刻は鳴り始めのまま
PEAK_WAIT = 0.06
# 最近の拍の山の大きさ（中央値）に対する割合
LEVEL_KEEP = 8
EARLY_SHARE = 0.85
EARLY_LEVEL = 0.75
QUIET_LEVEL = 0.22
# 直前の拍よりはっきり大きい音がすぐ後に来たら、そちらを本当の拍とみなして数え直す
REANCHOR_GAIN = 1.8
REANCHOR_SECONDS = 0.3
# 体の動きなどの大きな一発で、しばらく本物の拍が小さく見えて落ちないように
PEAK_CAP = 2.5


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


def estimate_period(
    env: list[float],
    rate: float,
    min_lag: float,
    max_lag: float,
    hint: float = 0.0,
) -> float:
    """包絡の自己相関から1拍の長さ（秒）。はっきりしないときは 0。

    ドッ・クンの間隔（片側だけ一致）より、1拍ぶんずらした所（両方一致）の方が強く出る。
    同じくらい強い候補のうち一番短いものを選び、2拍ぶんを1拍と取り違えないようにする。
    ただし倍の長さの方がはっきり強いときは、強弱が交互に来るドッ・クンなので倍を1拍とする。
    強さも間隔もそろった音は速い拍のまま（まとめない）。
    どちらとも言えないときは、hint（録音中のクリック拍の間隔）に近い方を選ぶ。
    176 BPM を超える候補で倍もほぼ同じ強さなら、等間隔に並んだドッ・クンとみて倍を取る。
    """
    n = len(env)
    lo = max(1, int(min_lag * rate))
    hi = min(n - int(rate) - 2, int(max_lag * rate))
    if hi <= lo:
        return 0.0
    # 体の動きなどの大きな一発に引きずられないよう、音の山の中央値の 1.6 倍で頭打ちにする
    tops = sorted(
        env[i] for i in range(1, n - 1) if env[i] >= env[i - 1] and env[i] > env[i + 1]
    )
    cap = RHYTHM_CAP * tops[len(tops) // 2] if tops else max(env)
    x = [min(v, cap) for v in env]
    mean = sum(x) / n
    x = [v - mean for v in x]
    scores = [0.0] * (hi + 2)
    for lag in range(lo - 1, hi + 2):
        a = x[: n - lag]
        b = x[lag:]
        na = sum(p * p for p in a)
        nb = sum(q * q for q in b)
        if na > 1e-12 and nb > 1e-12:
            scores[lag] = sum(p * q for p, q in zip(a, b)) / math.sqrt(na * nb)
    peaks = [
        lag
        for lag in range(lo, hi + 1)
        if scores[lag] >= scores[lag - 1] and scores[lag] > scores[lag + 1]
    ]
    if not peaks:
        return 0.0
    best = max(scores[lag] for lag in peaks)
    if best < RHYTHM_CONF:
        return 0.0
    lag = next(lag for lag in peaks if scores[lag] >= RHYTHM_PICK * best)
    doubles = [p for p in peaks if abs(p - 2 * lag) <= 3]
    if doubles:
        double = max(doubles, key=lambda p: scores[p])
        if scores[double] >= scores[lag] + RHYTHM_ALTERNATE:
            lag = double
        elif (
            hint > 0
            and scores[double] >= scores[lag] - RHYTHM_ALTERNATE
            and abs(math.log(double / (hint * rate))) < RHYTHM_HINT_BAND
        ):
            lag = double
        elif (
            lag < RHYTHM_FAST_LAG * rate
            and scores[double] >= scores[lag] - RHYTHM_FAST_MARGIN
            and not (0 < hint < RHYTHM_FAST_LAG * 1.25)
        ):
            lag = double
    y0, y1, y2 = scores[lag - 1], scores[lag], scores[lag + 1]
    den = y0 - 2.0 * y1 + y2
    off = 0.5 * (y0 - y2) / den if abs(den) > 1e-9 else 0.0
    return (lag + max(-0.5, min(0.5, off))) / rate


def _band_coeffs(sample_rate: float) -> tuple[float, float]:
    rate = max(sample_rate, 1.0)
    lp_a = 1.0 - math.exp(-2.0 * math.pi * 180.0 / rate)
    hp_a = 1.0 - math.exp(-2.0 * math.pi * 18.0 / rate)
    return lp_a, hp_a


def band_pass(samples: list[float], sample_rate: float) -> list[float]:
    """検出と同じ帯域（18〜180 Hz）に絞る。覚えた型と聞こえた音を同じ条件で比べるため。"""
    lp_a, hp_a = _band_coeffs(sample_rate)
    lp = 0.0
    hp = 0.0
    out: list[float] = []
    for sample in samples:
        lp += lp_a * (sample - lp)
        hp += hp_a * (lp - hp)
        out.append(lp - hp)
    return out


def extract_thuds(
    samples: list[float],
    sample_rate: float,
    cut_from: list[float] | None = None,
) -> list[list[float]]:
    """心音らしい塊を切り出す。cut_from を渡すと、同じ位置をそちらから切る。"""
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
            thuds.append(chunk if cut_from is None else cut_from[start:end])
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
            # 検出側は帯域を絞った音で比べるので、型も同じく絞った音から切る
            filtered = band_pass(session, sample_rate)
            thuds.extend(extract_thuds(session, sample_rate, cut_from=filtered))
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

    @classmethod
    def merge(cls, *templates: CalibrationTemplate | None) -> CalibrationTemplate | None:
        waves: list[list[float]] = []
        for tmpl in templates:
            if tmpl is None:
                continue
            waves.extend(tmpl.waves)
        if not waves:
            return None
        return cls(waves[0], waves)

    def score(self, window: list[float]) -> float:
        return max(_cosine_demean(window, wave) for wave in self.waves)


class HeartSoundDetector:
    def __init__(
        self,
        template: CalibrationTemplate | None = None,
        corr_min: float = CORR_MIN,
        tap_interval: float = 0.0,
    ) -> None:
        self.template = template
        self.corr_min = corr_min
        self.tap_interval = tap_interval
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
        self._last_raw_t = -1e9
        self._gaps: deque[float] = deque(maxlen=8)
        self._pair_mode = False
        self._primed = False
        self._rhythm: deque[float] = deque(maxlen=int(RHYTHM_SECONDS * RHYTHM_RATE))
        self._rhythm_step = 0
        self._rhythm_tick = 0
        self._period = 0.0
        self._pending: list[float] | None = None
        self._block_until = -1e9
        self._last_peak = 0.0
        self._levels: deque[float] = deque(maxlen=LEVEL_KEEP)
        self._level_mid = 0.0

    @property
    def period(self) -> float:
        """音の繰り返しから測った1拍の長さ（秒）。まだ分からないときは 0。"""
        return self._period

    def _refractory(self) -> float:
        if self._period > 0:
            return max(self.min_interval, RHYTHM_GUARD * self._period)
        if self.tap_interval >= 0.25:
            return max(self.min_interval, min(PAIR_SECONDS, self.tap_interval * 0.55))
        pair = min(PAIR_SECONDS, 0.45 * self._last_interval)
        if self._last_interval >= 0.5:
            pair = max(pair, 0.32)
        if self._pair_mode:
            pair = max(pair, 0.42)
        return max(self.min_interval, pair)

    def _update_pair_mode(self, gap: float) -> None:
        if self.tap_interval >= 0.25:
            self._pair_mode = self.tap_interval >= 0.55
            return
        self._gaps.append(gap)
        if len(self._gaps) < 4:
            return
        shorts = sum(1 for item in self._gaps if item < 0.42)
        longs = sum(1 for item in self._gaps if item >= 0.50)
        self._pair_mode = shorts >= 2 and longs >= 2

    def feed(self, samples: list[float], t: float, sample_rate: float = 16000.0) -> list[float]:
        hits: list[float] = []
        dt = 1.0 / sample_rate if sample_rate else 0.001
        win = max(16, int(THUD_SECONDS * sample_rate))
        lp_a, hp_a = _band_coeffs(sample_rate)
        a_up = 1.0 - math.exp(-dt / 6.0)
        a_dn = 1.0 - math.exp(-dt / 0.25)
        peak_decay = math.exp(-dt / 2.2)
        rhythm_hop = max(1, int(round(sample_rate / RHYTHM_RATE)))
        rhythm_every = int(RHYTHM_EVERY * RHYTHM_RATE)
        rhythm_min = int(RHYTHM_MIN_SECONDS * RHYTHM_RATE)
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
            sample_t = t + i * dt
            if not self._primed:
                # 最初の窓は「上がり始め」ではない。いまの音量を下地にして、
                # 起動直後の空打ちで本物の次の拍を消さない
                self._primed = True
                self._noise = max(env, 1e-4)
                self._prev_env = env
                continue
            self._rhythm_step += 1
            if self._rhythm_step >= rhythm_hop:
                self._rhythm_step = 0
                self._rhythm.append(env)
                self._rhythm_tick += 1
                if self._rhythm_tick >= rhythm_every and len(self._rhythm) >= rhythm_min:
                    self._rhythm_tick = 0
                    self._period = estimate_period(
                        list(self._rhythm),
                        RHYTHM_RATE,
                        self.min_interval,
                        RHYTHM_MAX_LAG,
                        hint=self.tap_interval if self.tap_interval >= 0.25 else 0.0,
                    )
            if env < self._noise:
                self._noise += a_dn * (env - self._noise)
            else:
                self._noise += a_up * (env - self._noise)
            self._noise = max(self._noise, 1e-4)
            self._peak *= peak_decay
            level = self._level()
            capped = min(env, PEAK_CAP * level) if level > 0 else env
            self._peak = max(self._peak, capped)
            denom = max(self._peak, self._noise * 4.0, 0.012)
            norm = env / denom
            onset = norm >= 0.42 and env > self._prev_env * 1.12 and self._prev_env <= env
            rising = norm >= 0.42 and self._prev_env < 0.42 * denom
            self._prev_env = 0.82 * self._prev_env + 0.18 * env
            pending = self._pending
            if pending is not None:
                pending[1] = max(pending[1], env)
                if sample_t >= pending[2] or env < 0.7 * pending[1]:
                    self._pending = None
                    self._block_until = sample_t + 0.05
                    if self._accept(pending[0], pending[1]):
                        hits.append(pending[0])
                continue
            if not (onset or rising) or sample_t < self._block_until:
                continue
            window = list(self._buf)
            if not looks_like_thud(window):
                continue
            if self.template is not None and self.corr_min > 0:
                if self.template.score(window) < self.corr_min:
                    continue
            self._pending = [sample_t, env, sample_t + PEAK_WAIT]
        return hits

    def _level(self) -> float:
        """最近の拍の山の大きさ（中央値）。まだ無いときは 0。"""
        return self._level_mid

    def _push_level(self, peak: float) -> None:
        self._levels.append(peak)
        if len(self._levels) >= 3:
            self._level_mid = sorted(self._levels)[len(self._levels) // 2]

    def _accept(self, sample_t: float, peak: float) -> bool:
        """山まで聞いた1つの音を、拍として数えるか決める。"""
        raw_dt = sample_t - self._last_raw_t
        if raw_dt >= self.min_interval:
            if self._last_raw_t > -1e8:
                self._update_pair_mode(raw_dt)
            self._last_raw_t = sample_t
        since = sample_t - self._last_beat
        level = self._level()
        period = self._period
        if period > 0:
            if since < self._refractory():
                # 小さな雑音で拍を取ったすぐ後に本物のドッが来たら、数え直す（表示は増やさない）
                if since <= REANCHOR_SECONDS and peak >= REANCHOR_GAIN * self._last_peak:
                    self._last_beat = sample_t
                    self._last_peak = peak
                    self._push_level(peak)
                return False
            if level > 0:
                need = EARLY_LEVEL if since < EARLY_SHARE * period else QUIET_LEVEL
                if peak < need * level:
                    return False
        else:
            if 0.20 <= since <= 0.33 and peak < self._last_peak * 0.85:
                return False
            if 0.33 < since <= 0.55 and peak < self._last_peak * 0.55:
                return False
            # クリック拍の記憶は、いまの拍の長さが測れていないときだけ使う
            # （安静時のクリックのせいで運動後の速い拍を半分にしない）
            if 0.45 <= self.tap_interval <= 1.2 and since < min(self.tap_interval * 0.72, 0.55):
                return False
            if since < self._refractory():
                return False
        if self._last_beat > -1e8 and since > self.min_interval:
            self._last_interval = 0.7 * self._last_interval + 0.3 * since
        self._last_beat = sample_t
        self._last_peak = peak
        self._push_level(peak)
        return True

    def unlock(self) -> None:
        """検出ロスト後に、遅い間隔の記憶で次の拍を落とさない。"""
        self._last_interval = DEFAULT_INTERVAL
        self._pair_mode = False
        self._gaps.clear()
        self._last_beat = -1e9
        self._last_raw_t = -1e9
        self._peak = min(self._peak, 0.08)
        self._levels.clear()
        self._level_mid = 0.0
        self._pending = None
