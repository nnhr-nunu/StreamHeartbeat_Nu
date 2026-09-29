"""心音ではない音（話し声・キーボード）を、拍の候補から外すための見分け方。

聴診器やマイクによって、同じ心音でも高い音の割合は大きく違う（ベル面とダイヤフラム面、
電子聴診器の帯域、胸当ての押し当て方）。そこで、音の大きさや高い音の割合そのものではなく、
どの機材でも同じように出る形で見分ける。どちらも、その音の所で急に強まったときだけ雑音とみなす
（話しながら・打ちながらの心音には、前から続く声やカチッが混ざって見えるが、それは捨てない）。

  * 声らしさ  300 Hz 以上が、声の高さ（80〜400 Hz）の周期で繰り返している（有声の話し声）
  * 鋭さ      300 Hz 以上の山がとがっている（キーボードのカチッ）

衣擦れや低い話し声は、心音を聞く帯域を低く絞ること（detect.BAND_HI）で大半を落とす。
"""

from __future__ import annotations

import math
import operator

# 300 Hz 以上を 4 kHz に間引いて覚える。山まで聞いた時点の直前 VOICE_NOW 秒を「その音」、
# さらに前の VOICE_BEFORE 秒を「前」として比べる
VOICE_RATE = 4000.0
VOICE_NOW = 0.08
VOICE_BEFORE = 0.25
VOICE_KEEP = VOICE_NOW + VOICE_BEFORE + 0.05
# 声らしさ: 2.5〜12.5 ms の遅れの自己相関の最大
VOICE_LAGS = (0.0025, 0.0125)
# 雑音とみなす境目。声らしさと、前から強まった倍率（エネルギー）
NOISE_VOICING = 0.8
NOISE_VOICE_RISE = 2.0
# 鋭さ（300 Hz 以上の山 / 実効値）と、前から強まった倍率
NOISE_CREST = 9.0
NOISE_HF_RISE = 4.0


def voicing(samples: list[float], rate: float) -> float:
    """声の高さの周期での繰り返しの強さ（正規化自己相関の最大、0〜1）。"""
    lo = max(1, int(VOICE_LAGS[0] * rate))
    hi = int(VOICE_LAGS[1] * rate)
    n = len(samples)
    if n < hi * 2:
        return 0.0
    prefix = [0.0]
    for v in samples:
        prefix.append(prefix[-1] + v * v)
    best = 0.0
    for lag in range(lo, hi + 1):
        den = math.sqrt(prefix[n - lag] * (prefix[n] - prefix[lag]))
        if den <= 1e-18:
            continue
        num = sum(map(operator.mul, samples[: n - lag], samples[lag:]))
        best = max(best, num / den)
    return best


def looks_like_noise(kept: list[float], rate: float) -> bool:
    """間引いて覚えた 300 Hz 以上（古い順）の最後が、急に強まった声かカチッという音か。"""
    take = int(VOICE_NOW * rate)
    before = int(VOICE_BEFORE * rate)
    now = kept[-take:]
    prior = kept[-take - before : -take]
    if len(now) < take or not prior:
        return False
    now_e = sum(v * v for v in now) / len(now)
    if now_e <= 0.0:
        return False
    rise = now_e / max(sum(v * v for v in prior) / len(prior), 1e-15)
    if rise <= min(NOISE_VOICE_RISE, NOISE_HF_RISE):
        return False
    crest = max(abs(v) for v in now) / math.sqrt(now_e)
    if crest > NOISE_CREST and rise > NOISE_HF_RISE:
        return True
    return rise > NOISE_VOICE_RISE and voicing(now, rate) > NOISE_VOICING
