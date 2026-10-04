"""心音の型とピーク検出。"""

from __future__ import annotations

import math
from collections import deque

from stream_heartbeat.config import MAX_BPM
from stream_heartbeat.noise_gate import VOICE_KEEP, VOICE_RATE, looks_like_noise

THUD_SECONDS = 0.09
# 心音を聞く帯域（Hz）。上は 1 次の低域通過を 2 段重ねて切れを良くする。
# S1 の芯は 100 Hz より下にあり、話し声・キーボード・衣擦れの多くはこれより上にある
BAND_LO = 18.0
BAND_HI = 100.0
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
# 音色で S1 と S2 を見分ける。S2 は鋭く、S1 は鈍い。300 Hz 以上の割合（対数エネルギー比）は
# S2 のほうが高い。割合は、鳴り始めの直前 HF_TAU 秒から山（PEAK_WAIT）までのエネルギーで測る。
# 拍の時刻は鳴り始めのまま
HF_FC = 300.0
HF_TAU = 0.03
# 拍の音と、周期の途中に来た音（S2 のはず）の割合の差が、この値以上に開いた録音でだけ音色を使う
# （差が無い録音は今まで通り）
HF_SEP = 1.2
# 覚えた割合の更新の速さと、使い始めに要る観測数
HF_RATE = 0.25
HF_MIN_N = 3
# 周期の途中の音と拍の割合の差は、直近この個数の中央値で見る（雑音の 1 回に引きずられない）
HF_KEEP = 5
# 拍から「周期の途中」と数える範囲（周期に対する割合）
HF_MID = (0.3, 0.8)
# 拍が来ないまま周期のこの割合を過ぎてから S2 らしい音が来たら、S1 を取りこぼしたとみて、
# 収縮期ぶん戻した所に拍を置く
HF_RESCUE_AT = 1.3
# 取りこぼしを取り戻すのは、収縮期を引いた位置が前の拍から周期のこの範囲にあるときだけ
# （拍が何回も抜けたときは今まで通り）
HF_RESCUE_BAND = (0.8, 1.25)
# 何拍も抜けたあと、S2 らしい音を見送って S1 を待つ最大の回数
HF_GAP_SKIPS = 2
# この秒数、拍が無ければ覚えた割合は捨てる（別の人・別のマイクに切り替わっても居座らない）
HF_FORGET = 5.0
# 心音ではない音らしくても拍の候補に残す、リズムどおりの位置（前の拍からの周期に対する割合）
NOISE_ON_TIME = (0.8, 1.3)


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
    lp_a = 1.0 - math.exp(-2.0 * math.pi * BAND_HI / rate)
    hp_a = 1.0 - math.exp(-2.0 * math.pi * BAND_LO / rate)
    return lp_a, hp_a


def _hf_coeffs(sample_rate: float) -> tuple[float, float, float]:
    """生の波形にかける 2 次バターワースの高域通過 (HF_FC)。戻り値: (b0, a1, a2)。b1=-2*b0, b2=b0。
    サンプルレートが低くて使えないときは b0=0（割合はいつも同じ値になり、音色は使われない）。"""
    if sample_rate < 4.0 * HF_FC:
        return 0.0, 0.0, 0.0
    c = 1.0 / math.tan(math.pi * HF_FC / sample_rate)
    a0 = c * c + math.sqrt(2.0) * c + 1.0
    return c * c / a0, (2.0 - 2.0 * c * c) / a0, (c * c - math.sqrt(2.0) * c + 1.0) / a0


def band_pass(samples: list[float], sample_rate: float) -> list[float]:
    """検出と同じ帯域（BAND_LO〜BAND_HI）に絞る。覚えた型と聞こえた音を同じ条件で比べるため。"""
    lp_a, hp_a = _band_coeffs(sample_rate)
    lp = 0.0
    lp2 = 0.0
    hp = 0.0
    out: list[float] = []
    for sample in samples:
        lp += lp_a * (sample - lp)
        lp2 += lp_a * (lp - lp2)
        hp += hp_a * (lp2 - hp)
        out.append(lp2 - hp)
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


# 補正の録音は心音の所だけ残す。長い録音をそのまま積むと保存ファイルが膨らむ
CAL_SNIPPET_MAX_S = 1.0
CAL_SNIPPETS_PER_TAKE = 8
CAL_SNIPPETS_MAX = 48


