from __future__ import annotations

import math

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.heart_mesh import (
    FLOATS_PER_VERTEX,
    REGION_ARTERY,
    REGION_LUMEN,
    REGION_LV,
    REGION_VEIN,
    build_heart_mesh,
)
from stream_heartbeat.render.heart_shaders import (
    REALISTIC_LOOKS,
    STYLE_LOOKS,
    fragment_source,
    realistic_look,
)
from stream_heartbeat.render.orbit import Orbit, clamp_pitch, wrap_yaw


def test_mesh_has_all_regions_and_unit_normals() -> None:
    mesh = build_heart_mesh(rows=24, cols=36)
    assert mesh.vertex_count % 3 == 0
    assert len(mesh.data) == mesh.vertex_count * FLOATS_PER_VERTEX
    regions = set()
    for i in range(0, len(mesh.data), FLOATS_PER_VERTEX):
        nx, ny, nz = mesh.data[i + 3 : i + 6]
        assert abs(math.sqrt(nx * nx + ny * ny + nz * nz) - 1.0) < 1e-3
        regions.add(mesh.data[i + 6])
        assert 0.0 <= mesh.data[i + 8] <= 1.0
    assert {REGION_LV, REGION_ARTERY, REGION_VEIN, REGION_LUMEN} <= regions


def test_mesh_triangles_face_outward() -> None:
    mesh = build_heart_mesh(rows=24, cols=36)
    stride = FLOATS_PER_VERTEX
    flipped = 0
    total = 0
    for start in range(0, len(mesh.data), stride * 3):
        p = [mesh.data[start + k * stride : start + k * stride + 3] for k in range(3)]
        n = [mesh.data[start + k * stride + 3 : start + k * stride + 6] for k in range(3)]
        ux, uy, uz = (p[1][j] - p[0][j] for j in range(3))
        vx, vy, vz = (p[2][j] - p[0][j] for j in range(3))
        fx, fy, fz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        avg = [sum(n[k][j] for k in range(3)) for j in range(3)]
        if fx * avg[0] + fy * avg[1] + fz * avg[2] < 0.0:
            flipped += 1
        total += 1
    assert flipped == 0, f"{flipped}/{total}"


def test_realistic_has_two_looks_and_style_looks() -> None:
    assert [look.key for look in REALISTIC_LOOKS] == ["surgical", "anatomy"]
    assert realistic_look("nope").key == "surgical"
    assert set(STYLE_LOOKS) == {"mech", "xray", "mri"}
    assert STYLE_LOOKS["xray"].additive and STYLE_LOOKS["mri"].additive
    for program in ("flesh", "mech", "scan"):
        assert "#version 130" in fragment_source(program)


def test_orbit_drag_and_limits() -> None:
    orbit = Orbit()
    orbit.drag(100.0, -1000.0)
    assert -89.0 <= orbit.pitch <= 89.0
    assert -180.0 <= orbit.yaw <= 180.0
    assert wrap_yaw(190.0) == -170.0
    assert clamp_pitch(120.0) == 89.0
    orbit.reset()
    assert orbit.yaw == Orbit().yaw


def _gl_available() -> bool:
    from PySide6.QtGui import QOffscreenSurface, QOpenGLContext

    ctx = QOpenGLContext()
    if not ctx.create():
        return False
    surface = QOffscreenSurface()
    surface.create()
    return ctx.makeCurrent(surface)


def test_offscreen_render_puts_heart_over_chroma(qapp: QApplication) -> None:
    del qapp
    if not _gl_available():
        pytest.skip("OpenGL なし")
    from stream_heartbeat.render.heart_gl import OffscreenHeart

    heart = OffscreenHeart()
    rest = CardiacCycle(0.0, 0.0, 0.2, 1.0, 1.0, 0.0, 0.5)
    for look in (*REALISTIC_LOOKS, STYLE_LOOKS["mech"]):
        image = heart.render(width=160, height=160, cycle=rest, look=look, scale=0.7)
        center = image.pixelColor(80, 88)
        corner = image.pixelColor(3, 3)
        assert corner == QColor(0, 255, 0), look.key
        assert center != QColor(0, 255, 0), look.key
        assert not (center.green() > 200 and center.red() < 60), look.key
