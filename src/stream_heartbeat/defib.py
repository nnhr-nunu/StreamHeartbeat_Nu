"""除細動（電気ショック）のあとの心臓のリズム。配信用の窓の演出「除細動器」が使う。

ショックの瞬間、心臓は電流で強く縮んだまま細かく震え（テタニー）、離れるとびくりと跳ねて止まる。
止まっている長さと、そのあとの乱れ方（不整脈の型）はショックのたびに選び直す。型は、ばらばらの
期外収縮・速い拍の連なり（ﾋﾞｸﾋﾞｸﾋﾞｸ）・期外収縮の連発（ビビビビクッ）・細動の震え・二段脈・
長く止まってからゆっくり・数拍ごとに一拍抜ける、の 7 つ。どれも最後は今の心拍数の規則正しい
リズムへ戻り、本物の拍時計の次の拍の頭で引き渡す（継ぎ目が見えない）。
時刻は拍時計と同じ（配信用の窓の絵の時刻）。
"""

from __future__ import annotations

import bisect
import math
import random
from collections.abc import Callable
from dataclasses import replace

from stream_heartbeat.clock import CardiacCycle, cycle_at

# びくり: この間隔の拍として速く縮め、縮み切る手前（JOLT_HOLD_AT 秒の形）で HOLD_S 秒止めて震える
JOLT_INTERVAL_S = 0.42
JOLT_HOLD_AT = 0.07
HOLD_S = 0.14
# 縮んでいる間の細かい震え（周期・強さ）と、離れたあとの減衰しながらの揺れ
TREMOR_PERIOD_S = 0.034
TREMOR = 0.45
SHAKE_S = 0.75
SHAKE_PERIOD_S = 0.085
SHAKE_DECAY_S = 0.15
# びくりで縦横に潰れる量と、上へ跳ねる量（窓の高さに対する割合）
SHAKE_SQUASH = 0.05
JUMP = 0.02
JUMP_DECAY_S = 0.12
# 不整脈の型と、ショックから次に打ち始めるまでの秒（びくりを含む。この範囲から選ぶ）
PATTERN_PAUSES: dict[str, tuple[float, float]] = {
    "scatter": (1.4, 2.4),  # ばらばらの期外収縮と長い休み
    "run": (0.75, 1.4),  # 速い拍の連なり（ﾋﾞｸﾋﾞｸﾋﾞｸﾋﾞｸ）
    "salvo": (1.0, 1.8),  # 期外収縮の連発（ビビビビクッ）
    "quiver": (0.6, 0.85),  # 細動の小刻みな震え → また止まる
    "bigeminy": (1.2, 2.0),  # 二段脈（ドッ・ピク）
    "slow": (2.8, 4.5),  # 長く止まってから、ゆっくり
    "dropped": (1.5, 2.6),  # 数拍ごとに一拍抜ける
}
PATTERNS = tuple(PATTERN_PAUSES)
# ばらばらの型が規則正しいリズムへ戻るまでの秒
RECOVER_S = 10.0
# 戻り始めの遅さ（今の間隔の何倍ぶん遅いか）・間隔のばらつき・早すぎる拍の出やすさ・弱い拍の弱さ
SLOW_START = 0.8
SCATTER = 0.4
ECTOPIC_CHANCE = 0.35
WEAKNESS = 0.5
# 早すぎる拍は戻り始めの方だけ（終わりの 3 割は規則正しく打つ）
ECTOPIC_UNTIL = 0.7
# 戻し終えたあと、本物の拍へ引き渡す前に打つ規則正しい拍の数（間隔のぶれの割合）
SETTLE_BEATS = 3
SETTLE_JITTER = 0.03
# これより短い間隔の拍は、1 拍の動きを間隔に収まるよう速める（次の拍で形が飛ばない）
FAST_FIT_S = 0.45
# 拍の文字を出す拍（弱すぎる震えには出さない・続けて出すときはこの秒より空ける）
TEXT_MIN_STRENGTH = 0.4
TEXT_GAP_S = 0.2
# 打ち終えたあと、本物の拍を待つ上限（今の間隔の何倍）。拍が来なくてもここで引き渡す
HANDOFF_WAIT = 2.5
# 連打しても、この秒より短い間隔のショックは受けない
MIN_GAP_S = 0.4


