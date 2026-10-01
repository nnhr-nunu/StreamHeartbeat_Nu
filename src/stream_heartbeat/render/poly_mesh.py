"""オシャレ2 のポリゴン風の心臓。リアルと同じ形を、粗い三角形で作り直す。

本体は同じ外形を少ない格子で、血管は六角の管でたどる。頂点の法線は滑らかなまま
（拍で膨らむ向きがそろい、面のあいだが割れない）にして、面ごとの平らな陰は断片側で付ける。
三角形の角ごとに (1,0)・(0,1)・(0,0) を uv に入れ、断片側で辺の細い線を引く。
"""

from __future__ import annotations

import math
from array import array

from stream_heartbeat.render.heart_mesh import (
    FLOATS_PER_VERTEX,
    HeartMesh,
    Vec3,
    Vessel,
    _body,
    _vertex,
    add,
    centerline,
    cross,
    dot,
    fix_winding,
    great_vessels,
    mul,
    norm,
    sub,
)

POLY_ROWS = 11
POLY_COLS = 16
# 管の周りの角の数と、制御点のあいだを何節で結ぶか
POLY_RING = 6
POLY_SPAN = 2
# 血管の先は細らせて閉じる
_TIP_TAPER = 0.6


def _uncut(_p: Vec3) -> float:
    return -1.0


def _poly_tube(vessel: Vessel) -> list[float]:
    centers, lengths = centerline(vessel.points, per_span=POLY_SPAN)
    total = max(lengths[-1], 1e-6)
    count = len(centers)
    tangents = [
        norm(sub(centers[min(count - 1, k + 1)], centers[max(0, k - 1)])) for k in range(count)
    ]
    t0 = tangents[0]
    helper = (1.0, 0.0, 0.0) if abs(t0[0]) < 0.9 else (0.0, 0.0, 1.0)
    n_prev = norm(cross(t0, helper))
    frames: list[tuple[Vec3, Vec3]] = []
    for t in tangents:
        n = norm(sub(n_prev, mul(t, dot(n_prev, t))))
        frames.append((n, norm(cross(t, n))))
        n_prev = n
    r_end = vessel.end_radius if vessel.end_radius is not None else vessel.radius * 0.88
    out: list[float] = []

    def radius_at(k: int) -> float:
        u = lengths[k] / total
        flare = 1.0 + vessel.root_flare * math.exp(-lengths[k] / 0.14)
        taper = 1.0 - (1.0 - _TIP_TAPER) * u * u if vessel.open_end else 1.0
        return (vessel.radius + (r_end - vessel.radius) * u) * flare * taper

    def ring_point(k: int, r: int) -> tuple[Vec3, Vec3]:
        angle = 2.0 * math.pi * r / POLY_RING
        n, b = frames[k]
        normal = add(mul(n, math.cos(angle)), mul(b, math.sin(angle)))
        return add(centers[k], mul(normal, radius_at(k))), normal

    def path(k: int) -> float:
        return min(1.0, (vessel.path_start + lengths[k]) / 3.2)

    def put(pos: Vec3, normal: Vec3, k: int) -> None:
        _vertex(out, pos, normal, vessel.region, 0.0, path(k), 0.0, 0.0, -1.0)

    for k in range(count - 1):
        for r in range(POLY_RING):
            p00, n00 = ring_point(k, r)
            p01, n01 = ring_point(k, r + 1)
            p10, n10 = ring_point(k + 1, r)
            p11, n11 = ring_point(k + 1, r + 1)
            put(p00, n00, k)
            put(p10, n10, k + 1)
            put(p11, n11, k + 1)
            put(p00, n00, k)
            put(p11, n11, k + 1)
            put(p01, n01, k)
    # 先は平らな六角の蓋でふさぐ
    last = count - 1
    end_t = tangents[last]
    for r in range(POLY_RING):
        p0, _n0 = ring_point(last, r)
        p1, _n1 = ring_point(last, r + 1)
        put(centers[last], end_t, last)
        put(p0, end_t, last)
        put(p1, end_t, last)
    return out


def _mark_corners(data: list[float]) -> None:
    """三角形の角ごとに (1,0)・(0,1)・(0,0) を uv へ入れる（断片側で辺を見つける）。"""
    stride = FLOATS_PER_VERTEX
    corners = ((1.0, 0.0), (0.0, 1.0), (0.0, 0.0))
    for start in range(0, len(data), stride * 3):
        for k, (u, v) in enumerate(corners):
            at = start + k * stride + 9
            data[at] = u
            data[at + 1] = v


def build_poly_mesh() -> HeartMesh:
    data = _body(POLY_ROWS, POLY_COLS, _uncut)
    tube_start = len(data) // FLOATS_PER_VERTEX
    for vessel in great_vessels():
        data += _poly_tube(vessel)
    fix_winding(data)
    _mark_corners(data)
    return HeartMesh(
        data=array("f", data), vertex_count=len(data) // FLOATS_PER_VERTEX, tube_start=tube_start
    )
