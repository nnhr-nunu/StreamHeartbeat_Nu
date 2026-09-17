from __future__ import annotations

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.ui.heart_ecg import ECG_COLOR, ECG_PEN_MIN, ecg_value


def test_ecg_is_thick_red_not_chroma_green() -> None:
    assert ECG_COLOR.red() >= 180
    assert ECG_COLOR.green() < 80
    assert ECG_COLOR.blue() < 80
    assert ECG_PEN_MIN >= 8


def test_qrs_peaks_right_after_the_beat() -> None:
    peak = max(ecg_value(dt / 1000.0, 0.8) for dt in range(0, 120))
    peak_at = max(range(0, 120), key=lambda dt: ecg_value(dt / 1000.0, 0.8))
    assert peak > 0.9
    assert 15 <= peak_at <= 45
    assert ecg_value(0.5, 0.8) < 0.08
    assert ecg_value(-0.1, 0.8) == 0.0


def test_t_wave_follows_qrs() -> None:
    assert ecg_value(0.34, 0.8) > 0.15
    assert ecg_value(0.34, 0.8) < ecg_value(0.028, 0.8)


def test_clock_origin_before_uses_real_beats() -> None:
    clock = BeatClock()
    for t in (0.0, 0.8, 1.6, 2.5):
        clock.feed_beat(t)
    assert clock.origin_before(1.7) == 1.6
    assert clock.origin_before(0.9) == 0.8
    assert clock.origin_before(2.6) == 2.5
    assert clock.origin_before(-0.3) < 0.0
