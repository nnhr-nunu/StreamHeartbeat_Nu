"""プロファイル保存先。配布 zip には入れない。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from stream_heartbeat.config import APP_DIR_NAME, PORTABLE_DIRNAME


def install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resolve_data_dir(
    root: Path | None = None,
    *,
    localappdata: Path | None = None,
) -> Path:
    base = root if root is not None else install_dir()
    portable = base / PORTABLE_DIRNAME
    if portable.is_dir():
        return portable
    if localappdata is None:
        env = os.environ.get("LOCALAPPDATA")
        localappdata = Path(env) if env else Path.home() / "AppData" / "Local"
    return localappdata / APP_DIR_NAME
