from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QLabel, QPushButton, QToolButton

from stream_heartbeat import OPERATOR_WINDOW_TITLE, OUTPUT_WINDOW_TITLE
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


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
    folds = [btn for btn in operator.findChildren(QToolButton) if btn.text() == "推しログ(ぬ)連携"]
    assert folds and not folds[0].isChecked()
    tap = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "拍")
    assert not tap.isEnabled()
    start = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "録音開始")
    start.click()
    assert tap.isEnabled()
    guides = " ".join(label.text() for label in operator.findChildren(QLabel))
    assert "ヘッドホン" in guides
    assert "スペース" in guides
    operator.close()
    output.close()
