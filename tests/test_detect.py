from __future__ import annotations

import math
import statistics
import wave
from pathlib import Path

from stream_heartbeat.detect import (
    CalibrationTemplate,
    HeartSoundDetector,
    envelope_rms,
    load_wav_mono,
    looks_like_thud,
)


def test_envelope_rms_is_shorter_than_samples() -> None:
    samples = [0.0] * 100 + [1.0] * 20 + [0.0] * 100
    env = envelope_rms(samples, hop=10)
    assert len(env) < len(samples)
    assert max(env) > min(env)


def _thud(pos: int, width: int = 40) -> float:
    if 0 <= pos < width:
        return 0.7 * math.sin(math.pi * pos / width)
    return 0.01


def test_detector_finds_periodic_peaks() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(3000):
        found = detector.feed([_thud(i % 500)], t, sr)
        beats.extend(found)
        t += 1 / sr
    assert len(beats) >= 4
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert all(0.4 < g < 0.6 for g in gaps)


def test_finger_snap_is_not_a_beat() -> None:
    detector = HeartSoundDetector()
    sr = 16000
    t = 0.0
    hits: list[float] = []
    for i in range(4000):
        sample = 0.0
        if 800 <= i < 820:
            sample = 0.95 if i % 2 == 0 else -0.95
        hits.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    assert hits == []


def test_template_prefers_matching_shape() -> None:
    pulse = [_thud(i, 40) for i in range(90)]
    template = CalibrationTemplate.from_sessions([pulse, pulse], sample_rate=1000)
    assert template is not None
    detector = HeartSoundDetector(template=template)
    t = 0.0
    hits: list[float] = []
    for i, sample in enumerate(pulse * 2):
        hits.extend(detector.feed([sample], t, 1000))
        t += 0.001
    assert hits
    miss_det = HeartSoundDetector(template=template)
    miss: list[float] = []
    t = 0.0
    for i in range(200):
        miss.extend(miss_det.feed([0.5], t, 1000))
        t += 0.001
    assert miss == []


def test_quiet_heart_is_detected() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(8000):
        sample = 0.055 * math.sin(math.pi * (i % 800) / 50) if i % 800 < 50 else 0.002
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    assert len(beats) >= 7
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert all(0.65 < g < 0.95 for g in gaps)


def test_lub_dub_counts_as_one_beat() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(9000):
        pos = i % 900
        if pos < 40:
            sample = 0.22 * math.sin(math.pi * pos / 40)
        elif 280 <= pos < 315:
            sample = 0.14 * math.sin(math.pi * (pos - 280) / 35)
        else:
            sample = 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    assert len(beats) >= 7
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert statistics.median(gaps) > 0.7
    assert all(g > 0.55 for g in gaps)


def test_regular_half_beats_are_paired() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(10000):
        sample = 0.25 * math.sin(math.pi * (i % 350) / 40) if i % 350 < 40 else 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    late = [b for b in beats if b > 3.0]
    assert len(late) >= 6
    gaps = [b - a for a, b in zip(late, late[1:])]
    assert statistics.median(gaps) > 0.55


def test_quiet_second_sound_is_not_a_second_beat() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(8000):
        pos = i % 800
        if pos < 40:
            sample = 0.28 * math.sin(math.pi * pos / 40)
        elif 300 <= pos < 330:
            sample = 0.12 * math.sin(math.pi * (pos - 300) / 30)
        else:
            sample = 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert statistics.median(gaps) > 0.65


def test_fast_equal_beats_stay_unmerged() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(5000):
        sample = 0.3 * math.sin(math.pi * (i % 400) / 40) if i % 400 < 40 else 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert len(beats) >= 8
    assert 0.32 < statistics.median(gaps) < 0.48


def test_slow_heart_near_thirty_is_detected() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(12000):
        sample = 0.35 * math.sin(math.pi * (i % 1900) / 50) if i % 1900 < 50 else 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    assert len(beats) >= 5
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert 1.6 < statistics.median(gaps) < 2.2


def test_quiet_gurgle_is_not_an_extra_beat() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(8000):
        pos = i % 800
        if pos < 40:
            sample = 0.3 * math.sin(math.pi * pos / 40)
        elif 480 <= pos < 510:
            sample = 0.11 * math.sin(math.pi * (pos - 480) / 30)
        else:
            sample = 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert statistics.median(gaps) > 0.7


def test_from_sessions_skips_empty_instead_of_whole_file() -> None:
    silence = [0.001] * 2000
    pulse = [_thud(i, 40) for i in range(90)]
    template = CalibrationTemplate.from_sessions([silence, pulse], sample_rate=1000)
    assert template is not None
    assert len(template.wave) <= 200


def test_looks_like_thud_rejects_bright_noise() -> None:
    snap = [0.9 if i % 2 == 0 else -0.9 for i in range(40)]
    heart = [_thud(i, 40) for i in range(40)]
    assert looks_like_thud(heart)
    assert not looks_like_thud(snap)


def test_load_wav_mono(tmp_path: Path) -> None:
    path = tmp_path / "thud.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        payload = b"".join(
            int(20000 * _thud(i, 80)).to_bytes(2, "little", signed=True) for i in range(160)
        )
        wav.writeframes(payload)
    samples = load_wav_mono(path)
    assert len(samples) == 160
    assert max(samples) > 0.1
