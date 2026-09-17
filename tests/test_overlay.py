from __future__ import annotations

from stream_heartbeat.overlay import OverlayState


def test_beat_text_fades_and_caps_at_three() -> None:
    state = OverlayState(rng=lambda: 0.5)
    for i in range(5):
        state.on_beat(i * 0.05, "ドクン")
    assert len(state.bursts_at(0.2)) == 3
    assert state.bursts_at(0.2)[0].alpha > 0


def test_arrhythmia_uses_same_burst_channel() -> None:
    state = OverlayState(rng=lambda: 0.2)
    state.on_arrhythmia(1.0)
    bursts = state.bursts_at(1.1)
    assert bursts
    assert bursts[0].text == "不整脈！"
    assert 0.0 < bursts[0].alpha <= 1.0


def test_positions_stay_inside_margin() -> None:
    values = iter([0.0, 1.0, 0.0, 1.0])
    state = OverlayState(rng=lambda: next(values))
    state.on_beat(0.0, "ドクン")
    x, y = state.bursts_at(0.0)[0].pos
    assert 0.15 <= x <= 0.85
    assert 0.15 <= y <= 0.85
