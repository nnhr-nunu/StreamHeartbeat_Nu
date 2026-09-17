"""手元確認用の操作画面。配信出力とは別窓。"""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from stream_heartbeat import OPERATOR_WINDOW_TITLE, display_version
from stream_heartbeat.ui.output_window import OutputWindow


class OperatorWindow(QMainWindow):
    def __init__(self, output: OutputWindow) -> None:
        super().__init__()
        self._output = output
        self.setWindowTitle(OPERATOR_WINDOW_TITLE)
        self.setMinimumSize(360, 240)
        self.resize(420, 280)

        hint = QLabel(
            "環境確認用の骨格です。\n"
            "左が操作画面、緑の窓が OBS 取り込み用です。\n"
            f"{display_version()}"
        )
        hint.setWordWrap(True)

        toggle = QPushButton("配信用の窓を表示 / 隠す")
        toggle.clicked.connect(self._toggle_output)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(hint)
        layout.addWidget(toggle)
        self.setCentralWidget(root)

    def _toggle_output(self) -> None:
        if self._output.isVisible():
            self._output.hide()
        else:
            self._output.show()
            self._output.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._output.close()
        super().closeEvent(event)
