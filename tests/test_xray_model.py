"""レントゲン4（Blender の心臓を X 線で写し、周りに肋骨を描く）。

肋骨のファイル・見た目の選び方・材質の欄・VTS のアイテムの作り直し。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.heart_looks import (
    STYLE_LOOKS,
    XRAY_MODEL_LOOK,
    realistic_look,
    style_look,
    xray_model_look,
)
from stream_heartbeat.render.model_bones import BONE_FRAGMENT, BONE_VERTEX
from stream_heartbeat.render.model_mesh import (
    RIBCAGE_MAGIC,
    RIBCAGE_PATH,
    ModelMeshError,
    load_ribcage_mesh,
)
from stream_heartbeat.render.model_shaders import MATERIAL_XRAY, MATERIALS
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.style_catalog import (
    STYLES,
    XRAY_MATERIALS,
    chosen_material,
    has_material,
    has_xray_material,
)
from stream_heartbeat.ui.vts_panel import look_key


def test_ribcage_file_is_bundled_and_whole() -> None:
    assert RIBCAGE_PATH.is_file()
    mesh = load_ribcage_mesh()
    # 16 bit の番号に収まる（心臓と同じく GPU へは 16 bit のまま渡す）
    assert 0 < mesh.vertex_count < 65536
    assert mesh.index_count % 3 == 0
    assert {"pos", "normal", "index"} <= set(mesh.offsets)
    assert mesh.offsets["normal"] >= mesh.vertex_count * 8
    assert mesh.offsets["index"] + mesh.index_count * 2 <= len(mesh.payload)
    # 心臓（高さ ±1.2）を囲む大きさ。置き場所は Blender のまま（上の肋骨は心臓より上まで届く）
    assert mesh.pos_scale[1] > 3.0


def test_broken_ribcage_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ModelMeshError):
        load_ribcage_mesh(tmp_path / "missing.bin")
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"not bones")
    with pytest.raises(ModelMeshError):
        load_ribcage_mesh(bad)
    cut = tmp_path / "cut.bin"
    cut.write_bytes(RIBCAGE_MAGIC + b"\x10\x00\x00\x00{}")
    with pytest.raises(ModelMeshError):
        load_ribcage_mesh(cut)


def test_bone_shaders_work_on_windows_and_mac() -> None:
    for source in (BONE_VERTEX, BONE_FRAGMENT):
        assert source.lstrip().startswith("#version 130")


def test_xray_model_is_listed_after_xray_3() -> None:
    names = [label for _style, _look, label in STYLES]
    assert names.index("レントゲン4") == names.index("レントゲン3") + 1
    assert ("xray_heart", XRAY_MODEL_LOOK.key, "レントゲン4") in STYLES


def test_style_look_picks_the_blender_heart_with_bones() -> None:
    look = style_look("xray_heart", "model")
    assert look.program == "model" and look.bones
    assert look.material == MATERIAL_XRAY
    # X 線だけ背景に重ねる描き方（手の裏も透ける）
    assert look.cutout
    red = style_look("xray_heart", "model", xray_material="real")
    assert red.material == "real" and red.bones and not red.cutout
    # レントゲン3 はそのまま。リアル1 の材質はレントゲン4 に混ざらない
    assert style_look("xray_heart", "") == STYLE_LOOKS["xray_heart"]
    assert style_look("xray_heart", "model", "glass").material == MATERIAL_XRAY
    assert style_look("realistic", "model", "glass", "real") == realistic_look("model", "glass")
    assert not realistic_look("model").bones


def test_xray_materials_cover_every_shader_material() -> None:
    keys = [key for key, _label in XRAY_MATERIALS]
    assert keys[0] == MATERIAL_XRAY
    assert sorted(keys) == sorted(MATERIALS)
    assert xray_model_look().material == MATERIAL_XRAY
    assert has_xray_material("xray_heart", "model")
    assert not has_xray_material("xray_heart", "")
    assert not has_xray_material("realistic", "model")
    assert not has_material("xray_heart", "model")


def test_new_profile_starts_xray_model_with_xray() -> None:
    assert HeartProfile().xray_material == MATERIAL_XRAY


def test_chosen_material_follows_style() -> None:
    profile = HeartProfile(heart_material="glass", xray_material="real")
    assert chosen_material(profile) == "glass"
    profile.style, profile.realistic_look = "xray_heart", "model"
    assert chosen_material(profile) == "real"
    profile.realistic_look = ""
    assert chosen_material(profile) == ""


def test_vts_item_is_remade_when_material_changes() -> None:
    profile = HeartProfile(style="xray_heart", realistic_look="model")
    before = look_key(profile)
    profile.xray_material = "glass"
    assert look_key(profile) != before
    # リアル1 の材質も絵に入る
    real1 = HeartProfile(style="realistic", realistic_look="model")
    before = look_key(real1)
    real1.heart_material = "gradient"
    assert look_key(real1) != before
    # 材質の無いスタイルは今までどおり
    assert look_key(HeartProfile(style="cute")) == ("cute", "model", "")


def test_xray_material_row_follows_style_and_saves(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    monkeypatch.setattr("stream_heartbeat.ui.operator_window.resolve_data_dir", lambda: tmp_path)
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    form = operator._style_form
    operator._select_style("xray_heart", "model")
    assert form.isRowVisible(operator._xray_material)
    assert not form.isRowVisible(operator._material)
    assert output.canvas._look().material == MATERIAL_XRAY
    operator._xray_material.setCurrentIndex(operator._xray_material.findData("glass"))
    assert session.profile.xray_material == "glass"
    assert session.profile.heart_material == "real"
    assert output.canvas._look().material == "glass"
    # レントゲン4 では演出（聴診器・わしづかみ）も選べ、配信用の窓で回せる
    assert operator._effect.count() > 1
    # リアル1 に戻すと、リアル1 の材質の欄に戻る（選んだガラスはレントゲン4 にだけ残る）
    operator._select_style("realistic", "model")
    assert form.isRowVisible(operator._material)
    assert not form.isRowVisible(operator._xray_material)
    assert output.canvas._look().material == "real"
    assert session.profile.xray_material == "glass"
    operator.close()
    output.close()
