from __future__ import annotations

import io
import json
from urllib.error import URLError

import pytest

from stream_heartbeat.i18n import LANG_EN, set_language
from stream_heartbeat.ui import update_notice
from stream_heartbeat.ui.update_notice import UpdateNotice
from stream_heartbeat.update_check import (
    RELEASE_PAGE,
    UpdateChecker,
    fetch_newer_version,
    is_newer,
    version_in_title,
)


def _release(name: str) -> str:
    return json.dumps({"name": name, "tag_name": "latest"})


def _opener(payload: str):
    def opener(_req, timeout: float, context) -> io.BytesIO:
        return io.BytesIO(payload.encode("utf-8"))

    return opener


def test_version_in_title() -> None:
    assert version_in_title(_release("最新版 v0.2.0 / Latest (unzip and run)")) == "0.2.0"
    assert version_in_title(_release("最新版 / Latest (unzip and run)")) is None
    assert version_in_title("not-json") is None
    assert version_in_title("[1]") is None
    assert version_in_title(json.dumps({"name": None})) is None


def test_is_newer() -> None:
    assert is_newer("0.2.1", "0.2.0")
    assert is_newer("0.10.0", "0.9.9")
    assert is_newer("1.0", "0.9.9")
    assert not is_newer("0.2.0", "0.2.0")
    assert not is_newer("0.2", "0.2.0")
    assert not is_newer("0.1.9", "0.2.0")
    assert not is_newer("abc", "0.2.0")


def test_fetch_returns_only_a_newer_version() -> None:
    payload = _release("最新版 v0.3.0 / Latest")
    assert fetch_newer_version("0.2.0", opener=_opener(payload)) == "0.3.0"
    assert fetch_newer_version("0.3.0", opener=_opener(payload)) is None
    assert fetch_newer_version("0.4.0", opener=_opener(payload)) is None


@pytest.mark.parametrize("error", [URLError("offline"), TimeoutError(), OSError("tls")])
def test_fetch_is_silent_when_offline(error: Exception) -> None:
    def opener(_req, timeout: float, context):
        raise error

    assert fetch_newer_version("0.2.0", opener=opener) is None


def test_fetch_ignores_broken_payload() -> None:
    assert fetch_newer_version("0.2.0", opener=_opener("<html>rate limited</html>")) is None


def test_checker_runs_in_background() -> None:
    checker = UpdateChecker(fetch=lambda: "9.9.9")
    assert not checker.started
    checker.start()
    checker._thread.join(2.0)
    assert checker.finished
    assert checker.newer == "9.9.9"


def test_checker_survives_a_failing_fetch() -> None:
    def broken() -> str | None:
        raise RuntimeError("boom")

    checker = UpdateChecker(fetch=broken)
    checker.start()
    checker._thread.join(2.0)
    assert checker.finished
    assert checker.newer is None


def _wait_done(qtbot, notice: UpdateNotice, checker: UpdateChecker) -> None:
    qtbot.waitUntil(lambda: checker.finished and not notice._timer.isActive(), timeout=3000)


def test_notice_stays_hidden_without_a_newer_version(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(update_notice, "START_DELAY_MS", 0)
    checker = UpdateChecker(fetch=lambda: None)
    notice = UpdateNotice(checker)
    qtbot.addWidget(notice)
    _wait_done(qtbot, notice, checker)
    assert notice.isHidden()
    assert notice.text() == ""


def test_notice_links_to_the_release_page(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(update_notice, "START_DELAY_MS", 0)
    checker = UpdateChecker(fetch=lambda: "0.9.0")
    notice = UpdateNotice(checker)
    qtbot.addWidget(notice)
    _wait_done(qtbot, notice, checker)
    assert not notice.isHidden()
    assert f'href="{RELEASE_PAGE}"' in notice.text()
    assert "新しい版 v0.9.0 が出ています" in notice.text()
    assert notice.openExternalLinks()

    set_language(LANG_EN)
    notice.retranslate()
    assert "A new version (v0.9.0) is available" in notice.text()
