"""配布 zip に入れる利用規約・ライセンスの文書。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import PySide6
from PySide6.QtCore import qVersion

ROOT = Path(__file__).resolve().parents[1]


def _write_licenses():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "write_licenses", ROOT / "packaging" / "write_licenses.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_license_documents_are_written(tmp_path: Path) -> None:
    _write_licenses().write(tmp_path)
    assert (tmp_path / "利用規約.txt").is_file()
    out = tmp_path / "ライセンス"
    # LGPL の Qt を配るのに要る全文（LGPL v3 は GPL v3 の上に立つので両方）と、FFmpeg の LGPL v2.1
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in (out / "LGPL-3.0.txt").read_text("utf-8")
    assert "Version 3" in (out / "GPL-3.0.txt").read_text("utf-8")
    assert "Version 2.1" in (out / "LGPL-2.1.txt").read_text("utf-8")
    assert "Python Software Foundation" in (out / "Python.txt").read_text("utf-8")
    notices = (out / "同梱しているソフト.txt").read_text("utf-8")
    # 版は zip に入れた Qt と同じで、ソースの入手先も同じ版を指す
    assert f"Qt {qVersion()}" in notices
    assert f"PySide6-{PySide6.__version__}-src" in notices
    assert "FFmpeg" in notices and "{" not in notices
    # Bluetooth の心拍計に使う bleak も、ライセンスの文書と一緒に載せる
    assert "■ bleak " in notices and (out / "bleak-LICENSE.txt").is_file()
