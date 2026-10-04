"""起動中に出す「お待ちください」の小窓。

窓の組み立てと心臓の形の読み込みで数秒かかり、その間は何も出ないので固まったように見える。
Qt が動き出したらすぐにこれを出し、段階ごとに文言を変える
（配信用の窓ではないので OBS には映らない）。

Qt の QSplashScreen は出すたびに「画面に映るまで」最大 1 秒待つので使わず、枠のない小窓で描く。
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QApplication, QWidget

from stream_heartbeat.i18n import tr
from stream_heartbeat.ui.app_icon import PROCESS_DISPLAY_NAME, load_app_icon

SPLASH_W = 360
SPLASH_H = 132
WAIT_TEXT = "起動しています。お待ちください…"
# 出した直後に画面へ映るのを待つ上限（秒）。この後しばらく手が離せないため
_EXPOSE_WAIT_S = 0.3
_BG = QColor(18, 18, 18)
_EDGE = QColor(90, 61, 122)
_TEXT = QColor(232, 232, 232)
_SUB = QColor(170, 170, 170)


class StartupSplash(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(SPLASH_W, SPLASH_H)
        self._icon = load_app_icon()
        self._step = ""
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center().x() - SPLASH_W // 2, area.center().y() - SPLASH_H // 2)

    @property
    def step_text(self) -> str:
        return self._step

    def show_now(self) -> None:
        """出して、画面に映るまで少しだけ待つ。"""
        self.show()
        self.raise_()
        deadline = time.perf_counter() + _EXPOSE_WAIT_S
        handle = self.windowHandle()
        while time.perf_counter() < deadline:
            QApplication.processEvents()
            if handle is not None and handle.isExposed():
                break
        self.repaint()

    def step(self, text: str) -> None:
        """今やっていることを下に出し、すぐ描き直す（この後しばらく手が離せないため）。"""
        self._step = text
        self.repaint()
        QApplication.processEvents()

    def finish(self, _main: QWidget) -> None:
        self.close()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt の名前)
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(1, 1, SPLASH_W - 2, SPLASH_H - 2), 12, 12)
        painter.fillPath(frame, _BG)
        painter.setPen(_EDGE)
        painter.drawPath(frame)
        if not self._icon.isNull():
            self._icon.paint(painter, 22, 24, 56, 56)
        title = QFont()
        title.setPixelSize(19)
        title.setBold(True)
        painter.setFont(title)
        painter.setPen(_TEXT)
        left = 94.0
        width = SPLASH_W - left - 16
        painter.drawText(
            QRectF(left, 26, width, 28), Qt.AlignmentFlag.AlignVCenter, PROCESS_DISPLAY_NAME
        )
        body = QFont()
        body.setPixelSize(14)
        painter.setFont(body)
        painter.setPen(_SUB)
        painter.drawText(
            QRectF(left, 56, width, 24), Qt.AlignmentFlag.AlignVCenter, tr(WAIT_TEXT)
        )
        if self._step:
            small = QFont()
            small.setPixelSize(12)
            painter.setFont(small)
            painter.drawText(
                QRectF(16, SPLASH_H - 34, SPLASH_W - 32, 22),
                Qt.AlignmentFlag.AlignCenter,
                self._step,
            )
        painter.end()
