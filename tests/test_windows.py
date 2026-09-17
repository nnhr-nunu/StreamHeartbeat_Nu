from __future__ import annotations

from PySide6.QtWidgets import QApplication

from stream_heartbeat import OPERATOR_WINDOW_TITLE, OUTPUT_WINDOW_TITLE
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


def test_two_windows_have_obs_titles(qapp: QApplication) -> None:
    del qapp
    output = OutputWindow()
    operator = OperatorWindow(output)
    assert operator.windowTitle() == OPERATOR_WINDOW_TITLE
    assert output.windowTitle() == OUTPUT_WINDOW_TITLE
    operator.close()
    output.close()
