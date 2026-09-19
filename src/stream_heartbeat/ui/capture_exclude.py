"""操作画面を OBS の画面取り込みから外す。配信用の窓には使わない。"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QWidget

_WDA_NONE = 0x00000000
_WDA_EXCLUDEFROMCAPTURE = 0x00000011
_dev_allow_capture = False
_DEV_ENV = "STREAMHEARTBEAT_DEV_ALLOW_CAPTURE"


def configure_dev_allow_capture(enabled: bool) -> None:
    """ソース起動専用。exe では常に取り込み除外のまま。"""
    global _dev_allow_capture
    _dev_allow_capture = bool(enabled)


def configure_dev_allow_capture_from_env() -> None:
    raw = os.environ.get(_DEV_ENV, "").strip().lower()
    configure_dev_allow_capture(raw in {"1", "true", "yes", "on"})


def should_exclude_from_capture() -> bool:
    if getattr(sys, "frozen", False):
        return True
    return not _dev_allow_capture


def exclude_from_capture(widget: QWidget) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        if not hwnd:
            return
        affinity = _WDA_NONE if not should_exclude_from_capture() else _WDA_EXCLUDEFROMCAPTURE
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
    except (AttributeError, OSError, ValueError):
        return
