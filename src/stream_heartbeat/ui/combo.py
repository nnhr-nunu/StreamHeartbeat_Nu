"""一覧の右端に ▼ を常に出すコンボ。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent, QShowEvent, QWheelEvent
from PySide6.QtWidgets import QComboBox, QLabel, QWidget


class MarkedComboBox(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mark = QLabel("▼", self)
        self._mark.setObjectName("comboMark")
        self._mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._place_mark()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._place_mark()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.view() is not None and self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()

    def _place_mark(self) -> None:
        self._mark.adjustSize()
        self._mark.raise_()
        margin = 10
        self._mark.move(
            self.width() - self._mark.width() - margin,
            (self.height() - self._mark.height()) // 2,
        )
