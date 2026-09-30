"""Mac の OpenGL（4.1 Core）でも立体・断面のシェーダーが通るようにする切り替え。"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QOffscreenSurface, QOpenGLContext, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render import gl_platform
from stream_heartbeat.render.gl_platform import core_profile, glsl
from stream_heartbeat.render.heart_shaders import REALISTIC_LOOKS, STYLE_LOOKS

CORE = QSurfaceFormat.OpenGLContextProfile.CoreProfile


def test_glsl_keeps_version_130_off_mac(monkeypatch) -> None:
    monkeypatch.setattr(gl_platform, "MAC", False)
    source = "\n#version 130\nin vec2 aPos;\n"
    assert glsl(source) == source


def test_glsl_declares_version_150_on_mac(monkeypatch) -> None:
    monkeypatch.setattr(gl_platform, "MAC", True)
    assert glsl("\n#version 130\nin vec2 aPos;\n") == "\n#version 150\nin vec2 aPos;\n"


def test_mac_asks_for_gl41_core(monkeypatch) -> None:
    monkeypatch.setattr(gl_platform, "MAC", True)
    fmt = core_profile(QSurfaceFormat())
    assert (fmt.majorVersion(), fmt.minorVersion()) == (4, 1)
    assert fmt.profile() == CORE


def test_other_platforms_keep_the_default_context(monkeypatch) -> None:
    monkeypatch.setattr(gl_platform, "MAC", False)
    fmt = core_profile(QSurfaceFormat())
    assert (fmt.majorVersion(), fmt.minorVersion()) == (2, 0)
    assert fmt.profile() == QSurfaceFormat.OpenGLContextProfile.NoProfile


def test_mac_shaders_compile_and_draw_in_core_profile(qapp: QApplication, monkeypatch) -> None:
    """Mac と同じ 4.1 Core・GLSL 150 で全シェーダーが通り、心臓が描ける（GPU がある PC だけ）。"""
    del qapp
    monkeypatch.setattr(gl_platform, "MAC", True)
    fmt = core_profile(QSurfaceFormat())
    ctx = QOpenGLContext()
    ctx.setFormat(fmt)
    surface = QOffscreenSurface()
    surface.setFormat(fmt)
    surface.create()
    if not ctx.create() or not ctx.makeCurrent(surface):
        pytest.skip("OpenGL なし")
    got = ctx.format()
    if got.profile() != CORE or (got.majorVersion(), got.minorVersion()) < (3, 2):
        pytest.skip("Core プロファイルの OpenGL なし")
    from stream_heartbeat.render.echo_gl import EchoRenderer
    from stream_heartbeat.render.heart_gl import OffscreenHeart
    from stream_heartbeat.render.mri_gl import MriRenderer
    from stream_heartbeat.render.xray_gl import XrayRenderer

    EchoRenderer(ctx.functions())
    MriRenderer(ctx.functions())
    XrayRenderer(ctx.functions())
    ctx.doneCurrent()

    # 窓なしの描画も Mac のアプリと同じく既定の形式（4.1 Core）で作られる
    before = QSurfaceFormat.defaultFormat()
    QSurfaceFormat.setDefaultFormat(fmt)
    try:
        heart = OffscreenHeart()
        rest = CardiacCycle(0.0, 0.0, 0.2, 1.0, 1.0, 0.0, 0.5)
        for look in (*REALISTIC_LOOKS, STYLE_LOOKS["mech"], STYLE_LOOKS["xray_heart"]):
            image = heart.render(width=160, height=160, cycle=rest, look=look, scale=0.7)
            assert image.pixelColor(3, 3) == QColor(0, 255, 0), look.key
            assert image.pixelColor(80, 88) != QColor(0, 255, 0), look.key
    finally:
        QSurfaceFormat.setDefaultFormat(before)
