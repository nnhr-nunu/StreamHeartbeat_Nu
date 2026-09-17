from __future__ import annotations

from stream_heartbeat.oshilog import parse_aux_bpm


def test_parse_aux_bpm() -> None:
    assert parse_aux_bpm('{"bpm": 88}') == 88
    assert parse_aux_bpm("not-json") is None
    assert parse_aux_bpm('{"bpm": 0}') is None
