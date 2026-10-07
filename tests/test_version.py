import re
from pathlib import Path

import pytest

from stream_heartbeat import __version__, display_version

ROOT = Path(__file__).resolve().parents[1]


def test_version_format() -> None:
    # 更新のお知らせは版を数の並びとして比べる
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert display_version() == f"v{__version__}"


def test_version_has_a_single_source() -> None:
    # 版は __init__.py だけに書く。pyproject や配布用の spec に書くと上げ忘れる
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version\s*=\s*"', pyproject, re.M) is None
    assert 'attr = "stream_heartbeat.__version__"' in pyproject
    for spec in ("StreamHeartbeat-windows.spec", "StreamHeartbeat-macos.spec"):
        text = (ROOT / "packaging" / spec).read_text(encoding="utf-8")
        assert "__init__.py" in text and "__version__" in text


def test_windows_version_template_fills_in() -> None:
    # pefile が要るので、PyInstaller の Windows 版がある所だけで確かめる
    versioninfo = pytest.importorskip("PyInstaller.utils.win32.versioninfo")
    template = (ROOT / "packaging" / "windows_version.txt").read_text(encoding="utf-8")
    assert "@VERSION@" in template and "@VERSION_TUPLE@" in template
    filled = template.replace("@VERSION_TUPLE@", "0, 2, 0, 0").replace("@VERSION@", "0.2.0")
    # PyInstaller が版のファイルを読むときと同じく、versioninfo の名前で式として読む
    info = eval(filled, dict(vars(versioninfo)))
    assert isinstance(info, versioninfo.VSVersionInfo)
    assert info.ffi.fileVersionMS == (0 << 16) | 2
