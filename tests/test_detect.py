from __future__ import annotations

import math
import statistics
import wave
from pathlib import Path

from stream_heartbeat.detect import (
    CalibrationTemplate,
    HeartSoundDetector,
    band_pass,
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


def test_slow_tap_interval_does_not_drop_normal_beats() -> None:
    detector = HeartSoundDetector(tap_interval=1.7)
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(4000):
        beats.extend(detector.feed([_thud(i % 800)], t, sr))
        t += 1 / sr
    assert len(beats) >= 3


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
    # 型は検出と同じ帯域に絞った音で覚えるので、聞こえた同じ形の音とよく一致する
    heard = band_pass([0.01] * 200 + pulse, 1000)[200:290]
    assert template.score(heard) > 0.9
    snap = [0.9 if i % 2 == 0 else -0.9 for i in range(20)] + [0.0] * 70
    other = band_pass([0.0] * 200 + snap, 1000)[200:290]
    assert template.score(other) < template.score(heard)
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


def test_equal_fast_beats_are_not_halved() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(10000):
        sample = 0.25 * math.sin(math.pi * (i % 350) / 40) if i % 350 < 40 else 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    late = [b for b in beats if b > 3.0]
    assert len(late) >= 12
    gaps = [b - a for a, b in zip(late, late[1:])]
    assert 0.28 < statistics.median(gaps) < 0.45


def test_short_long_pair_is_one_beat() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(12000):
        pos = i % 1200
        if pos < 40:
            sample = 0.24 * math.sin(math.pi * pos / 40)
        elif 320 <= pos < 360:
            sample = 0.22 * math.sin(math.pi * (pos - 320) / 40)
        else:
            sample = 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    late = [b for b in beats if b > 4.0]
    assert len(late) >= 5
    gaps = [b - a for a, b in zip(late, late[1:])]
    assert statistics.median(gaps) > 0.9


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


def test_tap_interval_merges_double_count() -> None:
    detector = HeartSoundDetector(tap_interval=0.80)
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(5000):
        sample = 0.3 * math.sin(math.pi * (i % 400) / 40) if i % 400 < 40 else 0.01
        beats.extend(detector.feed([sample], t, sr))
        t += 1 / sr
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert len(beats) >= 4
    assert 0.70 < statistics.median(gaps) < 0.90


def test_fast_tap_keeps_equal_beats() -> None:
    detector = HeartSoundDetector(tap_interval=0.40)
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


def _lub_dub(
    bpm: float,
    secs: float,
    systole: float,
    s1: float = 0.3,
    s2: float = 0.18,
    sr: int = 4000,
) -> list[float]:
    """ドッ（42Hz）とクン（58Hz）が systole 秒あいて鳴る合成の心音。"""
    out = [0.0] * int(secs * sr)
    t = 0.4
    while t < secs - 0.5:
        for freq, dur, amp, off in ((42.0, 0.09, s1, 0.0), (58.0, 0.07, s2, systole)):
            n = int(dur * sr)
            k = int((t + off) * sr)
            for j in range(n):
                env = math.sin(math.pi * j / n) ** 2
                out[k + j] += amp * env * math.sin(2 * math.pi * freq * j / sr)
        t += 60.0 / bpm
    return out


def _median_gap(samples: list[float], sr: int, after: float, **kwargs: float) -> float:
    detector = HeartSoundDetector(**kwargs)
    beats: list[float] = []
    for i in range(0, len(samples), sr // 20):
        beats.extend(detector.feed(samples[i : i + sr // 20], i / sr, sr))
    late = [b for b in beats if b > after]
    assert len(late) >= 4
    return statistics.median(b - a for a, b in zip(late, late[1:]))


def test_steady_background_is_not_a_beat_at_start() -> None:
    sr = 4000
    hum = [0.06 * math.sin(2 * math.pi * 40 * i / sr) for i in range(sr)]
    detector = HeartSoundDetector()
    assert detector.feed(hum, 0.0, sr) == []


def test_resting_lub_dub_is_not_doubled() -> None:
    # 70 BPM ではドッからクンまで約 0.37 秒あり、決め打ちの 0.36 秒の待ちでは防げなかった
    sig = _lub_dub(bpm=70, secs=14, systole=0.37)
    assert 0.78 < _median_gap(sig, 4000, after=5.0) < 0.94


def test_loud_second_sound_is_not_doubled() -> None:
    sig = _lub_dub(bpm=80, secs=14, systole=0.356, s1=0.16, s2=0.22)
    assert 0.68 < _median_gap(sig, 4000, after=5.0) < 0.82


def test_fast_beats_after_resting_tap_are_not_halved() -> None:
    # 安静時に 75 BPM でクリックしたあと、運動で 120 BPM になっても半分に数えない
    sig = _lub_dub(bpm=120, secs=14, systole=0.29)
    assert 0.44 < _median_gap(sig, 4000, after=5.0, tap_interval=0.8) < 0.56


def _add_bump(out: list[float], at: float, amp: float, freq: float, dur: float, sr: int) -> None:
    n = int(dur * sr)
    k = int(at * sr)
    for j in range(min(n, len(out) - k)):
        env = math.sin(math.pi * j / n) ** 2
        out[k + j] += amp * env * math.sin(2 * math.pi * freq * j / sr)


def _beats(samples: list[float], sr: int) -> list[float]:
    detector = HeartSoundDetector()
    beats: list[float] = []
    for i in range(0, len(samples), sr // 20):
        beats.extend(detector.feed(samples[i : i + sr // 20], i / sr, sr))
    return beats


def test_small_bump_before_lub_does_not_steal_the_beat() -> None:
    # おなかの音などの小さな音が拍の少し前に鳴っても、本物のドッに合わせ直す
    sr = 4000
    sig = _lub_dub(bpm=75, secs=16, systole=0.3, sr=sr)
    lubs = [0.4 + k * 0.8 for k in range(19)]
    for lub in lubs[8:]:
        _add_bump(sig, lub - 0.17, 0.16, 35.0, 0.06, sr)
    late = [b for b in _beats(sig, sr) if b > 8.0]
    assert len(late) >= 8
    on_lub = sum(1 for b in late if min(abs(b - lub) for lub in lubs) < 0.08)
    assert on_lub >= len(late) - 2


def test_loud_bump_does_not_hide_following_beats() -> None:
    # 体の動きなどの大きな一発のあとも、小さめの本物の拍を落とし続けない
    sr = 4000
    sig = _lub_dub(bpm=90, secs=16, systole=0.28, sr=sr)
    _add_bump(sig, 8.05, 1.6, 30.0, 0.25, sr)
    after = [b for b in _beats(sig, sr) if 8.6 < b < 12.6]
    assert len(after) >= 5
