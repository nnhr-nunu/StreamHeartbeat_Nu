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


def test_realistic_has_three_looks_and_style_looks() -> None:
    assert [look.key for look in REALISTIC_LOOKS] == ["surgical", "vivid", "anatomy"]
    assert realistic_look("nope").key == "surgical"
    assert set(STYLE_LOOKS) == {"mech", "poly", "xray", "xray_heart"}
    assert STYLE_LOOKS["xray"].additive
    # 心臓だけのレントゲンは背景に重ねるので、足し算ではなく下を隠して描く
    assert STYLE_LOOKS["xray_heart"].cutout and not STYLE_LOOKS["xray_heart"].additive
    # 生々しい見た目（リアル2）だけ、心房の時間差・心耳・冠動脈の盛り上がりを使う
    assert [look.key for look in REALISTIC_LOOKS if look.lively > 0] == ["vivid"]
    assert "uLively" in fragment_source("flesh") and "uCutout" in fragment_source("scan")
    for program in ("flesh", "mech", "scan", "poly"):
        assert "#version 130" in fragment_source(program)


def test_anatomy_look_has_less_fat_and_clearer_coronary() -> None:
    surgical = realistic_look("surgical")
    anatomy = realistic_look("anatomy")
    assert anatomy.fat_amount < surgical.fat_amount
    assert anatomy.coronary > surgical.coronary
    assert "uCoronary" in fragment_source("flesh")


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
    for look in (
        *REALISTIC_LOOKS,
        STYLE_LOOKS["mech"],
        STYLE_LOOKS["xray_heart"],
        STYLE_LOOKS["poly"],
    ):
        image = heart.render(width=160, height=160, cycle=rest, look=look, scale=0.7)
        center = image.pixelColor(80, 88)
        corner = image.pixelColor(3, 3)
        assert corner == QColor(0, 255, 0), look.key
        assert center != QColor(0, 255, 0), look.key
        assert not (center.green() > 200 and center.red() < 60), look.key


def test_section_cavities_leave_wall_inside_outline() -> None:
    from stream_heartbeat.render.heart_section import CAVITIES, inside_depth, plane_point

    for name, ((cx, cy), (rx, ry), tilt, taper) in CAVITIES.items():
        a = math.radians(tilt)
        for k in range(48):
            th = 2.0 * math.pi * k / 48
            qy = ry * math.sin(th)
            qx = rx * (1.0 + taper * math.sin(th)) * math.cos(th)
            s = cx + math.cos(a) * qx - math.sin(a) * qy
            t = cy + math.sin(a) * qx + math.cos(a) * qy
            depth, _region = inside_depth(plane_point(s, t))
            assert depth > 0.03, (name, round(s, 2), round(t, 2), round(depth, 3))


def test_neck_branches_rise_from_arch() -> None:
    from stream_heartbeat.render.heart_mesh import BODY_UP, dot, great_vessels

    vessels = great_vessels()
    aorta = vessels[0]
    arch_height = max(dot(p, BODY_UP) for p in aorta.points)
    branches = vessels[1:4]
    for branch in branches:
        assert not branch.cut
        assert dot(branch.points[-1], BODY_UP) > arch_height + 0.3
    # 大動脈は弓のあと背中側を心臓より下まで降りる
    assert dot(aorta.points[-1], BODY_UP) < dot(aorta.points[0], BODY_UP)


def test_section_cap_is_tail_of_mesh_and_only_anatomy_uses_it() -> None:
    mesh = build_heart_mesh(rows=24, cols=36, section_step=0.08)
    stride = FLOATS_PER_VERTEX
    assert 0 < mesh.section_start < mesh.vertex_count
    assert mesh.body_vertex_count == mesh.section_start
    assert mesh.section_start < mesh.auricle_start == mesh.section_end < mesh.vertex_count
    for v in range(0, mesh.vertex_count, 97):
        cap = mesh.data[v * stride + 11]
        assert cap == (1.0 if mesh.section_start <= v < mesh.section_end else 0.0)
    assert realistic_look("anatomy").section
    assert not realistic_look("surgical").section
    assert not any(look.section for look in STYLE_LOOKS.values())


