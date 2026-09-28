from __future__ import annotations

import threading

from stream_heartbeat.oshilog import AuxBpmPoller, fetch_aux_bpm, parse_aux_bpm


def test_parse_aux_bpm() -> None:
    assert parse_aux_bpm('{"bpm": 88}') == 88
    assert parse_aux_bpm("not-json") is None
    assert parse_aux_bpm('{"bpm": 0}') is None


def test_parse_aux_bpm_ignores_non_object() -> None:
    assert parse_aux_bpm("[88]") is None


def test_fetch_aux_bpm_ignores_url_without_scheme() -> None:
    # https:// を付け忘れた URL で操作画面ごと落ちない
    assert fetch_aux_bpm("example.com/bpm") is None


def test_poller_fetches_in_background() -> None:
    gate = threading.Event()

    def slow_fetch(_url: str) -> int | None:
        gate.wait(2.0)
        return 72

    poller = AuxBpmPoller(fetch=slow_fetch)
    assert poller.poll("https://example.invalid/bpm") is None  # 待たずにすぐ戻る
    gate.set()
    poller._thread.join(2.0)
    assert poller.poll("https://example.invalid/bpm") == 72
    assert poller.poll("") is None
