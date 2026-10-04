"""Blender の心臓（GLB）の胴の形を測り、render/model_body.py に書く値を出す。

- 正面から見た胴の輪郭（胴の真ん中から -180° 10° おき）と、楕円に合わせた奥行き
- シェイプキーの重みが 1 増えたときの、輪郭・奥行きの変わり方
- 輪郭の平均の縮み（拍の縮み 0〜1 に直す割合）と、胴の半分の幅・高さ

胴は形の座標で y が BODY_TOP より下（上の太い血管を除く）。真ん中は model_gl の MODEL_BODY_CENTER。
venv の Python でリポジトリの直下から実行:
  .venv\\Scripts\\python.exe scripts\\heart_model\\measure_body.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from convert_glb import GLB, _accessor, _read_glb  # noqa: E402

from stream_heartbeat.render.model_gl import MODEL_BODY_CENTER  # noqa: E402

BODY_TOP = 0.4
BINS = 36
# 正面の面を拾う升の大きさと、奥行きを合わせる範囲（輪郭までの長さに対する割合）
FRONT_CELL = 0.04
FRONT_REACH = 0.85


def measure(points: list[tuple[float, float, float]]) -> tuple[list[float], float]:
    """胴の点（真ん中からの位置）の、輪郭と奥行き。"""
    rim = [0.0] * BINS
    for x, y, _z in points:
        k = round((math.atan2(y, x) + math.pi) / (2.0 * math.pi) * BINS) % BINS
        rim[k] = max(rim[k], math.hypot(x, y))
    # 正面の面（xy の升ごとにいちばん手前の点）が、輪郭まで楕円で下がるとして奥行きを合わせる
    front: dict[tuple[int, int], tuple[float, float, float]] = {}
    for p in points:
        cell = (math.floor(p[0] / FRONT_CELL), math.floor(p[1] / FRONT_CELL))
        if cell not in front or p[2] > front[cell][2]:
            front[cell] = p
    num = den = 0.0
    for x, y, z in front.values():
        phi = math.atan2(y, x)
        f = (phi + math.pi) / (2.0 * math.pi) * BINS
        i = math.floor(f)
        edge = rim[i % BINS] * (1.0 - (f - i)) + rim[(i + 1) % BINS] * (f - i)
        rho = math.hypot(x, y) / max(edge, 1e-6)
        if rho < FRONT_REACH:
            s = math.sqrt(1.0 - rho * rho)
            num += z * s
            den += s * s
    return rim, num / den


def main() -> None:
    gltf, blob = _read_glb(GLB)
    prim = gltf["meshes"][0]["primitives"][0]
    pos = _accessor(gltf, blob, prim["attributes"]["POSITION"])
    keys = [_accessor(gltf, blob, t["POSITION"]) for t in prim["targets"]]
    anim = gltf["animations"][0]
    sampler = anim["samplers"][anim["channels"][0]["sampler"]]
    flat = [w[0] for w in _accessor(gltf, blob, sampler["output"])]
    rest = flat[-len(keys) :]
    body = [i for i, p in enumerate(pos) if p[1] < BODY_TOP]
    cx, cy, cz = MODEL_BODY_CENTER

    def shape(weights: list[float]) -> tuple[list[float], float]:
        pts = []
        for i in body:
            x, y, z = pos[i]
            for w, key in zip(weights, keys):
                x, y, z = x + w * key[i][0], y + w * key[i][1], z + w * key[i][2]
            pts.append((x - cx, y - cy, z - cz))
        return measure(pts)

    rim0, depth0 = shape(rest)
    print("REST_WEIGHTS", [round(w, 3) for w in rest])
    print("MODEL_RIM", [round(r, 3) for r in rim0])
    print("MODEL_DEPTH", round(depth0, 3))
    shrinks = []
    for k in range(len(keys)):
        weights = list(rest)
        weights[k] = 1.0
        unit = 1.0 - rest[k]
        rim, depth = shape(weights)
        drim = [(a - b) / unit for a, b in zip(rim, rim0)]
        shrinks.append(-sum(drim) / BINS)
        print(f"MODEL_RIM_KEYS[{k}]", [round(d, 3) for d in drim])
        print(f"MODEL_DEPTH_KEYS[{k}]", round((depth - depth0) / unit, 4))
    print("SHRINK_PER_KEY", [round(s, 4) for s in shrinks])
    full = max(
        sum((w - r) * s for w, r, s in zip(flat[i : i + len(keys)], rest, shrinks))
        for i in range(0, len(flat), len(keys))
    )
    print("SHRINK_FULL", round(full, 4))
    xs = [pos[i][0] - cx for i in body]
    ys = [pos[i][1] - cy for i in body]
    print("MODEL_HALF", round((max(xs) - min(xs)) / 2, 3), round((max(ys) - min(ys)) / 2, 3))


if __name__ == "__main__":
    main()
