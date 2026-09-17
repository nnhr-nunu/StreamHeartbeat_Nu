from __future__ import annotations

import math
from unittest.mock import patch

from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.session import HeartSession


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

