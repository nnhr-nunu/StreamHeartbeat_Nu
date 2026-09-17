"""アプリ専用アイコン。窓の枠と exe で同じ絵を使う。"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget

_ICON_STEM = "app_icon"
_WINDOWS_APP_ID = "StreamHeartbeat.Nu"
PROCESS_DISPLAY_NAME = "StreamHeartbeat(ぬ)"


def assets_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets"


def app_icon_path() -> Path:
    folder = assets_dir()
    ico = folder / f"{_ICON_STEM}.ico"
    if ico.is_file():
        return ico
    return folder / f"{_ICON_STEM}.png"


def load_app_icon() -> QIcon:
    path = app_icon_path()
    if not path.is_file():
        return QIcon()
    return QIcon(str(path))


def configure_process_identity() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_WINDOWS_APP_ID)
        except (AttributeError, OSError):
            pass
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(PROCESS_DISPLAY_NAME)
        except (AttributeError, OSError, TypeError):
            pass


def apply_app_icon(target: QWidget | QApplication) -> None:
    icon = load_app_icon()
    if icon.isNull():
        return
    target.setWindowIcon(icon)
    app = QApplication.instance()
    if app is not None and app is not target:
        app.setWindowIcon(icon)
