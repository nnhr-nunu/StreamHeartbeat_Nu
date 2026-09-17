from __future__ import annotations

from stream_heartbeat.bundled import bundled_heart_sessions, heart_samples_dir
from stream_heartbeat.samples import load_audio_mono


def test_bundled_heart_wav_is_present() -> None:
    sessions = bundled_heart_sessions()
    assert sessions
    assert max(abs(x) for x in sessions[0]) > 0.05


def test_load_audio_mono_reads_wav() -> None:
    src = next(heart_samples_dir().glob("*.wav"))
    samples = load_audio_mono(src)
    assert len(samples) > 100
    assert max(abs(x) for x in samples) > 0.05
