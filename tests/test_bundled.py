from __future__ import annotations

import math

from stream_heartbeat.bundled import bundled_heart_sessions, heart_samples_dir
from stream_heartbeat.samples import load_audio_mono, to_mono_16k


def test_bundled_heart_wav_is_present() -> None:
    sessions = bundled_heart_sessions()
    assert sessions
    assert max(abs(x) for x in sessions[0]) > 0.05


def test_load_audio_mono_reads_wav() -> None:
    src = next(heart_samples_dir().glob("*.wav"))
    samples = load_audio_mono(src)
    assert len(samples) > 100
    assert max(abs(x) for x in samples) > 0.05


def test_to_mono_16k_downmixes_and_resamples() -> None:
    # 44.1 kHz ステレオの 1 秒（左右で逆の片寄り + 共通の 50 Hz）
    rate = 44100
    frames: list[float] = []
    for i in range(rate):
        tone = 0.5 * math.sin(2 * math.pi * 50 * i / rate)
        frames.extend((tone + 0.2, tone - 0.2))
    out = to_mono_16k(frames, 2, rate)
    assert abs(len(out) - 16000) <= 1
    assert max(out) > 0.45
    assert abs(sum(out) / len(out)) < 0.01
