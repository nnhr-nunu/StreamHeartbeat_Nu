from __future__ import annotations

import array
import math
import wave
from pathlib import Path

from stream_heartbeat.samples import load_audio_mono, to_mono_16k


def test_load_audio_mono_reads_wav(tmp_path: Path) -> None:
    # 16 kHz モノラル 16bit の 0.5 秒（50 Hz・振幅 0.5）
    wave_50hz = (math.sin(2 * math.pi * 50 * i / 16000) for i in range(8000))
    pcm = array.array("h", (int(16384 * x) for x in wave_50hz))
    src = tmp_path / "beat.wav"
    with wave.open(str(src), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm.tobytes())
    samples = load_audio_mono(src)
    assert len(samples) == 8000
    assert 0.45 < max(samples) < 0.55


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