class _Plan:
    """拍の並びを前から順に組み立てる。now は次の拍を打つ時刻。"""

    def __init__(self, start: float, target: float, rng: random.Random) -> None:
        self.now = start
        self.target = target
        self.rng = rng
        self.beats: list[tuple[float, float]] = []

    def beat(self, strength: float, gap: float) -> None:
        """いま強さ strength の拍を打ち、gap 秒あとへ進む。"""
        self.beats.append((self.now, max(0.05, min(1.0, strength))))
        self.now += max(0.06, gap)

    def rest(self, gap: float) -> None:
        """最後の拍から次の拍までを gap 秒にする（連なりのあとの休み）。"""
        if self.beats:
            self.now = self.beats[-1][0] + gap

    def recover(self, seconds: float, slow: float, scatter: float, ectopic: float) -> None:
        """seconds 秒かけて今の心拍へ戻す。

        はじめは slow 倍ぶん遅く、間隔は scatter の割合でばらつき、ectopic の割合で早すぎる弱い拍
        （そのあとの長い休み）が混ざる。どれも戻るにつれて減り、最後は規則正しく強い拍になる。
        """
        rng = self.rng
        start = self.now
        while self.now - start < seconds:
            calm = 1.0 - (self.now - start) / seconds
            mean = self.target * (1.0 + slow * calm**1.5)
            strength = 1.0 - WEAKNESS * calm * rng.random()
            if calm > 1.0 - ECTOPIC_UNTIL and rng.random() < ectopic * calm:
                self.beat(strength, mean * rng.uniform(0.38, 0.5))
                self.beat(0.45 + 0.2 * rng.random(), mean * rng.uniform(1.35, 1.65))
            else:
                self.beat(strength, mean * (1.0 + scatter * calm * rng.uniform(-1.0, 1.0)))
        self.settle()

    def settle(self) -> None:
        """今の心拍数の規則正しい強い拍を数拍打つ（本物の拍へ継ぎ目なく引き渡す）。"""
        for _ in range(SETTLE_BEATS):
            jitter = self.rng.uniform(-SETTLE_JITTER, SETTLE_JITTER)
            self.beat(self.rng.uniform(0.95, 1.0), self.target * (1.0 + jitter))


def _scatter(plan: _Plan) -> None:
    """ばらばら: 早すぎる弱い拍と長い休みが混ざりながら、ゆっくり戻る。"""
    plan.recover(RECOVER_S, SLOW_START, SCATTER, ECTOPIC_CHANCE)


def _run(plan: _Plan) -> None:
    """速い拍の連なり（ﾋﾞｸﾋﾞｸﾋﾞｸﾋﾞｸ）が 1〜3 回。あいだは少し遅い拍。"""
    rng, target = plan.rng, plan.target
    runs = rng.choice((1, 2, 2, 3))
    for k in range(runs):
        rate = rng.uniform(0.15, 0.21)
        for _ in range(rng.randint(6, 12) if k == 0 else rng.randint(4, 8)):
            plan.beat(rng.uniform(0.45, 0.7), rate * rng.uniform(0.88, 1.12))
        plan.rest(target * rng.uniform(1.2, 1.9))
        if k < runs - 1:
            for _ in range(rng.randint(1, 3)):
                plan.beat(rng.uniform(0.75, 0.95), target * rng.uniform(1.05, 1.3))
    plan.recover(rng.uniform(4.0, 5.5), 0.4, 0.25, 0.15)


def _salvo(plan: _Plan) -> None:
    """期外収縮の連発（ビビビビクッ）: だんだん強まる小さな拍のあとに強い一打ちと長い休み。"""
    rng, target = plan.rng, plan.target
    for _ in range(rng.randint(2, 3)):
        count = rng.randint(3, 5)
        for i in range(count):
            plan.beat(0.18 + 0.3 * i / count + rng.uniform(-0.04, 0.04), rng.uniform(0.085, 0.13))
        plan.beat(1.0, target * rng.uniform(1.5, 1.9))
        for _ in range(rng.randint(1, 2)):
            plan.beat(rng.uniform(0.8, 0.95), target * rng.uniform(1.0, 1.25))
    plan.recover(rng.uniform(4.0, 6.0), 0.3, 0.2, 0.2)


def _quiver(plan: _Plan) -> None:
    """細動: 小刻みに弱く震え続け、ふっと止まってから、遅い拍で戻る。"""
    rng = plan.rng
    end = plan.now + rng.uniform(1.6, 3.2)
    while plan.now < end:
        plan.beat(rng.uniform(0.1, 0.3), rng.uniform(0.07, 0.14))
    plan.rest(rng.uniform(1.0, 2.2))
    plan.recover(rng.uniform(7.0, 9.0), 1.0, 0.35, 0.25)


def _bigeminy(plan: _Plan) -> None:
    """二段脈: ふつうの拍のすぐあとに弱い拍（ドッ・ピク）を繰り返す。"""
    rng, target = plan.rng, plan.target
    for _ in range(rng.randint(4, 6)):
        plan.beat(rng.uniform(0.85, 1.0), target * rng.uniform(0.42, 0.52))
        plan.beat(rng.uniform(0.35, 0.55), target * rng.uniform(1.45, 1.75))
    plan.recover(rng.uniform(3.0, 5.0), 0.2, 0.15, 0.3)


def _slow(plan: _Plan) -> None:
    """長く止まったあと、弱く遅い拍から。ときどき一拍抜けながら速まる。"""
    rng, target = plan.rng, plan.target
    seconds = rng.uniform(8.0, 10.0)
    start = plan.now
    while plan.now - start < seconds:
        calm = 1.0 - (plan.now - start) / seconds
        mean = target * (1.0 + 1.3 * calm**1.2)
        gap = mean * (1.0 + 0.12 * calm * rng.uniform(-1.0, 1.0))
        if calm > 0.4 and rng.random() < 0.15:
            gap += mean
        plan.beat(1.0 - 0.55 * calm, gap)
    plan.settle()


