"""話し声・キーボードのような心音ではない音を、拍に数えない。"""

from __future__ import annotations

import math
import random

import pytest

import stream_heartbeat.detect as detect
from stream_heartbeat.detect import HeartSoundDetector
from stream_heartbeat.noise_gate import VOICE_RATE, looks_like_noise, voicing

SR = 16000


def _voice(out: list[float], at: float, amp: float, f0: float, dur: float) -> None:
    """声帯の周期で鳴る有声音（基本周波数と倍音）の一節。"""
    n = int(dur * SR)
    k0 = int(at * SR)
    for j in range(min(n, len(out) - k0)):
        env = math.sin(math.pi * j / n) ** 2
        t = j / SR
        out[k0 + j] += amp * env * sum(math.sin(2 * math.pi * f0 * h * t) / h for h in range(1, 13))


def _lub_dub(secs: float, bpm: float = 75.0) -> tuple[list[float], list[float]]:
    """ドッ（42 Hz）とクン（58 Hz）の合成の心音と、ドッの時刻。"""
    out = [0.0] * int(secs * SR)
    lubs = []
    t = 0.4
    while t < secs - 0.5:
        lubs.append(t)
        for freq, dur, amp, off in ((42.0, 0.09, 0.3, 0.0), (58.0, 0.07, 0.18, 0.3)):
            n = int(dur * SR)
            k = int((t + off) * SR)
            for j in range(n):
                env = math.sin(math.pi * j / n) ** 2
                out[k + j] += amp * env * math.sin(2 * math.pi * freq * j / SR)
        t += 60.0 / bpm
    return out, lubs


def _beats(samples: list[float]) -> list[float]:
    detector = HeartSoundDetector()
    beats: list[float] = []
    for i in range(0, len(samples), SR // 20):
        beats.extend(detector.feed(samples[i : i + SR // 20], i / SR, SR))
    return beats


def test_voicing_sees_the_pitch_of_a_voice_not_noise() -> None:
    rate = VOICE_RATE
    rnd = random.Random(1)
    voiced = [sum(math.sin(2 * math.pi * 140 * h * k / rate) / h for h in (1, 2, 3))
              for k in range(320)]
    hiss = [rnd.gauss(0.0, 1.0) for _ in range(320)]
    assert voicing(voiced, rate) > 0.9
    assert voicing(hiss, rate) < 0.5
    assert voicing(voiced[:20], rate) == 0.0


def test_only_sounds_that_start_here_are_noise() -> None:
    rate = VOICE_RATE
    rnd = random.Random(2)
    quiet = [rnd.gauss(0.0, 0.001) for _ in range(1000)]
    voiced = [
        0.3 * math.sin(2 * math.pi * 150 * k / rate) + 0.1 * math.sin(2 * math.pi * 450 * k / rate)
        for k in range(320)
    ]
    click = [0.0] * 320
    click[100] = 1.0
    click[101] = -0.6
    # 静かなところで急に始まった声やカチッは雑音
    assert looks_like_noise(quiet + voiced, rate)
    assert looks_like_noise(quiet + [c + q for c, q in zip(click, quiet)], rate)
    # 前から続いている声（話しながらの心音）は雑音にしない
    steady = [0.3 * math.sin(2 * math.pi * 150 * k / rate) for k in range(1320)]
    assert not looks_like_noise(steady, rate)
    # 急に強まっても、声でもカチッでもない音（心音に混ざるざらついた高い音）は雑音にしない
    thud = [0.01 * rnd.gauss(0.0, 1.0) * math.exp(-k / 120) for k in range(320)]
    assert not looks_like_noise(quiet + [t + q for t, q in zip(thud, quiet)], rate)


def test_talking_alone_does_not_make_a_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    rnd = random.Random(3)
    sig = [rnd.gauss(0.0, 0.0005) for _ in range(int(14 * SR))]
    t = 0.5
    while t < 13.0:
        _voice(sig, t, 0.1, rnd.uniform(100.0, 220.0), rnd.uniform(0.12, 0.3))
        t += rnd.uniform(0.25, 0.6)
    assert len(_beats(sig)) <= 5
    # 見分けを外すと、話し声の節を拍に数えてしまう（見分けが効いていることの確認）
    monkeypatch.setattr(detect, "looks_like_noise", lambda *_a, **_k: False)
    assert len(_beats(sig)) >= 15


def test_talking_between_beats_keeps_every_beat() -> None:
    sig, lubs = _lub_dub(secs=14.0)
    for lub in lubs[4:-1]:
        _voice(sig, lub + 0.5, 0.2, 130.0, 0.22)
    late = [b for b in _beats(sig) if b > 4.0]
    expected = [lub for lub in lubs if lub > 4.0]
    assert len(late) == len(expected)
    assert all(min(abs(b - lub) for lub in lubs) < 0.1 for b in late)
