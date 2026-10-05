"""Blender で作った心臓の形（assets/heart_model/heart_model.bin）を読む。

中身は scripts/heart_model/convert_glb.py が書く。形・法線・シェイプキーは 16 bit に詰めてあり、
GPU が -1〜1（UV は 0〜1）に直して読むので、Python では並べ直さずそのまま載せる。
拍の動きは Blender のアニメ（1 秒・24 コマ）の、キーの重みの並びで持つ。
"""

from __future__ import annotations

import bisect
import json
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MAGIC = b"SHHM1\n"
RIBCAGE_MAGIC = b"SHRB1\n"
MODEL_DIR = Path(__file__).resolve().parent.parent / "assets" / "heart_model"
MODEL_PATH = MODEL_DIR / "heart_model.bin"
GRADIENT_PATH = MODEL_DIR / "gradient.png"
ENV_PATH = MODEL_DIR / "env.png"
# レントゲン4 の肋骨。心臓と同じ座標（置き場所は Blender のまま）
RIBCAGE_PATH = MODEL_DIR / "ribcage.bin"
# 速い心拍では、次の拍までにアニメを終える（間隔のこの割合で 1 回ぶん）
ANIM_FIT = 0.92


class ModelMeshError(RuntimeError):
    """形のファイルが無い・壊れている。"""


@dataclass(frozen=True)
class ModelMesh:
    payload: bytes
    vertex_count: int
    index_count: int
    pos_scale: tuple[float, float, float]
    delta_scales: tuple[float, ...]
    uv_offset: tuple[float, float]
    uv_scale: tuple[float, float]
    offsets: dict[str, int]
    anim_times: tuple[float, ...]
    anim_weights: tuple[tuple[float, ...], ...]

    @property
    def key_count(self) -> int:
        return len(self.delta_scales)


@dataclass(frozen=True)
class ModelAnim:
    """拍の動き（キーの重みの並び）だけ。手や聴診器を心臓の動きに合わせるのに使う。"""

    anim_times: tuple[float, ...]
    anim_weights: tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class RibcageMesh:
    """肋骨の形。形・法線は 16 bit を 4 つずつ、三角形の番号は 16 bit。"""

    payload: bytes
    vertex_count: int
    index_count: int
    pos_scale: tuple[float, float, float]
    offsets: dict[str, int]


def _read_head(path: Path, magic: bytes = MAGIC) -> tuple[dict, bytes]:
    """(見出し, 縮めた中身)。"""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ModelMeshError("心臓の形のファイルを読めません") from exc
    if not data.startswith(magic):
        raise ModelMeshError("心臓の形のファイルが違います")
    try:
        start = len(magic)
        head_len = struct.unpack_from("<I", data, start)[0]
        head = json.loads(data[start + 4 : start + 4 + head_len].decode("utf-8"))
    except (struct.error, ValueError) as exc:
        raise ModelMeshError("心臓の形のファイルが壊れています") from exc
    return head, data[start + 4 + head_len :]


@lru_cache(maxsize=1)
def load_model_anim(path: Path = MODEL_PATH) -> ModelAnim | None:
    """拍の動きだけを読む（形は広げないので軽い）。読めなければ None。"""
    try:
        head, _packed = _read_head(path)
        anim = ModelAnim(
            anim_times=tuple(float(t) for t in head["anim_times"]),
            anim_weights=tuple(tuple(float(w) for w in row) for row in head["anim_weights"]),
        )
    except (ModelMeshError, KeyError, TypeError, ValueError):
        return None
    if not anim.anim_times or len(anim.anim_times) != len(anim.anim_weights):
        return None
    return anim


def load_model_mesh(path: Path = MODEL_PATH) -> ModelMesh:
    head, packed = _read_head(path)
    try:
        payload = zlib.decompress(packed)
        mesh = ModelMesh(
            payload=payload,
            vertex_count=int(head["vertices"]),
            index_count=int(head["indices"]),
            pos_scale=tuple(head["pos_scale"]),
            delta_scales=tuple(head["delta_scales"]),
            uv_offset=tuple(head["uv_offset"]),
            uv_scale=tuple(head["uv_scale"]),
            offsets={str(k): int(v) for k, v in head["offsets"].items()},
            anim_times=tuple(float(t) for t in head["anim_times"]),
            anim_weights=tuple(tuple(float(w) for w in row) for row in head["anim_weights"]),
        )
    except (struct.error, ValueError, KeyError, TypeError, zlib.error) as exc:
        raise ModelMeshError("心臓の形のファイルが壊れています") from exc
    end = mesh.offsets.get("index", 0) + mesh.index_count * 2
    if len(mesh.payload) < end or len(mesh.anim_times) != len(mesh.anim_weights):
        raise ModelMeshError("心臓の形のファイルが壊れています")
    return mesh


def load_ribcage_mesh(path: Path = RIBCAGE_PATH) -> RibcageMesh:
    head, packed = _read_head(path, RIBCAGE_MAGIC)
    try:
        payload = zlib.decompress(packed)
        mesh = RibcageMesh(
            payload=payload,
            vertex_count=int(head["vertices"]),
            index_count=int(head["indices"]),
            pos_scale=tuple(head["pos_scale"]),
            offsets={str(k): int(v) for k, v in head["offsets"].items()},
        )
    except (ValueError, KeyError, TypeError, zlib.error) as exc:
        raise ModelMeshError("肋骨の形のファイルが壊れています") from exc
    if len(mesh.payload) < mesh.offsets.get("index", 0) + mesh.index_count * 2:
        raise ModelMeshError("肋骨の形のファイルが壊れています")
    return mesh


def beat_weights(mesh: ModelMesh | ModelAnim, age: float, interval: float) -> tuple[float, ...]:
    """拍から age 秒たったときの、シェイプキーの重み。

    アニメの最後のコマが休んでいる形。拍の瞬間はそこから始め（コマの 0 秒を足す）、
    終わったら次の拍まで休んだまま。速い心拍では間隔に収まるよう速める。
    """
    times = (0.0, *mesh.anim_times)
    rest = mesh.anim_weights[-1]
    rows = (rest, *mesh.anim_weights)
    length = times[-1]
    speed = max(1.0, length / max(1e-3, interval * ANIM_FIT))
    t = max(0.0, age) * speed
    if t >= length:
        return rest
    i = bisect.bisect_right(times, t) - 1
    t0, t1 = times[i], times[i + 1]
    f = (t - t0) / max(1e-6, t1 - t0)
    return tuple(a + (b - a) * f for a, b in zip(rows[i], rows[i + 1]))
