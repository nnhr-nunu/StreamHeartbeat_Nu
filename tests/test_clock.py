from __future__ import annotations

from stream_heartbeat.clock import BeatClock


def test_bpm_from_intervals() -> None:
    clock = BeatClock()
    clock.feed_beat(0.0)
    clock.feed_beat(0.5)
    clock.feed_beat(1.0)
    assert clock.bpm == 120
    assert clock.detected is True


def test_pulse_peaks_after_beat() -> None:
    clock = BeatClock()
    clock.feed_beat(1.0)
    assert clock.pulse_scale(1.0) > clock.pulse_scale(1.3)


def test_lost_keeps_last_bpm_and_metronome() -> None:
    clock = BeatClock()
    clock.feed_beat(0.0)
    clock.feed_beat(0.5)
    clock.lost_if_silent(2.0)
    assert clock.detected is False
    assert clock.bpm == 120
    scale_a = clock.pulse_scale(2.0)
    scale_b = clock.pulse_scale(2.25)
    assert scale_a != scale_b or clock.pulse_scale(2.5) > 0.2


def test_arrhythmia_needs_two_wild_intervals() -> None:
    clock = BeatClock()
    t = 0.0
    for _ in range(6):
        clock.feed_beat(t)
        t += 0.5
    assert clock.pop_arrhythmia(t) is False
    clock.feed_beat(t + 0.2)
    clock.feed_beat(t + 0.35)
    assert clock.pop_arrhythmia(t + 0.35) is True
    assert clock.pop_arrhythmia(t + 1.0) is False


def test_oshilog_mismatch() -> None:
    clock = BeatClock()
    clock.feed_beat(0.0)
    clock.feed_beat(0.5)
    clock.oshilog_bpm = 70
    assert clock.bpm_mismatch() is True
    clock.oshilog_bpm = 125
    assert clock.bpm_mismatch() is False
