"""立体心臓の形の保存と読み込み（起動を速くするため）。"""

from __future__ import annotations

from array import array
from pathlib import Path

import pytest

from stream_heartbeat.render import mesh_cache
from stream_heartbeat.render.heart_mesh import FLOATS_PER_VERTEX, HeartMesh


def _tiny_mesh() -> HeartMesh:
    count = 6
    data = array("f", [float(i) * 0.5 for i in range(count * FLOATS_PER_VERTEX)])
    return HeartMesh(
        data=data,
        vertex_count=count,
        section_start=3,
        tube_start=1,
        auricle_start=4,
        coronary_start=5,
    )


def test_saved_mesh_reads_back_the_same(tmp_path: Path) -> None:
    path = tmp_path / "cache" / mesh_cache.CACHE_FILENAME
    mesh = _tiny_mesh()
    mesh_cache.save_mesh(path, mesh, "key-1")
    loaded = mesh_cache.load_mesh(path, "key-1")
    assert loaded == mesh


def test_other_key_or_broken_file_is_rebuilt(tmp_path: Path) -> None:
    path = tmp_path / mesh_cache.CACHE_FILENAME
    mesh_cache.save_mesh(path, _tiny_mesh(), "key-1")
    # 形を作るコードが変わった
    assert mesh_cache.load_mesh(path, "key-2") is None
    # 書き込みの途中で切れた
    raw = path.read_bytes()
    path.write_bytes(raw[:-10])
    assert mesh_cache.load_mesh(path, "key-1") is None
    path.write_bytes(b"garbage")
    assert mesh_cache.load_mesh(path, "key-1") is None
    assert mesh_cache.load_mesh(tmp_path / "missing.bin", "key-1") is None


def test_second_start_reads_instead_of_building(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[int] = []

    def fake_build() -> HeartMesh:
        built.append(1)
        return _tiny_mesh()

    monkeypatch.setattr(mesh_cache, "build_heart_mesh", fake_build)
    first = mesh_cache.load_or_build_heart_mesh(tmp_path)
    assert built == [1]
    assert mesh_cache.has_cached_mesh(tmp_path)
    second = mesh_cache.load_or_build_heart_mesh(tmp_path)
    assert built == [1]
    assert second == first


def test_shape_key_changes_with_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 開発中はソースの中身で決まる（同じ中身なら同じ鍵）
    assert mesh_cache.shape_key() == mesh_cache.shape_key()
    fake = tmp_path / "mesh_cache.py"
    for name in mesh_cache._SHAPE_MODULES:
        (tmp_path / name).write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr(mesh_cache, "__file__", str(fake))
    before = mesh_cache.shape_key()
    (tmp_path / mesh_cache._SHAPE_MODULES[0]).write_text("a = 2\n", encoding="utf-8")
    assert mesh_cache.shape_key() != before
