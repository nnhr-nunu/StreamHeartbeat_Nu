"""OBS 取り込み用の配信用ウィンドウ。デバッグ文字は出さない。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QMainWindow, QWidget

from stream_heartbeat import OUTPUT_WINDOW_TITLE
from stream_heartbeat.config import CHROMA_HEX
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon
from stream_heartbeat.ui.heart_paint import paint_bpm, paint_bursts, paint_heart
from stream_heartbeat.ui.styles import DARK_QSS

CHROMA = QColor(CHROMA_HEX)


class OutputCanvas(QWidget):
    def __init__(self, session: HeartSession) -> None:
        super().__init__()
        self._session = session
        self._now = 0.0

    def set_now(self, t: float) -> None:
        self._now = t
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), CHROMA)
        profile = self._session.profile
        clock = self._session.clock
        t = self._now
        paint_heart(
            painter,
            self.rect(),
            style=profile.style,
            scale=profile.scale,
            opacity=profile.opacity,
            cycle=clock.cycle(t),
            ecg_phase=(t / max(clock.interval(), 0.2)) % 1.0,
        )
        paint_bursts(painter, self.rect(), self._session.overlay.bursts_at(t))
        if profile.show_bpm:
            paint_bpm(painter, self.rect(), clock.bpm)


class OutputWindow(QMainWindow):
    def __init__(self, session: HeartSession) -> None:
        super().__init__()
        self.setWindowTitle(OUTPUT_WINDOW_TITLE)
        self.setMinimumSize(480, 480)
        self.resize(720, 720)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setStyleSheet(DARK_QSS)
        apply_app_icon(self)
        self.canvas = OutputCanvas(session)
        self.canvas.setObjectName("outputCanvas")
        self.setCentralWidget(self.canvas)
        self._allow_close = False

    def allow_close(self) -> None:
        self._allow_close = True

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._allow_close:
            event.ignore()
            return
        super().closeEvent(event)
