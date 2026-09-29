from __future__ import annotations

import math

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QOffscreenSurface, QOpenGLContext
from PySide6.QtOpenGL import QOpenGLFramebufferObject
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.render.echo_gl import EchoRenderer, valve_open
from stream_heartbeat.ui.heart_echo import echo_zoom, sector_geometry


def _clock() -> tuple[BeatClock, float]:
    clock = BeatClock()
    for i in range(8):
        clock.feed_beat(i * 60 / 72)
    return clock, 7 * 60 / 72


@pytest.mark.parametrize("size", [(720, 720), (1280, 720), (480, 900)])
@pytest.mark.parametrize("scale", [0.2, 0.7, 1.2])
def test_sector_fits_inside_window(size: tuple[int, int], scale: float) -> None:
    rect = QRectF(0, 0, *size)
    apex, radius, half = sector_geometry(rect, scale)
    assert rect.contains(apex)
    for sign in (-1.0, 1.0):
        x = apex.x() + sign * radius * math.sin(half)
        y = apex.y() + radius * math.cos(half)
        assert rect.left() <= x <= rect.right()
        assert y <= rect.bottom()
    assert apex.y() + radius <= rect.bottom()


def test_small_scale_shrinks_fan_and_large_scale_zooms_inside() -> None:
    rect = QRectF(0, 0, 720, 720)
    _apex, small, _half = sector_geometry(rect, 0.35)
    _apex, normal, _half = sector_geometry(rect, 0.7)
    _apex, large, _half = sector_geometry(rect, 1.2)
    assert small < normal == large
    assert echo_zoom(0.35) == echo_zoom(0.7) == 1.0
    assert echo_zoom(1.2) > 1.0


def test_valves_close_at_beat_and_open_in_diastole() -> None:
    clock, last = _clock()
    assert valve_open(clock.cycle(last)) == 0.0
    assert valve_open(clock.cycle(last + 0.06)) == 0.0
    early = valve_open(clock.cycle(last + 0.36))
    late = valve_open(clock.cycle(last + 0.7))
    assert early > late > 0.3


def test_shader_draws_sector_and_leaves_outside(qapp: QApplication) -> None:
    del qapp
    ctx = QOpenGLContext()
    surface = QOffscreenSurface()
    surface.create()
    if not ctx.create() or not ctx.makeCurrent(surface):
        pytest.skip("OpenGL なし")
    echo = EchoRenderer(ctx.functions())
    clock, last = _clock()
    fbo = QOpenGLFramebufferObject(200, 200)
    fbo.bind()
    gl = ctx.functions()
    gl.glViewport(0, 0, 200, 200)
    gl.glClearColor(0.0, 1.0, 0.0, 1.0)
    gl.glClear(0x4000)
    apex, radius, half = sector_geometry(QRectF(0, 0, 200, 200))
    echo.draw(
        width=200,
        height=200,
        apex=(apex.x(), apex.y()),
        radius=radius,
        half_angle=half,
        zoom=1.0,
        cycle=clock.cycle(last + 0.3),
        time_s=last + 0.3,
        opacity=1.0,
    )
    image = fbo.toImage()
    fbo.release()
    assert image.pixelColor(3, 3) == QColor(0, 255, 0)
    inside = image.pixelColor(100, int(apex.y() + radius * 0.8))
    assert inside.green() < 200
    assert abs(inside.red() - inside.green()) < 30
