"""Blender の心臓（GLB）を、アプリが読む assets/heart_model/ の 3 つのファイルにする。

- heart_model.bin: 形・法線・UV・シェイプキー 3 つ・くぼみ具合・三角形と、拍のキーの重みの並び
  （16 bit に詰めて zlib で縮める。読み方は render/model_mesh.py）
- gradient.png: グラデの波模様の色（bake_gradient.py が material/build/ に書いたものを縮める）
- env.png: ガラスの映り込み（同じく material/build/ から）

venv の Python でリポジトリの直下から実行:
  .venv\\Scripts\\python.exe scripts\\heart_model\\convert_glb.py
"""

from __future__ import annotations

import array
import json
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GLB = ROOT / "material" / "data" / "wip" / "GLB" / "4.glb"
BUILD = ROOT / "material" / "build"
OUT = ROOT / "src" / "stream_heartbeat" / "assets" / "heart_model"
# グラデの色はなだらかなので小さくてよい（縦は UV の範囲の縦横比に合わせる）
GRADIENT_WIDTH = 768

sys.path.insert(0, str(ROOT / "src"))
from stream_heartbeat.render.model_mesh import MAGIC  # noqa: E402

_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
_FORMATS = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20 : 20 + json_len])
    bin_start = 20 + json_len + 8
    return gltf, data[bin_start:]


def _accessor(gltf: dict, blob: bytes, index: int) -> list[tuple[float, ...]]:
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    n = _COMPONENTS[acc["type"]]
    fmt = _FORMATS[acc["componentType"]]
    offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", 0) or n * struct.calcsize(fmt)
    out = []
    for i in range(acc["count"]):
        out.append(struct.unpack_from("<" + fmt * n, blob, offset + i * stride))
    return out


def _int16(value: float, scale: float) -> int:
    return max(-32767, min(32767, round(value / scale * 32767.0)))


def _pack4(rows: list[tuple[float, ...]], scales: tuple[float, float, float]) -> bytes:
    """3 成分を 16 bit 符号付きに詰め、4 つ目は 0（GPU が読みやすい 8 バイトずつ）。"""
    out = array.array("h")
    for x, y, z in rows:
        out.extend((_int16(x, scales[0]), _int16(y, scales[1]), _int16(z, scales[2]), 0))
    return out.tobytes()


def _max_abs(rows: list[tuple[float, ...]], axis: int | None = None) -> float:
    if axis is None:
        return max(max(abs(c) for c in row) for row in rows) or 1.0
    return max(abs(row[axis]) for row in rows) or 1.0


def _cavity(
    pos: list[tuple[float, ...]], nrm: list[tuple[float, ...]], idx: list[int], rounds: int = 12
) -> tuple[list[float], list[float]]:
    """頂点ごとのくぼみ具合（細かい溝・広い谷）。正がくぼみ、負が出っ張り。

    UV の継ぎ目で分かれた同じ位置の頂点は 1 つにまとめて数える（継ぎ目に筋が出ないよう）。
    細かい溝は隣の平均とのずれ、広い谷は位置を何度かならしたあとのずれを法線の向きで測る。
    """
    canon: dict[tuple[float, float, float], int] = {}
    ids = [canon.setdefault(tuple(round(c, 5) for c in p), len(canon)) for p in pos]
    n = len(canon)
    pts = [(0.0, 0.0, 0.0)] * n
    normals = [[0.0, 0.0, 0.0] for _ in range(n)]
    for i, k in enumerate(ids):
        pts[k] = pos[i]
        for a in range(3):
            normals[k][a] += nrm[i][a]
    for v in normals:
        length = sum(c * c for c in v) ** 0.5 or 1.0
        v[:] = [c / length for c in v]
    links: list[set[int]] = [set() for _ in range(n)]
    for t in range(0, len(idx), 3):
        a, b, c = ids[idx[t]], ids[idx[t + 1]], ids[idx[t + 2]]
        links[a].update((b, c))
        links[b].update((a, c))
        links[c].update((a, b))

    def smooth(src: list[tuple[float, ...]]) -> list[tuple[float, ...]]:
        out = []
        for k in range(n):
            near = links[k] or {k}
            m = len(near)
            out.append(tuple(sum(src[j][a] for j in near) / m for a in range(3)))
        return out

    def along_normal(moved: list[tuple[float, ...]]) -> list[float]:
        return [sum((moved[k][a] - pts[k][a]) * normals[k][a] for a in range(3)) for k in range(n)]

    fine = along_normal(smooth(pts))
    moved = pts
    for _ in range(rounds):
        moved = smooth(moved)
    broad = along_normal(moved)

    def unit(values: list[float]) -> list[float]:
        spread = (sum(v * v for v in values) / len(values)) ** 0.5 or 1.0
        return [max(-1.0, min(1.0, v / (3.0 * spread))) for v in values]

    fine_u, broad_u = unit(fine), unit(broad)
    return [fine_u[k] for k in ids], [broad_u[k] for k in ids]


