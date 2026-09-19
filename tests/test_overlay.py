from __future__ import annotations

import pytest

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
    values = iter([0.0, 1.0, 0.5])
    state = OverlayState(rng=lambda: next(values))
    state.on_beat(0.0, "ドクン", origin=(0.5, 0.22), jitter=0.05)
    x, y = state.bursts_at(0.0)[0].pos
    assert 0.08 <= x <= 0.92
    assert 0.08 <= y <= 0.45


def test_beat_text_uses_origin_and_stays_above_heart() -> None:
    state = OverlayState(rng=lambda: 0.5)
    state.on_beat(0.0, "❤", origin=(0.5, 0.22), jitter=0.0)
    x, y = state.bursts_at(0.05)[0].pos
    assert x == pytest.approx(0.5, abs=0.01)
    assert y == pytest.approx(0.22, abs=0.01)
    assert y < 0.4


def _pos_with_jitter(jitter: float) -> tuple[float, float]:
    values = iter([0.0, 1.0, 0.5])
    state = OverlayState(rng=lambda: next(values))
    state.on_beat(0.0, "❤", origin=(0.5, 0.22), jitter=jitter, tilt=0.0)
    return state.bursts_at(0.0)[0].pos


def test_zero_jitter_stays_at_origin() -> None:
    x, y = _pos_with_jitter(0.0)
    assert x == pytest.approx(0.5)
    assert y == pytest.approx(0.22)


def test_larger_jitter_spreads_farther() -> None:
    near = _pos_with_jitter(0.05)
    far = _pos_with_jitter(0.30)
    assert abs(far[0] - 0.5) > abs(near[0] - 0.5)
    assert abs(far[1] - 0.22) > abs(near[1] - 0.22)


def test_tilt_leans_toward_heart_center() -> None:
    left = OverlayState(rng=lambda: 0.5)
    left.on_beat(0.0, "❤", origin=(0.32, 0.22), jitter=0.0, tilt=1.0)
    right = OverlayState(rng=lambda: 0.5)
    right.on_beat(0.0, "❤", origin=(0.68, 0.22), jitter=0.0, tilt=1.0)
    assert left.bursts_at(0.0)[0].angle < -8
    assert right.bursts_at(0.0)[0].angle > 8


def test_tilt_zero_stays_upright() -> None:
    state = OverlayState(rng=lambda: 0.0)
    state.on_beat(0.0, "❤", origin=(0.32, 0.22), jitter=0.0, tilt=0.0)
    assert state.bursts_at(0.0)[0].angle == pytest.approx(0.0)


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