def test_vessel_tips_fade_out_and_roots_blend_into_body() -> None:
    mesh = build_heart_mesh(rows=24, cols=36, section_step=0.08)
    stride = FLOATS_PER_VERTEX
    body = range(0, mesh.tube_start)
    tubes = range(mesh.tube_start, mesh.section_start)
    joint = [mesh.data[v * stride + 13] for v in range(mesh.vertex_count)]
    fade = [mesh.data[v * stride + 14] for v in range(mesh.vertex_count)]
    # 本体と断面は透けない。血管の開いた先は透明まで消える
    assert all(fade[v] == 1.0 for v in body)
    assert all(fade[v] == 1.0 for v in range(mesh.section_start, mesh.vertex_count))
    assert min(fade[v] for v in tubes) == pytest.approx(0.0, abs=1e-6)
    # 付け根の近くだけ本体側もなじませる
    assert max(joint[v] for v in body) > 0.8
    apex = [v for v in body if mesh.data[v * stride + 8] > 0.6]
    assert apex and max(joint[v] for v in apex) < 0.05
    assert max(joint[v] for v in tubes) == pytest.approx(1.0)


def test_auricle_parts_are_tail_and_marked_from_root_to_tip() -> None:
    mesh = build_heart_mesh(rows=24, cols=36, section_step=0.08)
    stride = FLOATS_PER_VERTEX
    auricle = [mesh.data[v * stride + 15] for v in range(mesh.vertex_count)]
    # 心耳らしさは心耳のパーツだけ。根元（房に埋まる）0 から先 1
    assert all(auricle[v] == 0.0 for v in range(mesh.auricle_start))
    assert all(auricle[v] == 0.0 for v in range(mesh.coronary_start, mesh.vertex_count))
    parts = [auricle[v] for v in range(mesh.auricle_start, mesh.coronary_start)]
    assert min(parts) == pytest.approx(0.0, abs=1e-6)
    assert max(parts) == pytest.approx(1.0)
    # 左心耳は貼り付けた塊に見えるので載せず、右心耳だけ
    regions = {mesh.data[v * stride + 6] for v in range(mesh.auricle_start, mesh.coronary_start)}
    assert regions == {3.0}


def test_coronary_tubes_ride_on_ventricles_along_grooves() -> None:
    from stream_heartbeat.render.heart_coronary import (
        ARTERY,
        VEIN,
        coronary_parts,
        direction,
        trunks,
    )
    from stream_heartbeat.render.heart_mesh import CHAMBERS, _ray_ellipsoid

    mesh = build_heart_mesh(rows=24, cols=36, section_step=0.08)
    stride = FLOATS_PER_VERTEX
    assert mesh.auricle_start < mesh.coronary_start < mesh.vertex_count
    flags = [mesh.data[v * stride + 16] for v in range(mesh.vertex_count)]
    assert all(flag == 0.0 for flag in flags[: mesh.coronary_start])
    assert set(flags[mesh.coronary_start :]) == {ARTERY, VEIN}
    # 下の心室と一緒に動くよう、部位は左室〜右室（境目は間の値）
    regions = [mesh.data[v * stride + 6] for v in range(mesh.coronary_start, mesh.vertex_count)]
    assert 0.0 <= min(regions) and max(regions) <= 1.0
    assert any(0.1 < r < 0.9 for r in regions)
    # 左前下行枝は左室と右室の境目の溝をたどる（心尖を回る先を除く）
    lv, rv = CHAMBERS[0], CHAMBERS[1]
    for az, el in trunks()["lad"][:-3]:
        d = direction(az, el)
        assert abs(_ray_ellipsoid(d, lv) - _ray_ellipsoid(d, rv)) < 1e-3
    kinds = [part.kind for part in coronary_parts()]
    assert kinds.count(ARTERY) >= 6 and kinds.count(VEIN) >= 2

