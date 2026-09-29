from __future__ import annotations

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.config import BPM_DISPLAY_S


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
    assert clock.pulse_scale(1.05) > clock.pulse_scale(1.35)


def test_ejection_follows_squeeze() -> None:
    clock = BeatClock()
    clock.feed_beat(0.0)
    clock.feed_beat(0.8)
    squeeze = clock.cycle(0.85)
    eject = clock.cycle(0.92)
    rest = clock.cycle(1.35)
    assert squeeze.squeeze > eject.squeeze
    assert eject.eject > squeeze.eject
    assert rest.squeeze < 0.2
    assert rest.eject < 0.2
    assert squeeze.apex < rest.apex


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


def test_long_pause_counts_as_arrhythmia() -> None:
    clock = BeatClock()
    t = 0.0
    for _ in range(8):
        clock.feed_beat(t)
        t += 0.5
    clock.lost_if_silent(t + 2.0)
    assert clock.pop_arrhythmia(t + 2.0) is True
    assert clock.pop_arrhythmia(t + 2.1) is False


def test_displayed_bpm_uses_median_interval() -> None:
    clock = BeatClock()
    t = 0.0
    for _ in range(8):
        clock.feed_beat(t)
        t += 0.5
    clock.feed_beat(t)
    clock.feed_beat(t + 0.22)
    assert clock.bpm == 120


def test_oshilog_mismatch() -> None:
    clock = BeatClock()
    clock.feed_beat(0.0)
    clock.feed_beat(0.5)
    clock.oshilog_bpm = 70
    assert clock.bpm_mismatch() is True
    clock.oshilog_bpm = 125
    assert clock.bpm_mismatch() is False


def test_slow_bpm_is_not_clipped_to_thirty() -> None:
    clock = BeatClock()
    t = 0.0
    for _ in range(6):
        clock.feed_beat(t)
        t += 2.05
    assert 28 <= clock.bpm <= 30


def test_stall_gap_does_not_clip_bpm_to_minimum() -> None:
    clock = BeatClock()
    t = 0.0
    for _ in range(6):
        clock.feed_beat(t)
        t += 0.5
    assert clock.bpm == 120
    clock.feed_beat(t + 3.0)
    assert clock.bpm == 120
    assert clock.detected is True


def test_displayed_bpm_holds_through_brief_false_beats() -> None:
    clock = BeatClock()
    t = 0.0
    for _ in range(8):
        clock.feed_beat(t)
        t += 0.5
    assert clock.bpm == 120
    clock.publish_display(t)
    clock.feed_beat(t)
    clock.feed_beat(t + 0.2)
    clock.feed_beat(t + 0.35)
    assert clock.bpm == 120
    clock.publish_display(t + BPM_DISPLAY_S * 0.5)
    assert clock.bpm == 120


def test_preview_motion_matches_live_strength() -> None:
    clock = BeatClock()
    clock.feed_beat(0.0)
    clock.feed_beat(0.5)
    live = clock.pulse_scale(0.55)
    clock.lost_if_silent(2.0)
    assert clock.detected is False
    preview = max(clock.pulse_scale(2.0 + i * 0.02) for i in range(30))
    assert preview >= live * 0.95


def test_reacquire_after_lost_follows_new_tempo() -> None:
    clock = BeatClock()
    t = 0.0
    for _ in range(6):
        clock.feed_beat(t)
        t += 0.5
    clock.lost_if_silent(t + 2.0)
    assert clock.detected is False
    t = t + 2.0
    for _ in range(4):
        clock.feed_beat(t)
        t += 0.8
    assert clock.detected is True
    clock.publish_display(t + BPM_DISPLAY_S)
    assert 70 <= clock.bpm <= 80


def test_display_clock_smooths_uneven_audio_steps() -> None:
    from stream_heartbeat.clock import DisplayClock

    display = DisplayClock()
    audio = 0.0
    shown = []
    for i in range(240):
        wall = i * 0.016
        audio += 0.010 if i % 2 else 0.020
        shown.append(display.at(wall, audio))
    steps = [b - a for a, b in zip(shown[120:-1], shown[121:])]
    assert max(steps) - min(steps) < 0.004
    assert abs(shown[-1] - audio) < 0.03
    # 大きく飛んだら（止まっていた・巻き戻った）すぐ合わせる
    assert display.at(10.0, 50.0) == 50.0


def test_atria_contract_before_the_next_beat_right_then_left() -> None:
    from stream_heartbeat.clock import BeatClock

    clock = BeatClock()
    for i in range(8):
        clock.feed_beat(i * 0.8)
    last = 7 * 0.8
    # 心室が縮んでいる間は心房は縮まない
    early = clock.cycle(last + 0.08)
    assert early.atria_r == 0.0 and early.atria_l == 0.0
    samples = [clock.cycle(last + k * 0.005) for k in range(160)]
    right_peak = max(range(160), key=lambda k: samples[k].atria_r)
    left_peak = max(range(160), key=lambda k: samples[k].atria_l)
    assert 0.55 < right_peak * 0.005 < 0.8
    assert left_peak > right_peak
    # 心耳は一打ちのあと揺れ、しだいに収まる。左右で揺れ方がずれる
    flaps_r = [abs(c.auricle_r) for c in samples[:40]]
    assert max(flaps_r) > 0.3
    assert abs(samples[100].auricle_r) < max(flaps_r)
    assert any(abs(a.auricle_r - a.auricle_l) > 0.1 for a in samples[:40])

