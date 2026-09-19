from __future__ import annotations

from stream_heartbeat.ui.win_present import redraw_hwnd


def test_redraw_hwnd_rejects_invalid_handle() -> None:
    assert redraw_hwnd(0) is False
    assert redraw_hwnd(-1) is False
