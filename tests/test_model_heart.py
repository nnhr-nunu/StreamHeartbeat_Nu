"""Blender で作った心臓（リアル1）: 形のファイル・拍の動き・材質の選び方。"""

from __future__ import annotations

import math
from array import array
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.grip_pose import HEART_BODY, grip_pose, rim_at
from stream_heartbeat.render.heart_shaders import realistic_look
from stream_heartbeat.render.model_body import (
    MODEL_DEPTH,
    MODEL_HALF,
    MODEL_RIM,
    REST_WEIGHTS,
    follow_scale,
    grip_for_look,
    model_grip,
)
from stream_heartbeat.render.model_gl import MODEL_BODY_CENTER
from stream_heartbeat.render.model_mesh import (
    ENV_PATH,
    GRADIENT_PATH,
    MAGIC,
    ModelMeshError,
    beat_weights,
    load_model_anim,
    load_model_mesh,
)
from stream_heartbeat.render.model_shaders import (
    MATERIALS,
    MODEL_FRAGMENT,
    MODEL_VERTEX,
    TOP_FADE,
    VESSEL_ENDS,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.effects import BODY_HALF, gl_heart_frame
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.style_catalog import MODEL_MATERIALS, has_material


@pytest.fixture(scope="module")
def mesh():  # type: ignore[no-untyped-def]
    return load_model_mesh()


def test_model_file_is_bundled_and_whole(mesh) -> None:  # type: ignore[no-untyped-def]
    assert GRADIENT_PATH.is_file() and ENV_PATH.is_file()
    assert mesh.vertex_count == 55104
    assert mesh.index_count == 106772 * 3
    assert mesh.key_count == 3
    # 16 bit の番号に収まる（GPU へは 16 bit のまま渡す）
    assert mesh.vertex_count < 65536
    blocks = ("pos", "normal", "uv", "delta0", "delta1", "delta2", "cavity", "index")
    assert set(blocks) <= set(mesh.offsets)
    assert mesh.offsets["index"] + mesh.index_count * 2 <= len(mesh.payload)
    assert len(mesh.anim_times) == len(mesh.anim_weights) == 24
    assert all(len(row) == 3 for row in mesh.anim_weights)


def test_broken_model_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ModelMeshError):
        load_model_mesh(tmp_path / "missing.bin")
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"not a heart")
    with pytest.raises(ModelMeshError):
        load_model_mesh(bad)
    cut = tmp_path / "cut.bin"
    cut.write_bytes(MAGIC + b"\x10\x00\x00\x00{}")
    with pytest.raises(ModelMeshError):
        load_model_mesh(cut)


def test_beat_starts_and_ends_at_rest(mesh) -> None:  # type: ignore[no-untyped-def]
    rest = mesh.anim_weights[-1]
    assert beat_weights(mesh, 0.0, 1.0) == pytest.approx(rest)
    assert beat_weights(mesh, 5.0, 1.0) == pytest.approx(rest)
    # 50 BPM なら Blender のアニメのとおりの速さ。0.25 秒でキー 1 がいちばん強い
    peak = beat_weights(mesh, 0.25, 1.2)
    assert peak[0] == pytest.approx(1.0, abs=0.02)


def test_fast_beat_fits_the_interval(mesh) -> None:  # type: ignore[no-untyped-def]
    rest = mesh.anim_weights[-1]
    interval = 0.5
    # 120 BPM では次の拍までに 1 回ぶんを終える
    assert beat_weights(mesh, interval * 0.93, interval) == pytest.approx(rest)
    # 途中の形は同じ順に速く進む（ゆっくりの 0.25 秒が、速い拍ではその半分ほど）
    slow = beat_weights(mesh, 0.25, 1.2)
    fast = beat_weights(mesh, 0.25 * interval * 0.92, interval)
    assert fast == pytest.approx(slow, abs=1e-6)


def test_cycle_carries_interval() -> None:
    clock = BeatClock()
    for i in range(6):
        clock.feed_beat(i * 0.5)
    assert clock.cycle(2.6).interval == pytest.approx(clock.interval())


def test_model_shaders_work_on_windows_and_mac() -> None:
    for source in (MODEL_VERTEX, MODEL_FRAGMENT):
        assert source.lstrip().startswith("#version 130")
    assert "uMaterial" in MODEL_FRAGMENT and "uWeights" in MODEL_VERTEX


def test_material_list_matches_shader() -> None:
    assert [key for key, _label in MODEL_MATERIALS] == list(MATERIALS)
    assert has_material("realistic", "model")
    assert not has_material("realistic", "surgical")
    assert not has_material("cute", "model")


def test_new_profile_starts_with_red_model() -> None:
    profile = HeartProfile()
    assert profile.style == "realistic"
    assert profile.realistic_look == "model"
    assert profile.heart_material == "real"


