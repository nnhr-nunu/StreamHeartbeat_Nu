"""除細動（電気ショック）のあとの心臓のリズム。配信用の窓の演出「除細動器」が使う。

ショックの瞬間に心臓がびくりと強くひと縮みして揺れ、少し止まってから、間隔のばらばらな拍
（早すぎる弱い拍と、そのあとの長い休み）を打ちながら、ゆっくり今の心拍数の規則正しいリズムへ
戻る。打ち終えたら、本物の拍時計の次の拍の頭で引き渡す（継ぎ目が見えない）。
時刻は拍時計と同じ（配信用の窓の絵の時刻）。
"""

from __future__ import annotations

import bisect
import math
import random
from dataclasses import replace

from stream_heartbeat.clock import CardiacCycle, cycle_at

# びくり: この間隔の拍として速く縮める。揺れは減衰しながら細かく震える
JOLT_INTERVAL_S = 0.42
SHAKE_S = 0.6
SHAKE_PERIOD_S = 0.075
SHAKE_DECAY_S = 0.14
# びくりで縦横に潰れる量と、上へ跳ねる量（窓の高さに対する割合）
SHAKE_SQUASH = 0.05
JUMP = 0.018
JUMP_DECAY_S = 0.12
# ショックから次に打ち始めるまでの秒（びくりを含む。この範囲から選ぶ）
PAUSE_S = (1.6, 2.2)
# 不整脈から規則正しいリズムへ戻るまでの秒
RECOVER_S = 10.0
# 戻り始めの遅さ（今の間隔の何倍ぶん遅いか）・間隔のばらつき・早すぎる拍の出やすさ・弱い拍の弱さ
SLOW_START = 0.8
SCATTER = 0.4
ECTOPIC_CHANCE = 0.35
WEAKNESS = 0.5
# 早すぎる拍は戻り始めの方だけ（終わりの 3 割は規則正しく打つ）
ECTOPIC_UNTIL = 0.7
# 打ち終えたあと、本物の拍を待つ上限（今の間隔の何倍）。拍が来なくてもここで引き渡す
HANDOFF_WAIT = 2.5
# 連打しても、この秒より短い間隔のショックは受けない
MIN_GAP_S = 0.4


class DefibRhythm:
    """電気ショックのあとの拍の並びと、本物の拍時計へ引き渡すまでの状態。"""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()
        self._shock_at: float | None = None
        # 本物の拍時計へ引き渡した時刻（引き渡すまでは無限）
        self._end_at = math.inf
        # (拍の時刻, 次の拍までの秒, 強さ)。先頭はショックのびくり
        self._beats: list[tuple[float, float, float]] = []
        self._times: list[float] = []
        self._settle_at = 0.0
        self._target = 1.0

    def shock(self, t: float, interval: float) -> bool:
        """時刻 t に電気ショックをかける。interval は今の心拍の間隔（戻っていく先）。

        演出の途中でも最初からやり直す。直前のショックから MIN_GAP_S 未満なら受けずに False。
        """
        if self._shock_at is not None and 0.0 <= t - self._shock_at < MIN_GAP_S:
            return False
        rng = self._rng
        target = max(0.3, min(2.0, interval))
        resume = t + rng.uniform(*PAUSE_S)
        times: list[tuple[float, float]] = []
        now = resume
        while now - resume < RECOVER_S:
            calm = 1.0 - (now - resume) / RECOVER_S
            mean = target * (1.0 + SLOW_START * calm**1.5)
            times.append((now, 1.0 - WEAKNESS * calm * rng.random()))
            if calm > 1.0 - ECTOPIC_UNTIL and rng.random() < ECTOPIC_CHANCE * calm:
                # 早すぎる弱い拍と、そのあとの長い休み
                early = now + mean * rng.uniform(0.38, 0.5)
                times.append((early, 0.45 + 0.2 * rng.random()))
                now = early + mean * rng.uniform(1.35, 1.65)
            else:
                now += mean * (1.0 + SCATTER * calm * rng.uniform(-1.0, 1.0))
        beats = [(t, JOLT_INTERVAL_S, 1.0)]
        for k, (beat_t, strength) in enumerate(times):
            following = times[k + 1][0] if k + 1 < len(times) else now
            beats.append((beat_t, following - beat_t, strength))
        self._shock_at = t
        self._end_at = math.inf
        self._beats = beats
        self._times = [b[0] for b in beats]
        self._settle_at = now
        self._target = target
        return True

    def active(self, t: float) -> bool:
        """ショックから本物の拍時計へ引き渡すまでの間か。"""
        return self._shock_at is not None and self._shock_at <= t < self._end_at

    def step(self, t: float, real_origin: float) -> None:
        """不整脈の拍を打ち終えたら、本物の拍の頭で引き渡す。

        real_origin は t 以前で最後の本物の拍。
        """
        if self._shock_at is None or self._end_at < math.inf or t < self._settle_at:
            return
        if real_origin >= self._settle_at:
            self._end_at = real_origin
        elif t >= self._settle_at + HANDOFF_WAIT * self._target:
            self._end_at = t

    def cycle(self, t: float) -> CardiacCycle | None:
        """いまの心臓の動き。演出の外なら None（本物の拍時計のまま描く）。"""
        if not self.active(t):
            return None
        index = bisect.bisect_right(self._times, t) - 1
        if index < 0:
            return None
        beat_t, interval, strength = self._beats[index]
        cycle = cycle_at(t - beat_t, interval, strength)
        if index == 0:
            # びくりのあとは止まっている。次の拍に備える心房の収縮も無い
            cycle = replace(cycle, atria_r=0.0, atria_l=0.0)
        return cycle

    def since_shock(self, t: float) -> float | None:
        """ショックからの秒（演出の外・ショック前なら None）。"""
        if not self.active(t) or self._shock_at is None:
            return None
        return t - self._shock_at

    def shake(self, t: float) -> float:
        """びくりの揺れ（-1〜1。減衰しながら細かく震える。揺れていなければ 0）。"""
        since = self.since_shock(t)
        if since is None or since >= SHAKE_S:
            return 0.0
        return math.exp(-since / SHAKE_DECAY_S) * math.sin(2.0 * math.pi * since / SHAKE_PERIOD_S)

    def squash(self, t: float) -> tuple[float, float]:
        """びくりで心臓が横・縦に潰れる倍率（揺れていなければ 1, 1）。"""
        s = self.shake(t)
        return 1.0 + SHAKE_SQUASH * s, 1.0 - SHAKE_SQUASH * 0.9 * s

    def jump(self, t: float) -> float:
        """びくりで心臓が上へ跳ねる量（窓の高さに対する割合）。"""
        since = self.since_shock(t)
        if since is None or since >= SHAKE_S:
            return 0.0
        return JUMP * math.exp(-since / JUMP_DECAY_S) * (1.0 - math.exp(-since / 0.02))

    def beats_between(self, after: float, until: float) -> list[float]:
        """after より後・until までに打った拍（ショックのびくりは除く）。拍の文字を出すのに使う。"""
        return [b for b in self._times[1:] if after < b <= until and self.active(b)]

    def mutes(self, start: float) -> bool:
        """本物の拍で出た文字（start はその時刻）を隠すか。ショックから引き渡すまでの拍は隠す。"""
        return self._shock_at is not None and self._shock_at <= start < self._end_at
