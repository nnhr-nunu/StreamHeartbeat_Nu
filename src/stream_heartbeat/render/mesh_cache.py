"""立体心臓の形を一度だけ計算してファイルに残し、次の起動からはそれを読む。

形の計算は Python だけで 1.5 秒ほどかかり、起動が止まったように見える。
形は数式から毎回同じに決まるので、結果の頂点をそのまま保存しておけばよい。
形を作るコードが変わったとき（開発中はソースの中身、配布版は exe の作り直し）は
鍵が変わり、作り直す。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from array import array
from pathlib import Path

from stream_heartbeat.render.heart_mesh import FLOATS_PER_VERTEX, HeartMesh, build_heart_mesh

CACHE_FILENAME = "heart_mesh.bin"
_MAGIC = b"SHBMESH1"
# 形を決めるモジュール。どれかの中身が変われば作り直す
_SHAPE_MODULES = ("heart_mesh.py", "heart_section.py", "heart_auricles.py", "heart_coronary.py")


def shape_key() -> str:
    """形を作るコードの指紋。"""
    digest = hashlib.sha256()
    here = Path(__file__).resolve().parent
    sources = [here / name for name in _SHAPE_MODULES]
    if all(path.is_file() for path in sources):
        for path in sources:
            digest.update(path.read_bytes())
    else:
        # 配布版はソースを持たない。exe を作り直すまで形は変わらないので exe で見分ける
        exe = Path(sys.executable)
        try:
            stat = exe.stat()
            digest.update(f"{exe.name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        except OSError:
            digest.update(b"unknown")
    digest.update(str(FLOATS_PER_VERTEX).encode())
    return digest.hexdigest()


def save_mesh(path: Path, mesh: HeartMesh, key: str) -> None:
    header = json.dumps(
        {
            "key": key,
            "vertex_count": mesh.vertex_count,
            "section_start": mesh.section_start,
            "tube_start": mesh.tube_start,
            "auricle_start": mesh.auricle_start,
            "coronary_start": mesh.coronary_start,
        }
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as fh:
        fh.write(_MAGIC)
        fh.write(len(header).to_bytes(4, "little"))
        fh.write(header)
        fh.write(mesh.data.tobytes())
    os.replace(tmp, path)


def load_mesh(path: Path, key: str) -> HeartMesh | None:
    """鍵が合い、中身が欠けていなければ読む。合わない・壊れているときは None。"""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw.startswith(_MAGIC) or len(raw) < len(_MAGIC) + 4:
        return None
    at = len(_MAGIC)
    size = int.from_bytes(raw[at : at + 4], "little")
    at += 4
    try:
        header = json.loads(raw[at : at + size].decode("utf-8"))
        if header.get("key") != key:
            return None
        count = int(header["vertex_count"])
        data = array("f")
        data.frombytes(raw[at + size :])
        if count <= 0 or len(data) != count * FLOATS_PER_VERTEX:
            return None
        return HeartMesh(
            data=data,
            vertex_count=count,
            section_start=int(header["section_start"]),
            tube_start=int(header["tube_start"]),
            auricle_start=int(header["auricle_start"]),
            coronary_start=int(header["coronary_start"]),
        )
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return None


def load_or_build_heart_mesh(cache_dir: Path | None) -> HeartMesh:
    """保存した形があれば読み、無ければ作って保存する。保存できなくても形は返す。"""
    if cache_dir is None:
        return build_heart_mesh()
    path = cache_dir / CACHE_FILENAME
    key = shape_key()
    mesh = load_mesh(path, key)
    if mesh is not None:
        return mesh
    mesh = build_heart_mesh()
    try:
        save_mesh(path, mesh, key)
    except OSError:
        pass
    return mesh


_shared: HeartMesh | None = None


def shared_heart_mesh(cache_dir: Path | None) -> HeartMesh:
    """アプリの中で 1 つの形を使い回す（配信用の窓を作り直しても読み直さない）。"""
    global _shared
    if _shared is None:
        _shared = load_or_build_heart_mesh(cache_dir)
    return _shared


def has_cached_mesh(cache_dir: Path) -> bool:
    """次の読み込みが保存済みの形で済むか（起動画面の文言を選ぶため。中身までは確かめない）。"""
    return (cache_dir / CACHE_FILENAME).is_file()
