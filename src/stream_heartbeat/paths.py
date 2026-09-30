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
        localappdata = _user_data_root()
    return localappdata / APP_DIR_NAME


def cache_dir(data_dir: Path | None = None) -> Path:
    """計算に時間のかかる結果（立体心臓の形など）を残す場所。消しても次の起動で作り直す。"""
    return (data_dir if data_dir is not None else resolve_data_dir()) / "cache"


def _user_data_root() -> Path:
    """OS ごとのアプリの保存場所（Windows は %LOCALAPPDATA%、Mac は Application Support）。"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    env = os.environ.get("LOCALAPPDATA")
    return Path(env) if env else Path.home() / "AppData" / "Local"