def compact_calibration(
    sessions: list[list[float]], sample_rate: float = 16000.0
) -> list[list[float]]:
    """長い録音は大きい心音の塊だけに切り詰め、全体も新しい方から上限個に絞る。"""
    limit = int(CAL_SNIPPET_MAX_S * sample_rate)
    out: list[list[float]] = []
    for session in sessions:
        if len(session) <= limit:
            out.append(session)
            continue
        filtered = band_pass(session, sample_rate)
        thuds = extract_thuds(session, sample_rate, cut_from=filtered)
        thuds.sort(key=lambda item: -_rms(item))
        out.extend(thuds[:CAL_SNIPPETS_PER_TAKE])
    return out[-CAL_SNIPPETS_MAX:]


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
        self._lp2 = 0.0
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
        self._hf_sr = 0.0
        self._hf_coef = (0.0, 0.0, 0.0)
        self._hz1 = 0.0
        self._hz2 = 0.0
        self._hf_e = 0.0
        self._lo_e = 0.0
        self._tone_beat = 0.0
        self._tone_last = 0.0
        self._sep = 0.0
        self._gap_skips = 0
        self._diffs: deque[float] = deque(maxlen=HF_KEEP)
        self._tone_on = False
        self._tn_beat = 0
        self._tn_mid = 0
        self._tone_t = -1e9
        self._sys = 0.0
        # 心音ではない音をよける（noise_gate）。間引いて覚えた 300 Hz 以上で見分ける
        self._vacc = 0.0
        self._vcount = 0
        self._voice: deque[float] = deque()
        self._voice_sr = 0.0
        self._voice_rate = VOICE_RATE

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
        if sample_rate != self._hf_sr:
            self._hf_sr = sample_rate
            self._hf_coef = _hf_coeffs(sample_rate)
        hf_b0, hf_a1, hf_a2 = self._hf_coef
        hf_b1 = -2.0 * hf_b0
        hf_k = 1.0 - math.exp(-dt / HF_TAU)
        hf_pre = HF_TAU / dt  # 直前 HF_TAU 秒ぶんのサンプル数
        v_dec = max(1, int(round(sample_rate / VOICE_RATE))) if sample_rate else 1
        if sample_rate != self._voice_sr:
            self._voice_sr = sample_rate
            self._voice_rate = (sample_rate or VOICE_RATE) / v_dec
            self._voice = deque(maxlen=max(8, int(VOICE_KEEP * self._voice_rate)))
        voice = self._voice
        vacc = self._vacc
        vcount = self._vcount
        for i, sample in enumerate(samples):
            self._lp += lp_a * (sample - self._lp)
            self._lp2 += lp_a * (self._lp - self._lp2)
            self._hp += hp_a * (self._lp2 - self._hp)
            band = self._lp2 - self._hp
            # 300 Hz 以上と、いつもの帯域のエネルギー。直前 HF_TAU 秒ぶんは常に均しておき、
            # 音が鳴り始めたらその音の間だけ積み上げる
            hy = hf_b0 * sample + self._hz1
            self._hz1 = hf_b1 * sample - hf_a1 * hy + self._hz2
            self._hz2 = hf_b0 * sample - hf_a2 * hy
            self._hf_e += hf_k * (hy * hy - self._hf_e)
            self._lo_e += hf_k * (band * band - self._lo_e)
            # 声やカチッを見分けるため、300 Hz 以上を間引いて覚えておく
            vacc += hy
            vcount += 1
            if vcount >= v_dec:
                voice.append(vacc / v_dec)
                vacc = 0.0
                vcount = 0
            if self._pending is not None:
                self._pending[3] += hy * hy
                self._pending[4] += band * band
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
                    # サンプルレートが低くて 300 Hz 以上が測れないときは、音色を使わない（いつも 0）
                    tone = 0.0
                    if hf_b0 > 0.0:
                        tone = math.log((pending[3] + 1e-12) / (pending[4] + 1e-12))
                    # 300 Hz 以上が測れないサンプルレートでは雑音も見分けない
                    noisy = hf_b0 > 0.0 and looks_like_noise(list(self._voice), self._voice_rate)
                    beat_t = self._accept(pending[0], pending[1], tone, noisy)
                    if beat_t is not None:
                        hits.append(beat_t)
                continue
            if not (onset or rising) or sample_t < self._block_until:
                continue
            window = list(self._buf)
            if not looks_like_thud(window):
                continue
            if self.template is not None and self.corr_min > 0:
                if self.template.score(window) < self.corr_min:
                    continue
            self._pending = [
                sample_t,
                env,
                sample_t + PEAK_WAIT,
                self._hf_e * hf_pre,
                self._lo_e * hf_pre,
            ]
        self._vacc = vacc
        self._vcount = vcount
        return hits

    def _level(self) -> float:
        """最近の拍の山の大きさ（中央値）。まだ無いときは 0。"""
        return self._level_mid

    def _push_level(self, peak: float) -> None:
        self._levels.append(peak)
        if len(self._levels) >= 3:
            self._level_mid = sorted(self._levels)[len(self._levels) // 2]

    def _accept(
        self, sample_t: float, peak: float, tone: float = 0.0, noisy: bool = False
    ) -> float | None:
        """山まで聞いた1つの音を、拍として数えるか決める。数えるなら拍の時刻、数えないなら None。
        noisy は心音ではない音らしいか（noise_gate）。リズムどおりの位置に来た音には使わない
        （話しながらの心音は雑音が混ざって見えるが、捨てると拍が抜ける）。"""
        if noisy and not self._on_time(sample_t):
            return None
        raw_dt = sample_t - self._last_raw_t
        if raw_dt >= self.min_interval:
            if self._last_raw_t > -1e8:
                self._update_pair_mode(raw_dt)
            self._last_raw_t = sample_t
        since = sample_t - self._last_beat
        level = self._level()
        period = self._period
        beat_t = sample_t
        rescued = False
        if period > 0:
            act = self._tone_action(sample_t, tone, period)
            if act == "flip":
                if level > 0 and peak < QUIET_LEVEL * level:
                    act = "pass"  # 小さすぎる音には乗り換えない
                else:
                    self._flip(sample_t, peak, tone, period)
                    return sample_t
            if since < self._refractory():
                # 小さな雑音で拍を取ったすぐ後に本物のドッが来たら、数え直す（表示は増やさない）。
                # ただし数え直す先が S2 らしい音なら数え直さない
                if (
                    since <= REANCHOR_SECONDS
                    and peak >= REANCHOR_GAIN * self._last_peak
                    and act != "skip"
                ):
                    self._last_beat = sample_t
                    self._last_peak = peak
                    self._push_level(peak)
                self._note_mid(since, tone, period)
                return None
            if act == "skip":
                self._note_mid(since, tone, period)
                return None
            if level > 0:
                need = EARLY_LEVEL if since < EARLY_SHARE * period else QUIET_LEVEL
                if peak < need * level:
                    return None
            if act == "rescue":
                beat_t = sample_t - self._sys
                rescued = True
        else:
            if 0.20 <= since <= 0.33 and peak < self._last_peak * 0.85:
                return None
            if 0.33 < since <= 0.55 and peak < self._last_peak * 0.55:
                return None
            # クリック拍の記憶は、いまの拍の長さが測れていないときだけ使う
            # （安静時のクリックのせいで運動後の速い拍を半分にしない）
            if 0.45 <= self.tap_interval <= 1.2 and since < min(self.tap_interval * 0.72, 0.55):
                return None
            if since < self._refractory():
                return None
        if self._last_beat > -1e8 and beat_t - self._last_beat > self.min_interval:
            self._last_interval = 0.7 * self._last_interval + 0.3 * (beat_t - self._last_beat)
        self._last_beat = beat_t
        self._tone_t = beat_t
        self._gap_skips = 0
        if rescued:
            # S2 から置き直した拍では、S2 の大きさと割合を S1 のものとして覚えない
            self._tone_last = self._tone_beat
        else:
            self._last_peak = peak
            self._push_level(peak)
            self._note_beat(tone)
        return beat_t

    def _on_time(self, t: float) -> bool:
        """測れている 1 拍の長さから見て、次の拍が来るはずの位置か。"""
        period = self._period
        if period <= 0.0 or self._last_beat < -1e8:
            return False
        since = t - self._last_beat
        return NOISE_ON_TIME[0] * period <= since <= NOISE_ON_TIME[1] * period

    def _note_beat(self, tone: float) -> None:
        """拍にした音の高域の割合を覚える（直前の拍のぶんと、ならしたぶん）。"""
        self._tone_last = tone
        if self._tn_beat == 0:
            self._tone_beat = tone
        else:
            near = min(max(tone, self._tone_beat - 3.0), self._tone_beat + 3.0)
            self._tone_beat += HF_RATE * (near - self._tone_beat)
        self._tn_beat = min(self._tn_beat + 1, 1000)

    def _note_mid(self, since: float, tone: float, period: float) -> None:
        """拍にしなかった周期の途中の音（S2 のはず）について、直前の拍との割合の差（sep）と、
        拍からの時間（収縮期）を覚える。擦れなどで割合が全体にずれても、直前の拍との差は保たれる。"""
        if self._tn_beat == 0 or not HF_MID[0] * period <= since <= HF_MID[1] * period:
            return
        self._diffs.append(min(max(tone - self._tone_last, -5.0), 5.0))
        self._sep = sorted(self._diffs)[len(self._diffs) // 2]
        if self._tn_mid == 0:
            self._sys = since
        else:
            self._sys += HF_RATE * (since - self._sys)
        self._tn_mid = len(self._diffs)

    def _tone_action(self, t: float, tone: float, period: float) -> str:
        """音の高域の割合から見た、この音の扱い。
        pass: 音色では決めない / skip: S2 らしいので拍にしない /
        rescue: S1 を取りこぼしたので、収縮期ぶん戻して拍にする /
        flip: 拍が S2 側に乗っているので、S1 らしい音に乗り換える。"""
        if self._tn_beat < HF_MIN_N or self._tn_mid < HF_MIN_N:
            return "pass"
        ref = self._last_beat if self._last_beat > -1e8 else self._tone_t
        if t - ref > HF_FORGET:
            self._tn_beat = 0
            self._tn_mid = 0
            self._diffs.clear()
            self._tone_on = False
            return "pass"
        since = t - ref
        sep = self._sep
        # 使い始めは HF_SEP 以上の差が要るが、使い出したら半分まで下がっても使い続ける
        # （境目でばたつかない）
        if abs(sep) < (0.5 * HF_SEP if self._tone_on else HF_SEP):
            self._tone_on = False
            return "pass"
        self._tone_on = True
        in_mid = HF_MID[0] * period <= since <= HF_MID[1] * period and self._last_beat > -1e8
        if sep < 0:
            if in_mid and tone - self._tone_last <= 0.5 * sep:
                return "flip"
            return "pass"
        if in_mid:
            # 周期の途中の音は、直前の拍との差で比べる
            return "skip" if tone - self._tone_last > 0.5 * sep else "pass"
        diff = tone - self._tone_beat
        if since < HF_RESCUE_AT * period:
            # 次の拍のはずの位置にある音は、よほど S2 らしいときだけ見送る
            return "skip" if diff > sep else "pass"
        # 拍が来ないまま過ぎた。ちょうど 1 拍ぶん取りこぼしたと言える位置にある S2 らしい音は、
        # 収縮期ぶん戻して拍にする
        gap = since - self._sys
        if diff > 0.5 * sep and HF_RESCUE_BAND[0] * period <= gap <= HF_RESCUE_BAND[1] * period:
            return "rescue"
        # 何拍も抜けたあとの最初の音は、拍か S2 か分からない。
        # よほど S2 らしければ、数回だけ見送って S1 を待つ
        if diff > sep and self._gap_skips < HF_GAP_SKIPS:
            self._gap_skips += 1
            return "skip"
        return "pass"

    def _flip(self, t: float, peak: float, tone: float, period: float) -> None:
        """S2 に乗っていた拍を、直後の S1 に乗せ替える（拍と周期の途中の音の役を入れ替える）。"""
        since = t - (self._last_beat if self._last_beat > -1e8 else self._tone_t)
        self._tone_beat = tone
        self._tone_last = tone
        self._diffs = deque((-d for d in self._diffs), maxlen=HF_KEEP)
        self._sep = -self._sep
        self._sys = min(max(period - since, 0.12), 0.6)
        self._gap_skips = 0
        self._last_beat = t
        self._tone_t = t
        self._last_peak = peak
        self._push_level(peak)

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
