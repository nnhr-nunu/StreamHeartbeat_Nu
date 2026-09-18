from __future__ import annotations

import math
from unittest.mock import patch

from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.session import HeartSession, audio_origin


@patch("stream_heartbeat.session.bundled_heart_sessions", return_value=[])
def test_tick_feeds_clock_from_peaks(_bundled: object) -> None:
    session = HeartSession()
    t = 0.0
    for i in range(2500):
        sample = 0.7 * math.sin(math.pi * (i % 500) / 40) if i % 500 < 40 else 0.01
        session.tick(t, [sample], sample_rate=1000)
        t += 0.001
    assert session.clock.bpm >= 100
    assert session.overlay.bursts_at(t - 0.001)


def test_arrhythmia_text_respects_toggle() -> None:
    off = HeartSession(HeartProfile(show_arrhythmia=False))
    on = HeartSession(HeartProfile(show_arrhythmia=True))
    t = 0.0
    for clock in (off.clock, on.clock):
        t = 0.0
        for _ in range(6):
            clock.feed_beat(t)
            t += 0.5
        clock.feed_beat(t + 0.2)
        clock.feed_beat(t + 0.35)
    off.tick(t + 0.35, [])
    on.tick(t + 0.35, [])
    off_texts = [burst.text for burst in off.overlay.bursts_at(t + 0.4)]
    on_texts = [burst.text for burst in on.overlay.bursts_at(t + 0.4)]
    assert "不整脈！" not in off_texts
    assert "不整脈！" in on_texts


@patch("stream_heartbeat.session.bundled_heart_sessions", return_value=[])
def test_commit_calibration_uses_taps(_bundled: object) -> None:
    session = HeartSession()
    session.begin_calibration(0.0)
    audio = [0.01] * 4000
    for start in (500, 1300, 2100, 2900):
        for i in range(40):
            audio[start + i] = 0.6
    t = 0.0
    for sample in audio:
        session.tick(t, [sample], sample_rate=1000)
        t += 0.001
    for tap in (0.62, 1.42, 2.22, 3.02):
        session.tap(tap)
    session.commit_calibration()
    assert 0.75 < session.profile.tap_interval < 0.85
    assert len(session.profile.calibration) >= 5
    assert session.detector.tap_interval == session.profile.tap_interval


def test_audio_origin_rewinds_by_buffer_duration() -> None:
    assert audio_origin(1.0, 1600, 16000.0) == 0.9
    assert audio_origin(1.0, 0, 16000.0) == 1.0
    assert audio_origin(1.0, 10, 0.0) == 1.0


def test_tick_feeds_detector_from_buffer_start() -> None:
    session = HeartSession()
    captured: list[float] = []

    class _Detector:
        def feed(self, samples: list[float], t: float, sample_rate: float = 16000.0) -> list[float]:
            del samples, sample_rate
            captured.append(t)
            return []

    session.detector = _Detector()  # type: ignore[assignment]
    session.tick(1.0, [0.0] * 100, sample_rate=1000.0)
    assert captured == [0.9]


def test_hidden_beat_text_does_not_spawn_burst() -> None:
    hidden = HeartSession(HeartProfile(show_beat_text=False, beat_text="ドクン"))
    shown = HeartSession(HeartProfile(show_beat_text=True, beat_text="ドクン"))

    class _Hit:
        def feed(self, samples: list[float], t: float, sample_rate: float = 16000.0) -> list[float]:
            del samples, sample_rate
            return [t]

    hidden.detector = _Hit()  # type: ignore[assignment]
    shown.detector = _Hit()  # type: ignore[assignment]
    hidden.tick(1.0, [0.0])
    shown.tick(1.0, [0.0])
    assert hidden.overlay.bursts_at(1.0) == []
    assert shown.overlay.bursts_at(1.0)


def test_tap_is_ignored_outside_calibration() -> None:
    session = HeartSession()
    session.tap(1.0)
    assert session.taps == []
    session.begin_calibration(0.0)
    session.tap(1.0)
    session.tap(1.1)
    session.tap(1.3)
    assert session.taps == [1.0, 1.3]
    assert "クリック" in session.tap_label()

