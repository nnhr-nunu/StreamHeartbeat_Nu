"""テスト全体の前準備。"""

from __future__ import annotations

from pathlib import Path

import pytest

from stream_heartbeat.render.gl_platform import set_default_format

# アプリと同じく、QApplication より前に OpenGL の既定を決める（Mac だけ 4.1 Core）
set_default_format()


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """操作画面は閉じるときや自動保存でプロファイルを書くので、本物の保存先に書かせない。"""
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )
