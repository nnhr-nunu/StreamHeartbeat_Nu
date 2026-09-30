from __future__ import annotations

from pathlib import Path

from stream_heartbeat import paths
from stream_heartbeat.paths import resolve_data_dir


def test_portable_data_dir_wins(tmp_path: Path) -> None:
    portable = tmp_path / "app" / "data"
    portable.mkdir(parents=True)
    appdata = tmp_path / "appdata"
    got = resolve_data_dir(tmp_path / "app", localappdata=appdata)
    assert got == portable


def test_appdata_when_no_portable(tmp_path: Path) -> None:
    install = tmp_path / "app"
    install.mkdir()
    appdata = tmp_path / "appdata"
    got = resolve_data_dir(install, localappdata=appdata)
    assert got == appdata / "StreamHeartbeat_Nu"


def test_mac_keeps_data_in_application_support(tmp_path: Path, monkeypatch) -> None:
    install = tmp_path / "app"
    install.mkdir()
    home = tmp_path / "home"
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.Path, "home", lambda: home)
    # Mac では Windows のアプリデータの場所は使わない
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "windows"))
    got = resolve_data_dir(install)
    assert got == home / "Library" / "Application Support" / "StreamHeartbeat_Nu"
