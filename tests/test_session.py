from __future__ import annotations

from stream_heartbeat.session import HeartSession


def test_tick_feeds_clock_from_peaks() -> None:
    session = HeartSession()
    t = 0.0
    for i in range(2500):
        sample = 0.9 if i % 500 < 40 else 0.01
        session.tick(t, [sample])
        t += 0.001
    assert session.clock.bpm >= 100
    assert session.overlay.bursts_at(t - 0.001)
