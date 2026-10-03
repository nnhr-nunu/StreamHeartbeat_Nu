from __future__ import annotations

from stream_heartbeat.ui.win_front import bring_to_front


def test_bring_to_front_rejects_invalid_handle() -> None:
    assert bring_to_front(0) is False
    assert bring_to_front(-1) is False
