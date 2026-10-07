"""テスト全体の前準備。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from stream_heartbeat.i18n import LANG_JA, set_language
from stream_heartbeat.render.gl_platform import set_default_format

# アプリと同じく、QApplication より前に OpenGL の既定を決める（Mac だけ 4.1 Core）
set_default_format()


@pytest.fixture(autouse=True)
def _japanese_ui() -> Iterator[None]:
    """既存のテストは日本語の文字を前提にしている。言語はテストごとに日本語へ戻す。"""
    set_language(LANG_JA)
    yield
    set_language(LANG_JA)


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """操作画面は起動すると新しい版を GitHub に聞きに行く。テストでは通信させない。"""
    monkeypatch.setattr("stream_heartbeat.update_check.fetch_newer_version", lambda: None)


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """操作画面は閉じるときや自動保存でプロファイルを書くので、本物の保存先に書かせない。"""
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )
