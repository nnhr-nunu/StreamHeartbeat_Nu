"""画面外の窓でも絵の全体を書き直す（Windows）。

StreamMediaViewer(ぬ) と同じく、画面の外へはみ出した配信用窓を
OBS が古い絵のまま持たないようにする。
"""

from __future__ import annotations

import sys
from ctypes import c_void_p
from ctypes.wintypes import DWORD

_RDW_INVALIDATE = 0x0001
_RDW_ERASE = 0x0004
_RDW_ALLCHILDREN = 0x0080
_RDW_UPDATENOW = 0x0100
_RDW_FRAME = 0x0400


def redraw_hwnd(hwnd: int) -> bool:
    """画面外の領域も含め、既存の HWND を再描画する。重ね描きはしない。"""
    if sys.platform != "win32" or hwnd <= 0:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RedrawWindow.restype = wintypes.BOOL
        user32.RedrawWindow.argtypes = [wintypes.HWND, c_void_p, c_void_p, DWORD]
        return bool(
            user32.RedrawWindow(
                wintypes.HWND(hwnd),
                None,
                None,
                _RDW_INVALIDATE | _RDW_ERASE | _RDW_ALLCHILDREN | _RDW_UPDATENOW | _RDW_FRAME,
            )
        )
    except (AttributeError, OSError, ValueError, TypeError):
        return False
