"""OBS 取り込み用の配信用ウィンドウ。デバッグ文字は出さない。

キャンバスは OpenGL ウィジェット。立体スタイルは GL で心臓を描き、
その前後に QPainter で背景・前景・文字を重ねる。GL が使えなければ 2D で描く。
"""

from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent, QPainter, QShowEvent, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMainWindow

from stream_heartbeat import OUTPUT_WINDOW_TITLE
from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.paths import cache_dir
from stream_heartbeat.render.echo_gl import EchoRenderer, EchoRendererError
from stream_heartbeat.render.gl_platform import core_profile
from stream_heartbeat.render.grip_pose import HEART_BODY, GripBody, HandPose, grip_pose, held_grip
from stream_heartbeat.render.hand_gl import HandRenderer, HandRendererError
from stream_heartbeat.render.heart_gl import BASE_SCALE, HeartRenderer, HeartRendererError
from stream_heartbeat.render.heart_shaders import STYLE_LOOKS, Look, realistic_look
from stream_heartbeat.render.mesh_cache import shared_heart_mesh
from stream_heartbeat.render.model_body import follow_scale, grip_for_look
from stream_heartbeat.render.mri_gl import MriRenderer
from stream_heartbeat.render.orbit import Orbit
from stream_heartbeat.render.xray_gl import XRAY_FEMALE, XrayRenderer
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon
from stream_heartbeat.ui.effect_burst import paint_beat_pops, paint_heart_pops
from stream_heartbeat.ui.effect_grip import grip_image, hand_image, paint_grip_hand
from stream_heartbeat.ui.effect_monitor import (
    monitor_screen,
    paint_monitor_back,
    paint_monitor_front,
)
from stream_heartbeat.ui.effect_stetho import paint_stethoscope
from stream_heartbeat.ui.effects import (
    EFFECT_BURST,
    EFFECT_DOPPLER,
    EFFECT_GRIP,
    EFFECT_MONITOR,
    EFFECT_STETHO,
    EFFECT_TAGGING,
    STETHO_EFFECTS,
    EffectMotion,
    HeartFrame,
    active_effect,
    beat_pops,
    flat_heart_frame,
    gl_heart_frame,
    grip_squash,
    heart_offset,
)
from stream_heartbeat.ui.heart_echo import (
    echo_zoom,
    paint_doppler_scale,
    paint_echo_marks,
    sector_geometry,
)
from stream_heartbeat.ui.heart_imaging import PANEL_RADIUS_RATIO, panel_rect
from stream_heartbeat.ui.heart_paint import (
    GL_STYLES,
    ROTATABLE_STYLES,
    backdrop_color,
    heart_lift,
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
    return core_profile(fmt)


class OutputCanvas(QOpenGLWidget):
    def __init__(self, session: HeartSession) -> None:
        super().__init__()
        self.setFormat(gl_surface_format())
        self._session = session
        self._now = 0.0
        self._renderer: HeartRenderer | None = None
        self._echo: EchoRenderer | None = None
        self._mri: MriRenderer | None = None
        self._xray: XrayRenderer | None = None
        # 心臓わしづかみの手。初めて掴んだときに作る（作れなければ 2D の手で描く）
        self._hand: HandRenderer | None = None
        self._hand_failed = False
        self._gl_error: str | None = None
        self._orbit = Orbit(session.profile.heart_yaw_deg, session.profile.heart_pitch_deg)
        self._drag_from: QPointF | None = None
        # 角度の固定は保存しない。起動のたびにオフ
        self.angle_locked = False
        # 演出（握る強さ・聴診器の位置）。聴診器はドラッグで回したときは置き直さない
        self._motion = EffectMotion()
        self._press_at: QPointF | None = None
        self._dragged = False
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
        profile = self._session.profile
        self._motion.step(time.perf_counter(), (profile.stetho_x, profile.stetho_y))
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
            profile = self._session.profile
            return realistic_look(profile.realistic_look, profile.heart_material)
        return STYLE_LOOKS[style]

    @property
    def effect(self) -> str:
        """今描いている演出（スタイルが対応しなければ無し）。"""
        profile = self._session.profile
        return active_effect(profile.style, profile.effect)

    def _heart_frame(self, rect: QRectF) -> HeartFrame:
        profile = self._session.profile
        if self.uses_gl:
            return gl_heart_frame(rect, profile.scale, self._look(), heart_lift(profile.style))
        return flat_heart_frame(rect, profile.style, profile.scale, profile.realistic_look)

    def stetho_offset(self) -> tuple[float, float]:
        """置いてある聴診器の、心臓の真ん中からのずれ（心臓の半径を 1 とする）。

        VTube Studio のアイテムの絵で、同じ所に聴診器を当てるのに使う。
        """
        profile = self._session.profile
        rect = QRectF(self.rect())
        point = QPointF(
            rect.left() + profile.stetho_x * rect.width(),
            rect.top() + profile.stetho_y * rect.height(),
        )
        return heart_offset(self._heart_frame(rect), point)

    def _relative(self, pos: QPointF) -> tuple[float, float]:
        w = max(1.0, float(self.width()))
        h = max(1.0, float(self.height()))
        return max(0.0, min(1.0, pos.x() / w)), max(0.0, min(1.0, pos.y() / h))

    # ---------------------------------------------------------------- GL

    def initializeGL(self) -> None:
        # 手は初めて掴んだときに今のコンテキストで作り直す
        self._hand = None
        self._hand_failed = False
        try:
            # 形は起動時に読み込み済み（2 回目からは保存した形を読むだけで済む）
            mesh = shared_heart_mesh(cache_dir())
            self._renderer = HeartRenderer(self.context().functions(), mesh)
            self._gl_error = None
        except (HeartRendererError, RuntimeError, AttributeError) as exc:
            self._renderer = None
            self._gl_error = str(exc) or "OpenGL を初期化できません"
        # 断面のスタイルは使えなければ図形で描く代替に戻るだけなので、失敗は知らせない
        try:
            self._echo = EchoRenderer(self.context().functions())
            self._mri = MriRenderer(self.context().functions())
            self._xray = XrayRenderer(self.context().functions())
        except (EchoRendererError, RuntimeError, AttributeError):
            self._echo = None
            self._mri = None
            self._xray = None

    def _panel_px(self, rect: QRectF) -> tuple[tuple[float, float, float, float], float]:
        """レントゲン・MRI のパネルの位置と角の丸み（GL の画素）。"""
        ratio = self.devicePixelRatioF()
        panel = panel_rect(rect)
        corner = min(panel.width(), panel.height()) * PANEL_RADIUS_RATIO
        box = (panel.x() * ratio, panel.y() * ratio, panel.width() * ratio, panel.height() * ratio)
        return box, corner * ratio

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
        effect = self.effect
        grip = self._motion.grip if effect == EFFECT_GRIP else 0.0
        # Blender の心臓は形そのものが拍で動くので、手の胴と握り直しをその形と縮みに合わせる
        body, grip_cycle = self._grip_body(cycle) if effect == EFFECT_GRIP else (HEART_BODY, cycle)
        # 掴んでいる間は、鼓動に合わせて握り直す強さで心臓が潰れる
        squash_x, squash_y = grip_squash(
            held_grip(grip, grip_cycle) if effect == EFFECT_GRIP else 0.0
        )
        # 立体の心臓を掴むときは、手と心臓が同じ形を使う（指の所が凹む）
        gl_hand = effect == EFFECT_GRIP and self.uses_gl and not self._hand_failed
        pose = self._grip_pose(grip_cycle, grip, body) if gl_hand else None

        gl_mri = style == "mri" and self._mri is not None
        # レントゲン1・2 の胸は、立体心臓と同じく GL で描ける時だけシェーダーで描く
        gl_chest = style == "xray" and self._xray is not None and self.uses_gl
        if not (gl_mri or gl_chest):
            paint_backdrop(painter, rect, style=style, scale=profile.scale, opacity=profile.opacity)
        # 心電図をモニター画面に映すときは、波形を画面の中に収める
        heart_rect = rect
        if effect == EFFECT_MONITOR:
            painter.save()
            painter.setOpacity(max(0.08, min(1.0, profile.opacity)))
            paint_monitor_back(painter, rect)
            painter.restore()
            heart_rect = monitor_screen(rect)
        if style == "echo" and self._echo is not None:
            painter.beginNativePainting()
            ratio = self.devicePixelRatioF()
            apex, radius, half = sector_geometry(rect, profile.scale)
            self._echo.draw(
                width=int(self.width() * ratio),
                height=int(self.height() * ratio),
                apex=(apex.x() * ratio, apex.y() * ratio),
                radius=radius * ratio,
                half_angle=half,
                zoom=echo_zoom(profile.scale),
                cycle=cycle,
                time_s=t,
                opacity=profile.opacity,
                interval=clock.interval(),
                doppler=effect == EFFECT_DOPPLER,
            )
            painter.endNativePainting()
            painter.save()
            painter.setOpacity(max(0.08, min(1.0, profile.opacity)))
            paint_echo_marks(painter, rect, profile.scale)
            if effect == EFFECT_DOPPLER:
                paint_doppler_scale(painter, rect, profile.scale)
            painter.restore()
        elif gl_mri and self._mri is not None:
            painter.beginNativePainting()
            ratio = self.devicePixelRatioF()
            box, corner = self._panel_px(rect)
            self._mri.draw(
                width=int(self.width() * ratio),
                height=int(self.height() * ratio),
                panel=box,
                corner=corner,
                zoom=profile.scale / 0.7,
                cycle=cycle,
                time_s=t,
                opacity=profile.opacity,
                interval=clock.interval(),
                tagging=effect == EFFECT_TAGGING,
            )
            painter.endNativePainting()
        elif self.uses_gl and self._renderer is not None:
            painter.beginNativePainting()
            ratio = self.devicePixelRatioF()
            if gl_chest and self._xray is not None:
                box, corner = self._panel_px(rect)
                self._xray.draw(
                    width=int(self.width() * ratio),
                    height=int(self.height() * ratio),
                    panel=box,
                    corner=corner,
                    time_s=t,
                    opacity=profile.opacity,
                    female=profile.realistic_look == XRAY_FEMALE,
                )
            # 回せないスタイルは体の絵と同じ正面から見る。手で掴んでいる間も正面（手の絵に合わせる）
            rotatable = style in ROTATABLE_STYLES and effect != EFFECT_GRIP
            self._renderer.draw(
                width=int(self.width() * ratio),
                height=int(self.height() * ratio),
                cycle=cycle,
                look=self._look(),
                yaw_deg=self._orbit.yaw if rotatable else 0.0,
                pitch_deg=self._orbit.pitch if rotatable else 0.0,
                scale=profile.scale,
                opacity=profile.opacity,
                time_s=t,
                squash_x=squash_x,
                squash_y=squash_y,
                lift=heart_lift(style),
                hand=pose,
            )
            painter.endNativePainting()
        else:
            painter.save()
            if grip > 0.0:
                middle = self._heart_frame(rect).center
                painter.translate(middle)
                painter.scale(squash_x, squash_y)
                painter.translate(-middle)
            painter.translate(0.0, -heart_lift(style) * rect.height())
            paint_heart(
                painter,
                heart_rect,
                style=style,
                scale=profile.scale,
                opacity=profile.opacity,
                cycle=cycle,
                clock=clock,
                now=t,
                look=profile.realistic_look,
            )
            painter.restore()
        if not gl_chest:
            # GL で描いた胸は骨まで描き込み済み（重ねると肋骨が二重になる）
            paint_overlay(painter, rect, style=style, opacity=profile.opacity, cycle=cycle)
        if effect == EFFECT_MONITOR:
            flash = max(0.0, 1.0 - (t - clock.origin_before(t)) / 0.3)
            painter.save()
            painter.setOpacity(max(0.08, min(1.0, profile.opacity)))
            paint_monitor_front(painter, rect, flash)
            painter.restore()
        self._paint_effect(painter, rect, effect, cycle, grip, pose)
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

    def _model_shown(self) -> bool:
        """Blender の心臓を描いている（形のファイルが読めずに作った心臓で描いているときは偽）。"""
        renderer = self._renderer
        return (
            self.uses_gl
            and self._look().program == "model"
            and renderer is not None
            and renderer.model_error is None
        )

    def _grip_body(self, cycle: CardiacCycle) -> tuple[GripBody, CardiacCycle]:
        if not self._model_shown():
            return HEART_BODY, cycle
        return grip_for_look(self._look(), cycle)

    def _grip_pose(self, cycle: CardiacCycle, grip: float, body: GripBody) -> HandPose:
        profile = self._session.profile
        look = self._look()
        return grip_pose(
            shift=(look.shift_x, look.shift_y),
            size=BASE_SCALE * max(0.05, profile.scale) * look.size_factor,
            cycle=cycle,
            grip=grip,
            time_s=self._now,
            body=body,
        )

    def _paint_gl_hand(self, painter: QPainter, pose: HandPose) -> bool:
        """立体の心臓を掴む手を GL で描く。描けなければ False（2D の手で描く）。"""
        if self._hand_failed:
            return False
        profile = self._session.profile
        look = self._look()
        painter.beginNativePainting()
        try:
            if self._hand is None:
                self._hand = HandRenderer(self.context().functions(), hand_image(), grip_image())
            ratio = self.devicePixelRatioF()
            self._hand.draw(
                width=int(self.width() * ratio),
                height=int(self.height() * ratio),
                pose=pose,
                lift=heart_lift(profile.style),
                opacity=profile.opacity,
                see_through=look.additive or look.cutout,
            )
        except (HandRendererError, RuntimeError, AttributeError):
            self._hand = None
            self._hand_failed = True
        finally:
            painter.endNativePainting()
        return not self._hand_failed

    def _paint_effect(
        self,
        painter: QPainter,
        rect: QRectF,
        effect: str,
        cycle: CardiacCycle,
        grip: float,
        pose: HandPose | None = None,
    ) -> None:
        profile = self._session.profile
        if effect == EFFECT_GRIP:
            if pose is not None and self._paint_gl_hand(painter, pose):
                return
            frame = self._heart_frame(rect)
            paint_grip_hand(
                painter, rect, frame, cycle, grip=grip, time_s=self._now, opacity=profile.opacity
            )
        elif effect == EFFECT_BURST:
            frame = self._heart_frame(rect)
            painter.save()
            painter.setOpacity(max(0.08, min(1.0, profile.opacity)))
            paint_beat_pops(
                painter, frame.center, frame.radius, beat_pops(self._session.clock, self._now)
            )
            painter.restore()
            paint_heart_pops(painter, rect, self._motion.pops_at(time.perf_counter()))
        elif effect in STETHO_EFFECTS:
            rel = self._motion.stetho or (profile.stetho_x, profile.stetho_y)
            pos = QPointF(rect.left() + rel[0] * rect.width(), rect.top() + rel[1] * rect.height())
            frame = self._heart_frame(rect)
            if self._model_shown():
                # Blender の心臓は形が縮むので、当てた所も表面と一緒に真ん中へ寄る
                away = pos - frame.center
                pos = frame.center + away * follow_scale(cycle, away.x(), -away.y())
            paint_stethoscope(
                painter,
                rect,
                pos,
                frame,
                cycle,
                time_s=self._now,
                opacity=profile.opacity,
                back_view=effect == EFFECT_STETHO,
            )

    # ---------------------------------------------------------------- 回転・演出の操作

    def _can_rotate(self) -> bool:
        return (
            self.uses_gl
            and self._session.profile.style in ROTATABLE_STYLES
            and not self.angle_locked
            and self.effect != EFFECT_GRIP
        )

    def _idle_cursor(self) -> Qt.CursorShape:
        effect = self.effect
        if effect in STETHO_EFFECTS:
            # マウスの所に聴診器を描くので、矢印は隠す
            return Qt.CursorShape.BlankCursor
        if self._can_rotate():
            return Qt.CursorShape.OpenHandCursor
        if effect in (EFFECT_GRIP, EFFECT_BURST):
            return Qt.CursorShape.PointingHandCursor
        return Qt.CursorShape.ArrowCursor

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            effect = self.effect
            if effect == EFFECT_GRIP:
                self._motion.press(time.perf_counter())
                return
            self._press_at = event.position()
            self._dragged = False
            if self._can_rotate():
                self._drag_from = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            if effect in STETHO_EFFECTS or effect == EFFECT_BURST:
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_at is not None:
            moved = event.position() - self._press_at
            if abs(moved.x()) + abs(moved.y()) > 4.0:
                self._dragged = True
        if self._drag_from is not None and self._can_rotate():
            delta = event.position() - self._drag_from
            self._drag_from = event.position()
            self._orbit.drag(delta.x(), delta.y())
            self._store_orbit()
            self.update()
            return
        if self.effect in STETHO_EFFECTS:
            self._motion.hover(self._relative(event.position()))
        self.setCursor(self._idle_cursor())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._motion.release()
        pressed_at = self._press_at
        self._press_at = None
        if (
            event.button() == Qt.MouseButton.LeftButton
            and pressed_at is not None
            and not self._dragged
            and self.effect in STETHO_EFFECTS
        ):
            # クリックした所に聴診器を置く（マウスが窓の外へ出るとここへ戻る）
            profile = self._session.profile
            profile.stetho_x, profile.stetho_y = self._relative(event.position())
            self._motion.hover(self._relative(event.position()))
        if (
            event.button() == Qt.MouseButton.LeftButton
            and pressed_at is not None
            and not self._dragged
            and self.effect == EFFECT_BURST
        ):
            # 回すためのドラッグでなければ、放した所からハートをはじけさせる
            self._motion.pop(time.perf_counter(), self._relative(event.position()))
        if self._drag_from is not None:
            self._drag_from = None
            self.setCursor(self._idle_cursor())
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._motion.hover(None)
        self._motion.release()
        super().leaveEvent(event)

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
        self.setStyleSheet(DARK_QSS)
        apply_app_icon(self)
        self.canvas = OutputCanvas(session)
        self.canvas.setObjectName("outputCanvas")
        self.setCentralWidget(self.canvas)
        self._allow_close = False
        self._quit_via: Callable[[], None] | None = None
        self._created_translucent: bool | None = None
        self.apply_backdrop()

    def apply_backdrop(self) -> None:
        transparent = self.canvas._session.profile.backdrop == "transparent"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, transparent)
        self.canvas.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, transparent)
        self.canvas.update()

    def needs_rebuild(self) -> bool:
        """透過は窓を作るときにしか効かない。緑などで作った窓を透明にするには作り直す。"""
        if self._created_translucent is None:
            # まだ一度も出していない窓は、そのまま透過にできる
            return False
        transparent = self.canvas._session.profile.backdrop == "transparent"
        return transparent and not self._created_translucent

    def showEvent(self, event: QShowEvent) -> None:
        if self._created_translucent is None:
            self._created_translucent = self.testAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground
            )
        super().showEvent(event)

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
