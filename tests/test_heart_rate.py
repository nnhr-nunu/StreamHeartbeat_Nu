"""Bluetooth の心拍計の値の読み取りと、心拍数から拍を刻む部分。"""

from __future__ import annotations

import pytest

from stream_heartbeat.heart_rate import (
    STALE_S,
    BeatsFromRate,
    HeartRateReading,
    parse_heart_rate,
)
from stream_heartbeat.session import HeartSession


def _run(beats: BeatsFromRate, start: float, end: float) -> list[float]:
    """操作画面のタイマーのように、0.1 秒ごとに拍を聞く。"""
    out: list[float] = []
    steps = round((end - start) / 0.1)
    for i in range(1, steps + 1):
        out.extend(beats.due(start + i * 0.1))
    return out


def test_parse_8bit_heart_rate() -> None:
    assert parse_heart_rate(bytes([0x00, 72])) == HeartRateReading(bpm=72)


def test_parse_16bit_heart_rate_with_contact_energy_and_rr() -> None:
    # 16bit の心拍数・肌に触れている・消費エネルギー・RR 間隔 2 つ（1/1024 秒単位）
    data = bytes([0x1F]) + (75).to_bytes(2, "little") + (12).to_bytes(2, "little")
    data += (820).to_bytes(2, "little") + (790).to_bytes(2, "little")
    reading = parse_heart_rate(data)
    assert reading is not None
    assert reading.bpm == 75 and reading.contact is True
    assert reading.rr == pytest.approx((820 / 1024, 790 / 1024))


def test_parse_reports_no_contact_and_short_data() -> None:
    reading = parse_heart_rate(bytes([0x04, 0]))
    assert reading is not None and reading.contact is False
    assert parse_heart_rate(b"") is None
    assert parse_heart_rate(bytes([0x01, 70])) is None


def test_beats_follow_the_heart_rate() -> None:
    beats = BeatsFromRate()
    assert beats.due(1.0) == []
    beats.feed(HeartRateReading(bpm=60), 10.0)
    assert beats.due(10.0) == [10.0]
    assert _run(beats, 10.0, 12.5) == pytest.approx([11.0, 12.0])
    beats.feed(HeartRateReading(bpm=120), 12.5)
    # 次の拍（13.0）から新しい心拍数の間隔になる
    assert _run(beats, 12.5, 14.1) == pytest.approx([13.0, 13.5, 14.0])


def test_beats_use_rr_intervals_when_sent() -> None:
    beats = BeatsFromRate()
    beats.feed(HeartRateReading(bpm=60, rr=(0.9, 1.1, 5.0)), 0.0)
    # 外れた RR（5 秒）は使わず、使い切ったら心拍数の間隔
    beats.due(0.0)
    assert _run(beats, 0.0, 4.05) == pytest.approx([0.9, 2.0, 3.0, 4.0])


def test_beats_stop_when_the_monitor_goes_quiet_or_loses_contact() -> None:
    beats = BeatsFromRate()
    beats.feed(HeartRateReading(bpm=60), 0.0)
    beats.due(1.0)
    assert beats.due(STALE_S + 1.0) == []
    assert not beats.beating
    # 肌から離れた・あり得ない値では動き出さない
    beats.feed(HeartRateReading(bpm=70, contact=False), 10.0)
    beats.feed(HeartRateReading(bpm=0), 10.0)
    assert beats.due(11.0) == []


def test_beats_skip_ahead_after_the_window_stalls() -> None:
    beats = BeatsFromRate()
    beats.feed(HeartRateReading(bpm=60), 0.0)
    beats.due(0.5)
    beats.feed(HeartRateReading(bpm=60), 4.0)
    # 4 秒止まっていた間の拍はまとめて出さず、今から刻み直す
    assert beats.due(4.0) == [4.0]


def test_session_moves_with_beats_from_a_monitor() -> None:
    session = HeartSession()
    for i in range(8):
        session.tick(i * 0.8, [], beats=[i * 0.8])
    assert session.clock.detected
    assert session.clock.bpm == 75