def _dropped(plan: _Plan) -> None:
    """数拍ごとに一拍抜ける（だんだん詰まって、ふっと抜ける）。"""
    rng, target = plan.rng, plan.target
    for _ in range(rng.randint(3, 4)):
        for i in range(rng.randint(2, 4)):
            plan.beat(rng.uniform(0.85, 1.0), target * (1.0 - 0.06 * i) * rng.uniform(0.95, 1.05))
        plan.rest(target * rng.uniform(1.8, 2.1))
    plan.recover(rng.uniform(2.0, 3.5), 0.15, 0.1, 0.1)


_BUILDERS: dict[str, Callable[[_Plan], None]] = {
    "scatter": _scatter,
    "run": _run,
    "salvo": _salvo,
    "quiver": _quiver,
    "bigeminy": _bigeminy,
    "slow": _slow,
    "dropped": _dropped,
}


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
        # 拍の文字を出す拍の時刻
        self._text_times: list[float] = []
        self._settle_at = 0.0
        self._target = 1.0
        # 今の不整脈の型と、これまでのショックの回数（電流の走り方を毎回変えるのに使う）
        self.pattern = ""
        self.shots = 0

    def shock(self, t: float, interval: float, pattern: str | None = None) -> bool:
        """時刻 t に電気ショックをかける。interval は今の心拍の間隔（戻っていく先）。

        pattern は不整脈の型（PATTERNS のどれか。None なら前回と違う型をくじで選ぶ）。
        演出の途中でも最初からやり直す。直前のショックから MIN_GAP_S 未満なら受けずに False。
        """
        if self._shock_at is not None and 0.0 <= t - self._shock_at < MIN_GAP_S:
            return False
        rng = self._rng
        if pattern not in _BUILDERS:
            pattern = rng.choice([p for p in PATTERNS if p != self.pattern])
        target = max(0.3, min(2.0, interval))
        plan = _Plan(t + rng.uniform(*PATTERN_PAUSES[pattern]), target, rng)
        _BUILDERS[pattern](plan)
        beats = [(t, JOLT_INTERVAL_S, 1.0)]
        for k, (beat_t, strength) in enumerate(plan.beats):
            following = plan.beats[k + 1][0] if k + 1 < len(plan.beats) else plan.now
            beats.append((beat_t, following - beat_t, strength))
        texts: list[float] = []
        for beat_t, _gap, strength in beats[1:]:
            if strength >= TEXT_MIN_STRENGTH and (not texts or beat_t - texts[-1] >= TEXT_GAP_S):
                texts.append(beat_t)
        self._shock_at = t
        self._end_at = math.inf
        self._beats = beats
        self._times = [b[0] for b in beats]
        self._text_times = texts
        self._settle_at = plan.now
        self._target = target
        self.pattern = pattern
        self.shots += 1
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
        dt = t - beat_t
        if index == 0:
            # 電流が流れている間は縮んだまま。離れると残りを縮み切って止まる（心房も動かない）
            if dt > JOLT_HOLD_AT:
                dt = max(JOLT_HOLD_AT, dt - HOLD_S)
            return replace(cycle_at(dt, interval, strength), atria_r=0.0, atria_l=0.0)
        if interval < FAST_FIT_S:
            # 速い拍は 1 拍の動きを縮めて間隔に収める（Blender の心臓も age と間隔の比で収まる）
            k = FAST_FIT_S / interval
            return cycle_at(dt * k, FAST_FIT_S, strength)
        return cycle_at(dt, interval, strength)

    def since_shock(self, t: float) -> float | None:
        """ショックからの秒（演出の外・ショック前なら None）。"""
        if not self.active(t) or self._shock_at is None:
            return None
        return t - self._shock_at

    def shake(self, t: float) -> float:
        """びくりの揺れ（-1〜1。揺れていなければ 0）。

        電流が流れている間は細かく速く震え、離れると大きく揺れてから減っていく。
        """
        since = self.since_shock(t)
        if since is None or since >= SHAKE_S:
            return 0.0
        held = JOLT_HOLD_AT + HOLD_S
        if since < held:
            return TREMOR * math.sin(2.0 * math.pi * since / TREMOR_PERIOD_S)
        after = since - held
        return math.exp(-after / SHAKE_DECAY_S) * math.sin(2.0 * math.pi * after / SHAKE_PERIOD_S)

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
        """after より後・until までに打った、文字を出す拍（びくりと弱い震えは除く）。"""
        return [b for b in self._text_times if after < b <= until and self.active(b)]

    def mutes(self, start: float) -> bool:
        """本物の拍で出た文字（start はその時刻）を隠すか。ショックから引き渡すまでの拍は隠す。"""
        return self._shock_at is not None and self._shock_at <= start < self._end_at