def convert(glb: Path = GLB) -> dict:
    gltf, blob = _read_glb(glb)
    mesh = gltf["meshes"][0]
    prim = mesh["primitives"][0]
    attrs = prim["attributes"]
    pos = _accessor(gltf, blob, attrs["POSITION"])
    nrm = _accessor(gltf, blob, attrs["NORMAL"])
    uv = _accessor(gltf, blob, attrs["TEXCOORD_0"])
    idx = [i[0] for i in _accessor(gltf, blob, prim["indices"])]
    targets = [_accessor(gltf, blob, t["POSITION"]) for t in prim["targets"]]
    names = mesh.get("extras", {}).get("targetNames", [f"key{i}" for i in range(len(targets))])
    if len(pos) >= 65536:
        raise SystemExit("頂点が 65536 以上あると 16 bit の番号に入りません")

    pos_scale = tuple(_max_abs(pos, a) for a in range(3))
    delta_scales = [_max_abs(t) for t in targets]
    u_min = min(u for u, _v in uv)
    v_min = min(v for _u, v in uv)
    u_span = (max(u for u, _v in uv) - u_min) or 1.0
    v_span = (max(v for _u, v in uv) - v_min) or 1.0
    uv_out = array.array("H")
    for u, v in uv:
        uv_out.extend((round((u - u_min) / u_span * 65535), round((v - v_min) / v_span * 65535)))

    blocks = [
        ("pos", _pack4(pos, pos_scale)),
        ("normal", _pack4(nrm, (1.0, 1.0, 1.0))),
        ("uv", uv_out.tobytes()),
    ]
    for i, (target, scale) in enumerate(zip(targets, delta_scales)):
        blocks.append((f"delta{i}", _pack4(target, (scale, scale, scale))))
    fine, broad = _cavity(pos, nrm, idx)
    cavity = array.array("h")
    for f, b in zip(fine, broad):
        cavity.extend((_int16(f, 1.0), _int16(b, 1.0)))
    blocks.append(("cavity", cavity.tobytes()))
    blocks.append(("index", array.array("H", idx).tobytes()))

    payload = b""
    offsets: dict[str, int] = {}
    for name, data in blocks:
        offsets[name] = len(payload)
        payload += data

    anim = gltf["animations"][0]
    sampler = anim["samplers"][anim["channels"][0]["sampler"]]
    times = [t[0] for t in _accessor(gltf, blob, sampler["input"])]
    flat = [w[0] for w in _accessor(gltf, blob, sampler["output"])]
    count = len(targets)
    weights = [flat[i * count : (i + 1) * count] for i in range(len(times))]

    header = {
        "vertices": len(pos),
        "indices": len(idx),
        "pos_scale": pos_scale,
        "delta_scales": delta_scales,
        "uv_offset": (u_min, v_min),
        "uv_scale": (u_span, v_span),
        "offsets": offsets,
        "keys": names,
        "anim_times": [round(t, 5) for t in times],
        "anim_weights": [[round(w, 4) for w in row] for row in weights],
    }
    head = json.dumps(header, ensure_ascii=False).encode("utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    packed = zlib.compress(payload, 9)
    (OUT / "heart_model.bin").write_bytes(MAGIC + struct.pack("<I", len(head)) + head + packed)
    return header


def copy_images() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    gradient = QImage(str(BUILD / "gradient_bake.png"))
    env = QImage(str(BUILD / "glass_env.png"))
    if gradient.isNull() or env.isNull():
        raise SystemExit(
            "material/build/ に画像がありません。先に bake_gradient.py を実行してください"
        )
    smooth = Qt.TransformationMode.SmoothTransformation
    height = round(GRADIENT_WIDTH * gradient.height() / gradient.width())
    gradient = gradient.scaled(GRADIENT_WIDTH, height, Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
    gradient.convertToFormat(QImage.Format.Format_RGB888).save(str(OUT / "gradient.png"))
    env.convertToFormat(QImage.Format.Format_RGB888).save(str(OUT / "env.png"))


if __name__ == "__main__":
    info = convert()
    copy_images()
    size = (OUT / "heart_model.bin").stat().st_size
    print(f"頂点 {info['vertices']}・三角形 {info['indices'] // 3}・キー {info['keys']}")
    print(f"heart_model.bin {size / 1e6:.2f} MB・拍のコマ {len(info['anim_times'])}")
    print("範囲", [round(s, 3) for s in info["pos_scale"]])
    print("UV", info["uv_offset"], info["uv_scale"])
