from __future__ import annotations

from stream_heartbeat.tap import chunks_near_taps, tap_interval


def test_tap_interval_needs_four_clicks() -> None:
    assert tap_interval([0.0, 0.8, 1.6]) == 0.0
    assert 0.75 < tap_interval([0.0, 0.8, 1.6, 2.4, 3.2]) < 0.85


def test_tap_interval_ignores_one_wild_gap() -> None:
    times = [0.0, 0.8, 1.6, 3.5, 4.3]
    assert 0.75 < tap_interval(times) < 0.9


def test_chunks_near_taps_take_peak_before_click() -> None:
    sr = 1000.0
    samples = [0.01] * 2000
    for i in range(40):
        samples[800 + i] = 0.6
    chunks = chunks_near_taps(samples, sr, 0.0, [1.05], pre=0.32, post=0.04)
    assert chunks
    assert max(abs(x) for x in chunks[0]) > 0.4
