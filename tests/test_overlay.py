from __future__ import annotations

from stream_heartbeat.overlay import OverlayState, burst_font_px, burst_opacity


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


def test_burst_font_and_opacity_follow_settings() -> None:
    assert burst_font_px(400.0, 1.0) == 24
    assert burst_font_px(400.0, 2.0) == 48
    assert burst_font_px(400.0, 0.5) == 12
    assert burst_opacity(1.0, 0.4) == 0.4
    assert burst_opacity(0.5, 0.5) == 0.25


def test_positions_stay_inside_margin() -> None:
    values = iter([0.0, 1.0, 0.0, 1.0])
    state = OverlayState(rng=lambda: next(values))
    state.on_beat(0.0, "ドクン")
    x, y = state.bursts_at(0.0)[0].pos
    assert 0.15 <= x <= 0.85
    assert 0.15 <= y <= 0.85


def test_tap_ripple_expands_and_fades() -> None:
    state = OverlayState()
    state.on_ripple(1.0)
    early = state.ripples_at(1.05)
    late = state.ripples_at(1.4)
    gone = state.ripples_at(1.7)
    assert early
    assert late
    assert early[0].radius < late[0].radius
    assert late[0].alpha < early[0].alpha
    assert gone == []
