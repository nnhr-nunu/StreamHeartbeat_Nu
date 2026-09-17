"""OBS 取り込み用の配信用ウィンドウ。デバッグ文字は出さない。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QMainWindow, QWidget

from stream_heartbeat import OUTPUT_WINDOW_TITLE


class OutputCanvas(QWidget):
    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 255, 0))


class OutputWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(OUTPUT_WINDOW_TITLE)
        self.setMinimumSize(480, 480)
        self.resize(720, 720)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        canvas = OutputCanvas()
        canvas.setObjectName("outputCanvas")
        self.setCentralWidget(canvas)
