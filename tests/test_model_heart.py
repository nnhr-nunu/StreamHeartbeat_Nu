"""Blender で作った心臓（リアル1）: 形のファイル・拍の動き・材質の選び方。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.model_mesh import (
    ENV_PATH,
    GRADIENT_PATH,
    MAGIC,
    ModelMeshError,
    beat_weights,
    load_model_mesh,
)
from stream_heartbeat.render.model_shaders import MATERIALS, MODEL_FRAGMENT, MODEL_VERTEX
from stream_heartbeat.session import HeartSession
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
