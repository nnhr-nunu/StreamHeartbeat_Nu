"""起動した窓を一番手前に出してフォーカスを渡す（Windows）。

Windows は起動の仕方によって（起動.bat 経由・起動を待つ間にほかの窓を触ったときなど）、
新しい窓が手前に出るのを止めてタスクバーを光らせるだけにする。Qt の activateWindow も同じく止まる。
いま手前にある窓の入力にいったん相乗りして前へ出し、それでも出なければ Alt キーを押したことにして
出す（どちらも、前へ出る許しをもらうためによく使われる方法）。
"""

from __future__ import annotations

import sys

_SW_RESTORE = 9
_VK_MENU = 0x12
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002


def bring_to_front(hwnd: int) -> bool:
    """hwnd の窓を一番手前にしてフォーカスを渡す。手前に出せたら True（Windows 以外は False）。"""
    if sys.platform != "win32" or hwnd <= 0:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        byte, dword = wintypes.BYTE, wintypes.DWORD
        user32.keybd_event.argtypes = [byte, byte, dword, ctypes.c_void_p]

        def in_front() -> bool:
            return (user32.GetForegroundWindow() or 0) == hwnd

        target = wintypes.HWND(hwnd)
        if user32.IsIconic(target):
            user32.ShowWindow(target, _SW_RESTORE)
        if in_front():
            return True
        front = user32.GetForegroundWindow()
        front_thread = user32.GetWindowThreadProcessId(front, None) if front else 0
        me = kernel32.GetCurrentThreadId()
        attached = bool(
            front_thread and front_thread != me and user32.AttachThreadInput(me, front_thread, True)
        )
        try:
            user32.BringWindowToTop(target)
            user32.SetForegroundWindow(target)
        finally:
            if attached:
                user32.AttachThreadInput(me, front_thread, False)
        if in_front():
            return True
        # Alt を押したことにすると、この窓の持ち主が「最後に入力を受けた」扱いになり前へ出せる
        user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_EXTENDEDKEY, None)
        user32.SetForegroundWindow(target)
        user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP, None)
        return in_front()
    except (AttributeError, OSError, ValueError, TypeError):
        return False