def test_material_row_follows_style_and_saves(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    monkeypatch.setattr("stream_heartbeat.ui.operator_window.resolve_data_dir", lambda: tmp_path)
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    form = operator._style_form
    operator._select_style("realistic", "model")
    assert form.isRowVisible(operator._material)
    operator._material.setCurrentIndex(operator._material.findData("glass"))
    assert session.profile.heart_material == "glass"
    assert output.canvas._look().material == "glass"
    # 材質を選んでも演出（聴診器など）はそのまま選べる
    assert operator._effect.count() > 1
    operator._select_style("realistic", "surgical")
    assert not form.isRowVisible(operator._material)
    # 別のリアルでは材質を描かないが、選んだ値は残る（リアル1 に戻せばガラス）
    assert output.canvas._look().material == ""
    assert session.profile.heart_material == "glass"
    operator.close()
    output.close()


def _block(mesh, name: str) -> array:  # type: ignore[no-untyped-def]
    raw = array("h")
    start = mesh.offsets[name]
    raw.frombytes(mesh.payload[start : start + mesh.vertex_count * 8])
    return raw


def _body_points(mesh) -> list[tuple[float, float, float]]:  # type: ignore[no-untyped-def]
    """休んだ形（キーの重みが REST_WEIGHTS）の胴の点（胴の真ん中から。上の太い血管は除く）。"""
    pos = _block(mesh, "pos")
    keys = [_block(mesh, f"delta{k}") for k in range(mesh.key_count)]
    scales = [w * d / 32767.0 for w, d in zip(REST_WEIGHTS, mesh.delta_scales)]
    cx, cy, cz = MODEL_BODY_CENTER
    points = []
    for i in range(0, len(pos), 4):
        p = [pos[i + a] * mesh.pos_scale[a] / 32767.0 for a in range(3)]
        for key, scale in zip(keys, scales):
            for a in range(3):
                p[a] += key[i + a] * scale
        if p[1] < 0.4:
            points.append((p[0] - cx, p[1] - cy, p[2] - cz))
    return points


def test_model_body_outline_matches_mesh(mesh) -> None:  # type: ignore[no-untyped-def]
    """手を巻き付ける胴の輪郭と大きさが、Blender の心臓の形と合っている。"""
    points = _body_points(mesh)
    bins = len(MODEL_RIM)
    reach = [0.0] * bins
    for x, y, _z in points:
        k = round((math.atan2(y, x) + math.pi) / (2.0 * math.pi) * bins) % bins
        reach[k] = max(reach[k], math.hypot(x, y))
    # 上の向き（胴の上の切り口）は、形を 16 bit に詰めたずれで少し変わる
    for k, (measured, saved) in enumerate(zip(reach, MODEL_RIM)):
        assert abs(measured - saved) < 0.015, k
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    assert (max(xs) - min(xs)) / 2 == pytest.approx(MODEL_HALF[0], abs=0.01)
    assert (max(ys) - min(ys)) / 2 == pytest.approx(MODEL_HALF[1], abs=0.01)
    # 正面のいちばん手前は、楕円に合わせた奥行きより少し前に出る（丸みの頂き）
    front = max(p[2] for p in points)
    assert MODEL_DEPTH < front < MODEL_DEPTH * 1.3


def test_anim_is_read_without_unpacking_the_shape(mesh) -> None:  # type: ignore[no-untyped-def]
    anim = load_model_anim()
    assert anim is not None
    assert anim.anim_times == mesh.anim_times
    assert anim.anim_weights[-1] == pytest.approx(REST_WEIGHTS, abs=1e-3)


def _beating_clock() -> BeatClock:
    clock = BeatClock()
    for i in range(12):
        clock.feed_beat(i * 0.857)
    return clock


def test_grip_follows_the_model_contraction() -> None:
    """Blender の心臓を掴む手は、この心臓の輪郭に巻き付き、形が縮むのに合わせて握り直す。"""
    clock = _beating_clock()
    last = 11 * 0.857
    interval = clock.interval()
    rest_body, rest_cycle = model_grip(clock.cycle(last + interval * 0.97))
    assert rest_cycle.squeeze == pytest.approx(0.0, abs=0.02)
    assert rest_body.rim == pytest.approx(MODEL_RIM, abs=0.01)
    # 形そのものが動くので、作った心臓の鼓動の縮み・寄りは足さない
    assert rest_body.beat_squeeze == 0.0 and rest_body.rock == 0.0
    # 拍の頭で手が跳ねて指がぶるっと震えない（この心臓は拍より後でゆっくり縮む）
    assert rest_body.kick == 0.0 and HEART_BODY.kick == 1.0
    squeezes = []
    for k in range(40):
        body, cycle = model_grip(clock.cycle(last + interval * k / 40))
        squeezes.append(cycle.squeeze)
        pose = grip_pose(
            shift=(0.0, -0.08), size=0.74, cycle=cycle, grip=0.0, time_s=0.0, body=body
        )
        for i in range(1, 5):
            # 指の付け根は正面に載り、指先は縁を越えて奥へ回らない
            assert pose.finger_facing(i, 0.0) > 0.8, (k, i)
            assert pose.finger_facing(i, 1.0) > 0.3, (k, i)
    # いちばん縮んだ所で 1。縮むのは拍の頭より後（このアニメは 0.3〜0.5 秒でいちばん縮む）
    peak = max(range(40), key=lambda k: squeezes[k])
    assert squeezes[peak] == pytest.approx(1.0, abs=0.05)
    assert 0.3 < peak * interval / 40 < 0.55
    body, _cycle = model_grip(clock.cycle(last + peak * interval / 40))
    # 左室の側（画面の右下）がよく縮む
    lv = math.radians(-30.0)
    assert rim_at(lv, body.rim) < rim_at(lv, MODEL_RIM) * 0.9
    # 作った心臓の見た目では、これまでどおりの胴と拍
    cycle = clock.cycle(last + 0.1)
    assert grip_for_look(realistic_look("surgical"), cycle) == (HEART_BODY, cycle)
    assert grip_for_look(realistic_look("model"), cycle)[0] != HEART_BODY


def test_stethoscope_moves_with_the_shrinking_surface() -> None:
    clock = _beating_clock()
    last = 11 * 0.857
    rest = clock.cycle(last + clock.interval() * 0.97)
    peak = clock.cycle(last + 0.42)
    assert follow_scale(rest, 0.5, -0.5) == pytest.approx(1.0, abs=0.01)
    # 左室の上に当てた聴診器は真ん中へ寄る。ほとんど動かない左上（右房）では寄らない
    assert follow_scale(peak, 0.5, -0.5) < 0.93
    assert follow_scale(peak, -0.5, 0.5) == pytest.approx(1.0, abs=0.04)


def test_frame_uses_the_model_body_size() -> None:
    rect = QRectF(0, 0, 720, 720)
    look = realistic_look("model")
    model = gl_heart_frame(rect, 0.7, look)
    made = gl_heart_frame(rect, 0.7, realistic_look("surgical"))
    assert model.half_w / made.half_w == pytest.approx(
        MODEL_HALF[0] * look.size_factor / BODY_HALF[0], rel=1e-6
    )


def test_model_shader_fades_vessel_ends_and_moves_the_auricle() -> None:
    for name in ("vesselFade", "auricleMove", "gripContact", "uAurL", "uAtriaL", "uHandOn"):
        assert name in MODEL_VERTEX, name
    assert "uPass" in MODEL_FRAGMENT and "vFade" in MODEL_FRAGMENT
    # 上でまとめて消すのは胴より上（上の太い血管だけ）
    assert TOP_FADE[0] > 0.6
    for center, axis, radius, length in VESSEL_ENDS:
        assert 0.9 < math.sqrt(sum(a * a for a in axis)) < 1.1
        assert 0.0 < radius < 0.25 and 0.0 < length <= 0.2
        # 切り口は胴の外寄り（胴の真ん中から離れている）
        assert math.dist(center, MODEL_BODY_CENTER) > 0.6


def test_model_draws_faded_vessels_and_dented_grip(qapp: QApplication) -> None:
    del qapp
    from PySide6.QtGui import QOffscreenSurface, QOpenGLContext

    ctx = QOpenGLContext()
    surface = QOffscreenSurface()
    surface.create()
    if not ctx.create() or not ctx.makeCurrent(surface):
        pytest.skip("OpenGL なし")
    from stream_heartbeat.render.heart_gl import OffscreenHeart

    heart = OffscreenHeart()
    look = realistic_look("model")
    clock = _beating_clock()
    cycle = clock.cycle(11 * 0.857 + 0.3)
    clear = QColor(0, 0, 0, 0)
    image = heart.render(width=200, height=200, cycle=cycle, look=look, background=clear)
    if heart._renderer.model_error is not None:
        pytest.skip(heart._renderer.model_error)
    # 上の太い血管は、切り口へ向かって透けて消える（いちばん上の行ほど薄い）
    rows = []
    for y in range(200):
        alpha = max(image.pixelColor(x, y).alpha() for x in range(200))
        if alpha > 0:
            rows.append(alpha)
    assert rows[0] < 128 and max(rows) == 255
    body, grip_cycle = model_grip(cycle)
    pose = grip_pose(
        shift=(look.shift_x, look.shift_y),
        size=0.7 * look.size_factor,
        cycle=grip_cycle,
        grip=1.0,
        time_s=0.0,
        body=body,
    )
    held = heart.render(
        width=200, height=200, cycle=cycle, look=look, background=clear, hand=pose
    )
    # 指の所が凹んで影が付く（掴んでいないときと絵が変わる）
    assert held != image
