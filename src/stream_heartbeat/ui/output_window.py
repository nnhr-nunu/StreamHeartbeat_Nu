"""OBS 取り込み用の配信用ウィンドウ。デバッグ文字は出さない。

キャンバスは OpenGL ウィジェット。立体スタイルは GL で心臓を描き、
その前後に QPainter で背景・前景・文字を重ねる。GL が使えなければ 2D で描く。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QPainter, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMainWindow

from stream_heartbeat import OUTPUT_WINDOW_TITLE
from stream_heartbeat.render.heart_gl import HeartRenderer, HeartRendererError
from stream_heartbeat.render.heart_shaders import STYLE_LOOKS, Look, realistic_look
from stream_heartbeat.render.orbit import Orbit
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon
from stream_heartbeat.ui.heart_paint import (
    GL_STYLES,
    backdrop_color,
    paint_backdrop,
    paint_bpm,
    paint_bursts,
    paint_heart,
    paint_overlay,
    paint_ripples,
)
from stream_heartbeat.ui.styles import DARK_QSS
from stream_heartbeat.ui.win_present import redraw_hwnd


def gl_surface_format() -> QSurfaceFormat:
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(4)
    fmt.setSwapInterval(1)
    fmt.setAlphaBufferSize(8)
    return fmt


class OutputCanvas(QOpenGLWidget):
    def __init__(self, session: HeartSession) -> None:
        super().__init__()
        self.setFormat(gl_surface_format())
        self._session = session
        self._now = 0.0
        self._renderer: HeartRenderer | None = None
        self._gl_error: str | None = None
        self._orbit = Orbit(session.profile.heart_yaw_deg, session.profile.heart_pitch_deg)
        self._drag_from: QPointF | None = None
        # 角度の固定は保存しない。起動のたびにオフ
        self.angle_locked = False
        self.setMouseTracking(True)

    # ---------------------------------------------------------------- 状態

    @property
    def gl_error(self) -> str | None:
        return self._gl_error

    @property
    def uses_gl(self) -> bool:
        return self._renderer is not None and self._session.profile.style in GL_STYLES

    def set_now(self, t: float) -> None:
        self._now = t
        self.update()
        host = self.window()
        if host is not None:
            redraw_hwnd(int(host.winId()))

    def sync_orbit_from_profile(self) -> None:
        profile = self._session.profile
        self._orbit.yaw = profile.heart_yaw_deg
        self._orbit.pitch = profile.heart_pitch_deg

    def reset_angle(self) -> None:
        self._orbit.reset()
        self._store_orbit()
        self.update()

    def _store_orbit(self) -> None:
        profile = self._session.profile
        profile.heart_yaw_deg = self._orbit.yaw
        profile.heart_pitch_deg = self._orbit.pitch

    def _look(self) -> Look:
        style = self._session.profile.style
        if style == "realistic":
            return realistic_look(self._session.profile.realistic_look)
        return STYLE_LOOKS[style]

    # ---------------------------------------------------------------- GL

    def initializeGL(self) -> None:
        try:
            self._renderer = HeartRenderer(self.context().functions())
            self._gl_error = None
        except (HeartRendererError, RuntimeError, AttributeError) as exc:
            self._renderer = None
            self._gl_error = str(exc) or "OpenGL を初期化できません"

    def paintGL(self) -> None:
        painter = QPainter(self)
        rect = QRectF(self.rect())
        profile = self._session.profile
        bg = backdrop_color(profile.backdrop)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(rect, bg)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        clock = self._session.clock
        t = self._now
        cycle = clock.cycle(t)
        style = profile.style

        paint_backdrop(painter, rect, style=style, scale=profile.scale, opacity=profile.opacity)
        if self.uses_gl and self._renderer is not None:
            painter.beginNativePainting()
            ratio = self.devicePixelRatioF()
            self._renderer.draw(
                width=int(self.width() * ratio),
                height=int(self.height() * ratio),
                cycle=cycle,
                look=self._look(),
                yaw_deg=self._orbit.yaw,
                pitch_deg=self._orbit.pitch,
                scale=profile.scale,
                opacity=profile.opacity,
                time_s=t,
            )
            painter.endNativePainting()
        else:
            paint_heart(
                painter,
                rect,
                style=style,
                scale=profile.scale,
                opacity=profile.opacity,
                cycle=cycle,
                clock=clock,
                now=t,
            )
        paint_overlay(painter, rect, style=style, opacity=profile.opacity, cycle=cycle)
        paint_bursts(
            painter,
            rect,
            self._session.overlay.bursts_at(t),
            scale=profile.beat_text_scale,
            opacity=profile.beat_text_opacity,
            color=profile.beat_text_color,
            outline=profile.beat_text_outline,
        )
        paint_ripples(painter, rect, self._session.overlay.ripples_at(t))
        if profile.show_bpm:
            paint_bpm(
                painter,
                rect,
                clock.bpm,
                scale=profile.bpm_scale,
                pos=(profile.bpm_x, profile.bpm_y),
                color=profile.bpm_color,
                outline=profile.bpm_outline,
            )
        painter.end()

    # ---------------------------------------------------------------- 回転

    def _can_rotate(self) -> bool:
        return self.uses_gl and not self.angle_locked

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._can_rotate():
            self._drag_from = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_from is not None and self._can_rotate():
            delta = event.position() - self._drag_from
            self._drag_from = event.position()
            self._orbit.drag(delta.x(), delta.y())
            self._store_orbit()
            self.update()
            return
        self.setCursor(
            Qt.CursorShape.OpenHandCursor if self._can_rotate() else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_from is not None:
            self._drag_from = None
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if self._can_rotate() else Qt.CursorShape.ArrowCursor
            )
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._can_rotate():
            self.reset_angle()
            return
        super().mouseDoubleClickEvent(event)


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
        self._quit_via: Callable[[], None] | None = None
        self.apply_backdrop()

    def apply_backdrop(self) -> None:
        transparent = self.canvas._session.profile.backdrop == "transparent"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, transparent)
        self.canvas.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, transparent)
        self.canvas.update()

    def set_quit_handler(self, handler: Callable[[], None]) -> None:
        self._quit_via = handler

    def allow_close(self) -> None:
        self._allow_close = True

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            super().closeEvent(event)
            return
        if self._quit_via is not None:
            event.ignore()
            self._quit_via()
            return
        super().closeEvent(event)
