from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QLabel, QPushButton, QToolButton

from stream_heartbeat import OPERATOR_WINDOW_TITLE, OUTPUT_WINDOW_TITLE
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.styles import DARK_QSS


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
    assert "キャリブレーション（配信前調整）" in titles
    profiles = operator.findChildren(QComboBox)[0]
    assert not profiles.isEditable()
    folds = [btn for btn in operator.findChildren(QToolButton) if "推しログ(ぬ)連携" in btn.text()]
    assert folds and not folds[0].isChecked()
    tap = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "拍")
    assert not tap.isEnabled()
    start = next(btn for btn in operator.findChildren(QPushButton) if "録音開始" in btn.text())
    assert start.text().startswith("⏺️")
    start.click()
    assert tap.isEnabled()
    assert "録音停止" in start.text()
    assert start.text().startswith("■")
    guides = " ".join(label.text() for label in operator.findChildren(QLabel))
    assert "ヘッドホン" in guides
    assert "スペース" in guides
    start.click()
    assert not tap.isEnabled()
    assert "録音開始" in start.text()
    assert any("やめました" in label.text() for label in operator.findChildren(QLabel))
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
    assert "QComboBox::down-arrow" in DARK_QSS
    assert "combo_down" in DARK_QSS
    operator.close()
    output.close()
