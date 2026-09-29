"""心耳のパーツ。本体の半径の関数では張り出しを表せないので、別に作って足す。

芯線は原点からの向きと本体の表面からの高さで決め、表面に沿わせる。
頂点の「心耳らしさ」は根元 0 から先 1 で、頂点シェーダーが心耳だけ別に動かすのに使う。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from stream_heartbeat.render.heart_mesh import (
    ORIGIN,
    REGION_RA,
    Vec3,
    _smooth01,
    _vertex,
    add,
    axial,
    centerline,
    cross,
    dot,
    mul,
    norm,
    sub,
    surface,
    warp,
)


@dataclass(frozen=True)
class Auricle:
    """心耳のパーツ。芯線は原点からの向きと本体の表面からの高さで決め、表面に沿わせる
    （根元は房の中に埋まる）。太さ・平たさ（表面に垂直な向き）・縁のひだ。"""

    anchors: list[tuple[Vec3, float]]
    region: float
    root_radius: float
    swell: float
    flat: float
    frill: float


# 右心耳: 右房の前上から大動脈の根元を右前から覆う、幅の広い三角の耳。
# 左心耳は正面からは左の縁に先が少しのぞく程度で、このパーツで足すと表面に貼り付けた
# 別の塊（フタ）に見えるので載せない（表面すれすれまで沈めても黒いかけらに見えた）
AURICLE_PARTS: list[Auricle] = [
    Auricle(
        [
            ((-0.80, 0.45, 0.02), -0.08),
            ((-0.76, 0.46, 0.30), 0.02),
            ((-0.62, 0.44, 0.55), 0.03),
            ((-0.50, 0.42, 0.70), 0.02),
        ],
        REGION_RA,
        0.085,
        0.095,
        0.36,
        0.12,
    ),
]


def auricle_path(part: Auricle) -> list[Vec3]:
    """向きと高さから、心耳の芯線の点を本体の表面の上に置く。"""
    points: list[Vec3] = []
    for direction, lift in part.anchors:
        unit = norm(direction)
        radius, _region, _fat = surface(unit)
        points.append(add(ORIGIN, mul(unit, radius + lift)))
    return points


def auricle_lobe(part: Auricle, rings: int = 28, ring: int = 24) -> list[float]:
    """心耳 1 つ分の頂点。心耳らしさは根元 0 から先 1。"""
    centers, lengths = centerline(auricle_path(part), per_span=10)
    total = lengths[-1]
    count = len(centers)
    steps = rings
    samples = [min(count - 1, round(k * (count - 1) / steps)) for k in range(steps + 1)]
    tangents: list[Vec3] = []
    for k in samples:
        tangents.append(norm(sub(centers[min(count - 1, k + 1)], centers[max(0, k - 1)])))
    # 断面の平たい向きは、心臓の表面（原点から外）に沿わせる
    grid: list[list[Vec3]] = []
    for idx, k in enumerate(samples):
        u = lengths[k] / total
        t = tangents[idx]
        out_dir = norm(sub(centers[k], ORIGIN))
        side_dir = norm(cross(t, out_dir))
        up_dir = norm(cross(side_dir, t))
        swell = math.sin(math.pi * min(1.0, u * 1.15)) ** 0.7
        base = part.root_radius + part.swell * swell * (1.0 - 0.55 * u)
        tip_close = math.sqrt(max(0.0, 1.0 - max(0.0, (u - 0.86) / 0.14) ** 2))
        row: list[Vec3] = []
        for r in range(ring):
            a = 2.0 * math.pi * r / ring
            # 縁のひだ（先へ行くほど深い）と、平たい断面
            ruffle = math.sin(3.0 * a + 5.0 * u) * abs(math.cos(a))
            frill = 1.0 + (part.frill + part.frill * u) * ruffle
            radius = base * frill * tip_close
            offset = add(
                mul(side_dir, math.cos(a) * radius), mul(up_dir, math.sin(a) * radius * part.flat)
            )
            row.append(add(centers[k], offset))
        grid.append(row)
    tip = add(centers[samples[-1]], mul(tangents[-1], 0.02))
    grid.append([tip] * ring)
    rows = len(grid) - 1

    normals: list[list[Vec3]] = []
    for i in range(rows + 1):
        row_n: list[Vec3] = []
        for j in range(ring):
            ahead = grid[min(rows, i + 1)][j]
            behind = grid[max(0, i - 1)][j]
            left = grid[i][(j - 1) % ring]
            right = grid[i][(j + 1) % ring]
            n = norm(cross(sub(right, left), sub(ahead, behind)))
            center = centers[samples[min(i, steps)]]
            if dot(n, sub(grid[i][j], center)) < 0.0:
                n = mul(n, -1.0)
            if i == rows:
                n = tangents[-1]
            row_n.append(n)
        normals.append(row_n)

    out: list[float] = []

    def emit(i: int, j: int) -> None:
        u = min(1.0, i / steps)
        pos = warp(grid[i][j % ring])
        _vertex(
            out,
            pos,
            normals[i][j % ring],
            part.region,
            0.15 * (1.0 - u),
            axial(pos[1]),
            u,
            j / ring,
            -1.0,
            # 表面から出る所は付け根と同じくなじませる（くっきりした境目を出さない）
            joint=1.0 - _smooth01(u / 0.4),
            auricle=_smooth01(u / 0.8),
        )

    for i in range(rows):
        for j in range(ring):
            emit(i, j)
            emit(i + 1, j)
            emit(i + 1, j + 1)
            emit(i, j)
            emit(i + 1, j + 1)
            emit(i, j + 1)
    return out
