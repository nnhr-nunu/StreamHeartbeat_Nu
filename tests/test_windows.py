from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QToolButton,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE, OUTPUT_WINDOW_TITLE
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


@pytest.fixture(autouse=True)
def _isolate_operator_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )


def test_two_windows_have_obs_titles(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    assert operator.windowTitle() == OPERATOR_WINDOW_TITLE
    assert output.windowTitle() == OUTPUT_WINDOW_TITLE
    operator.close()
    output.close()


def test_operator_stays_on_top_and_labels(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    flag = Qt.WindowType.WindowStaysOnTopHint
    assert operator.windowFlags() & flag
    assert output.windowFlags() & flag
    titles = [box.title() for box in operator.findChildren(QGroupBox)]
    assert "心拍の補正（配信前調整）" in titles
    profiles = operator.findChildren(QComboBox)[0]
    assert not profiles.isEditable()
    folds = [btn for btn in operator.findChildren(QToolButton) if "推しログ(ぬ)連携" in btn.text()]
    assert folds and not folds[0].isChecked()
    tap = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "拍")
    assert not tap.isEnabled()
    primary = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "補正開始")
    discard = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "補正を破棄")
    reset = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "設定を初期化")
    assert not discard.isEnabled()
    assert not reset.isEnabled()
    primary.click()
    assert tap.isEnabled()
    assert primary.text() == "補正を保存"
    assert discard.isEnabled()
    guides = " ".join(label.text() for label in operator.findChildren(QLabel))
    assert "ヘッドホン" in guides
    assert "スペース" in guides
    assert "4回" in guides or "４回" in guides
    assert "補正開始" in guides
    assert "補正を破棄" in guides
    assert "設定を初期化" in guides
    assert "録音停止" not in guides
    session.tick(session.now + 0.1, [0.2] * 80, sample_rate=1000.0)
    primary.click()
    assert not tap.isEnabled()
    assert primary.text() == "補正開始"
    assert not discard.isEnabled()
    assert reset.isEnabled()
    assert any("保存しました" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()


def test_save_notice_survives_tick(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    save = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "上書き保存")
    save.click()
    operator._on_tick()
    assert any("保存しました" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()


def test_fold_and_combo_show_pulldown_mark(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    folds = operator.findChildren(QToolButton)
    texts = [btn.text() for btn in folds]
    assert any(text.startswith("▶") or text.startswith("▼") for text in texts)
    assert any("同期文字" in text for text in texts)
    marks = [lab for lab in operator.findChildren(QLabel) if lab.objectName() == "comboMark"]
    assert len(marks) >= 4
    assert all(lab.text() == "▼" for lab in marks)
    assert len(operator.findChildren(QComboBox)) >= 4
    operator.close()
    output.close()


def test_detect_banner_stays_above_scroll(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    banner = operator.findChild(QFrame, "detectBanner")
    assert banner is not None
    shell = operator.centralWidget()
    assert shell is not None
    layout = shell.layout()
    assert layout is not None
    assert layout.itemAt(0).widget() is banner
    assert operator._status.parent() is banner
    operator.close()
    output.close()


def test_operator_marks_preview_and_live(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator._on_tick()
    assert "プレビュー" in operator._status.text()
    session.clock.feed_beat(0.0)
    session.clock.feed_beat(0.5)
    operator._on_tick()
    assert "連動中" in operator._status.text()
    session.clock.lost_if_silent(3.0)
    operator._on_tick()
    assert "プレビュー" in operator._status.text()
    assert "ロスト" in operator._status.text()
    operator.close()
    output.close()


def test_discard_aborts_current_correction(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    primary = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "補正開始")
    discard = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "補正を破棄")
    saved = [list(chunk) for chunk in session.profile.calibration]
    primary.click()
    session.tick(session.now + 0.1, [0.2] * 80, sample_rate=1000.0)
    discard.click()
    assert primary.text() == "補正開始"
    assert not discard.isEnabled()
    assert session.recording is False
    assert [list(chunk) for chunk in session.profile.calibration] == saved
    assert any("破棄" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()


def test_reset_clears_saved_heart_sound(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator._confirm_reset = lambda: True  # type: ignore[method-assign]
    session.profile.calibration.append([0.2] * 20)
    operator._sync_cal_ui()
    reset = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "設定を初期化")
    assert reset.isEnabled()
    reset.click()
    assert session.profile.calibration == []
    assert not reset.isEnabled()
    assert any("初期化" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()
