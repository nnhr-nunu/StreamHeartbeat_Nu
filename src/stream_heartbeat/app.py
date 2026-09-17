"""操作用と配信用の 2 窓を起動する。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("StreamHeartbeat(ぬ)")
    output = OutputWindow()
    operator = OperatorWindow(output)
    operator.show()
    output.show()
    return app.exec()
