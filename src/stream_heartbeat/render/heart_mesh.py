"""立体心臓の形を数式から起こす。

4 つの腔を楕円体の滑らかな合成で作り、腔どうしの境目に溝（冠状溝・室間溝）を刻む。
大動脈・肺動脈・上大静脈は曲線に沿った管。座標は心臓の長軸が -Y（尖が下）の姿勢。
頂点ごとに位置・法線・部位・脂肪量・軸位置・UV を持ち、変形は頂点シェーダーが行う。
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass

REGION_LV = 0.0
REGION_RV = 1.0
REGION_LA = 2.0
REGION_RA = 3.0
REGION_ARTERY = 4.0
REGION_VEIN = 5.0
REGION_LUMEN = 6.0

FLOATS_PER_VERTEX = 11
BASE_Y = 0.36
APEX_Y = -1.12

Vec3 = tuple[float, float, float]

_ORIGIN: Vec3 = (0.0, 0.2, -0.1)


@dataclass(frozen=True)
class Chamber:
    center: Vec3
    radii: Vec3
    region: float
    yaw_deg: float = 0.0
    roll_deg: float = 0.0


_CHAMBERS: list[Chamber] = [
    Chamber((0.12, -0.20, -0.08), (0.60, 0.94, 0.62), REGION_LV, roll_deg=-10.0),
    Chamber((-0.20, -0.02, 0.16), (0.60, 0.74, 0.46), REGION_RV, yaw_deg=20.0, roll_deg=8.0),
    Chamber((0.18, 0.50, -0.30), (0.50, 0.40, 0.44), REGION_LA),
    Chamber((-0.36, 0.40, -0.02), (0.46, 0.44, 0.42), REGION_RA, yaw_deg=-30.0),
]

_SMOOTH_K = 0.05
_GROOVE_DEPTH = 0.03
_GROOVE_WIDTH = 0.045
_FAT_WIDTH = 0.14
_LUMP_AMOUNT = 0.045


@dataclass(frozen=True)
class HeartMesh:
    data: array
    vertex_count: int

    @property
    def triangle_count(self) -> int:
        return self.vertex_count // 3


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec3) -> Vec3:
    length = math.sqrt(_dot(a, a))
    if length < 1e-9:
        return (0.0, 1.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


def _to_local(v: Vec3, chamber: Chamber) -> Vec3:
    """楕円体の向きを打ち消して、軸に沿った座標へ。"""
    yaw = -math.radians(chamber.yaw_deg)
    roll = -math.radians(chamber.roll_deg)
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, y, z = v
    x, z = x * cy + z * sy, -x * sy + z * cy
    cr, sr = math.cos(roll), math.sin(roll)
    x, y = x * cr - y * sr, x * sr + y * cr
    return (x, y, z)


def origin_inside(chamber: Chamber) -> float:
    """原点が楕円体の中なら負。生成の前提。"""
    ox, oy, oz = _to_local(_sub(_ORIGIN, chamber.center), chamber)
    ax, ay, az = chamber.radii
    return (ox / ax) ** 2 + (oy / ay) ** 2 + (oz / az) ** 2 - 1.0


def _ray_ellipsoid(direction: Vec3, chamber: Chamber) -> float:
    """原点から direction へ進み、楕円体の外側の壁に当たる距離。原点は楕円体の中。"""
    ox, oy, oz = _to_local(_sub(_ORIGIN, chamber.center), chamber)
    dx, dy, dz = _to_local(direction, chamber)
    ax, ay, az = chamber.radii
    a = (dx / ax) ** 2 + (dy / ay) ** 2 + (dz / az) ** 2
    b = 2.0 * (dx * ox / ax**2 + dy * oy / ay**2 + dz * oz / az**2)
    c = (ox / ax) ** 2 + (oy / ay) ** 2 + (oz / az) ** 2 - 1.0
    disc = max(0.0, b * b - 4.0 * a * c)
    return (-b + math.sqrt(disc)) / (2.0 * a)


def _hash(ix: int, iy: int, iz: int) -> float:
    n = (ix * 1619 + iy * 31337 + iz * 6971) & 0x7FFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0x7FFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _value_noise(p: Vec3) -> float:
    fx, fy, fz = (math.floor(v) for v in p)
    tx, ty, tz = p[0] - fx, p[1] - fy, p[2] - fz
    tx, ty, tz = (t * t * (3.0 - 2.0 * t) for t in (tx, ty, tz))
    ix, iy, iz = int(fx), int(fy), int(fz)

    def lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    x00 = lerp(_hash(ix, iy, iz), _hash(ix + 1, iy, iz), tx)
    x10 = lerp(_hash(ix, iy + 1, iz), _hash(ix + 1, iy + 1, iz), tx)
    x01 = lerp(_hash(ix, iy, iz + 1), _hash(ix + 1, iy, iz + 1), tx)
    x11 = lerp(_hash(ix, iy + 1, iz + 1), _hash(ix + 1, iy + 1, iz + 1), tx)
    return lerp(lerp(x00, x10, ty), lerp(x01, x11, ty), tz)


def _lumps(p: Vec3) -> float:
    a = _value_noise(_mul(p, 2.4))
    b = _value_noise(_add(_mul(p, 5.1), (3.7, 1.3, 8.2)))
    c = _value_noise(_add(_mul(p, 9.7), (1.1, 6.3, 2.9)))
    return (a - 0.5) * 0.6 + (b - 0.5) * 0.3 + (c - 0.5) * 0.15


def _surface(direction: Vec3) -> tuple[float, float, float]:
    """方向ごとの半径・部位・脂肪量。"""
    radii = [(_ray_ellipsoid(direction, chamber), chamber.region) for chamber in _CHAMBERS]
    radii.sort(key=lambda item: item[0], reverse=True)
    top = radii[0][0]
    merged = _SMOOTH_K * math.log(sum(math.exp((r - top) / _SMOOTH_K) for r, _ in radii)) + top
    gap = radii[0][0] - radii[1][0]
    groove = _GROOVE_DEPTH * math.exp(-((gap / _GROOVE_WIDTH) ** 2))
    fat = math.exp(-((gap / _FAT_WIDTH) ** 2))
    probe = _add(_ORIGIN, _mul(direction, merged))
    lumpy = merged * (1.0 + _LUMP_AMOUNT * _lumps(probe))
    # 溝は脂肪で少し埋まる
    lumpy += 0.012 * fat * (0.5 + 0.5 * _value_noise(_mul(probe, 7.0)))
    return lumpy - groove, radii[0][1], fat


def _axial(y: float) -> float:
    return max(0.0, min(1.0, (BASE_Y - y) / (BASE_Y - APEX_Y)))


def _body(rows: int, cols: int) -> list[float]:
    grid: list[list[tuple[Vec3, float, float]]] = []
    for i in range(rows + 1):
        theta = math.pi * i / rows
        row: list[tuple[Vec3, float, float]] = []
        for j in range(cols):
            phi = 2.0 * math.pi * j / cols
            direction = (
                math.sin(theta) * math.cos(phi),
                math.cos(theta),
                math.sin(theta) * math.sin(phi),
            )
            radius, region, fat = _surface(direction)
            row.append((_add(_ORIGIN, _mul(direction, radius)), region, fat))
        grid.append(row)

    normals: list[list[Vec3]] = []
    for i in range(rows + 1):
        row_n: list[Vec3] = []
        for j in range(cols):
            up = grid[max(0, i - 1)][j][0]
            down = grid[min(rows, i + 1)][j][0]
            left = grid[i][(j - 1) % cols][0]
            right = grid[i][(j + 1) % cols][0]
            n = _cross(_sub(right, left), _sub(down, up))
            n = _norm(n)
            outward = _sub(grid[i][j][0], _ORIGIN)
            if _dot(n, outward) < 0.0:
                n = _mul(n, -1.0)
            if i == 0 or i == rows:
                n = (0.0, 1.0 if i == 0 else -1.0, 0.0)
            row_n.append(n)
        normals.append(row_n)

    out: list[float] = []

    def emit(i: int, j: int) -> None:
        pos, region, fat = grid[i][j % cols]
        n = normals[i][j % cols]
        out.extend(pos)
        out.extend(n)
        out.append(region)
        out.append(fat)
        out.append(_axial(pos[1]))
        out.append(j / cols)
        out.append(i / rows)

    for i in range(rows):
        for j in range(cols):
            emit(i, j)
            emit(i + 1, j)
            emit(i + 1, j + 1)
            emit(i, j)
            emit(i + 1, j + 1)
            emit(i, j + 1)
    return out


def _bezier(p0: Vec3, p1: Vec3, p2: Vec3, p3: Vec3, u: float) -> Vec3:
    s = 1.0 - u
    return (
        s**3 * p0[0] + 3 * s * s * u * p1[0] + 3 * s * u * u * p2[0] + u**3 * p3[0],
        s**3 * p0[1] + 3 * s * s * u * p1[1] + 3 * s * u * u * p2[1] + u**3 * p3[1],
        s**3 * p0[2] + 3 * s * s * u * p1[2] + 3 * s * u * u * p2[2] + u**3 * p3[2],
    )


def _tube(
    control: tuple[Vec3, Vec3, Vec3, Vec3],
    radius: float,
    region: float,
    *,
    segments: int = 36,
    ring: int = 24,
    root_flare: float = 0.35,
) -> list[float]:
    centers: list[Vec3] = []
    tangents: list[Vec3] = []
    for k in range(segments + 1):
        u = k / segments
        centers.append(_bezier(*control, u))
        ahead = _bezier(*control, min(1.0, u + 1e-3))
        behind = _bezier(*control, max(0.0, u - 1e-3))
        tangents.append(_norm(_sub(ahead, behind)))

    frames: list[tuple[Vec3, Vec3]] = []
    t0 = tangents[0]
    helper = (1.0, 0.0, 0.0) if abs(t0[0]) < 0.9 else (0.0, 0.0, 1.0)
    n_prev = _norm(_cross(t0, helper))
    for t in tangents:
        n = _norm(_sub(n_prev, _mul(t, _dot(n_prev, t))))
        b = _norm(_cross(t, n))
        frames.append((n, b))
        n_prev = n

    def radius_at(u: float) -> float:
        return radius * (1.0 + root_flare * (1.0 - u) ** 3) * (1.0 - 0.12 * u)

    def vertex(k: int, r: int) -> tuple[Vec3, Vec3, float]:
        u = k / segments
        angle = 2.0 * math.pi * r / ring
        n, b = frames[k]
        normal = _add(_mul(n, math.cos(angle)), _mul(b, math.sin(angle)))
        pos = _add(centers[k], _mul(normal, radius_at(u)))
        return pos, normal, u

    out: list[float] = []

    def emit(pos: Vec3, normal: Vec3, reg: float, u: float, v: float) -> None:
        out.extend(pos)
        out.extend(normal)
        out.append(reg)
        out.append(0.0)
        out.append(0.0)
        out.append(u)
        out.append(v)

    for k in range(segments):
        for r in range(ring):
            p00, n00, u0 = vertex(k, r)
            p01, n01, _ = vertex(k, r + 1)
            p10, n10, u1 = vertex(k + 1, r)
            p11, n11, _ = vertex(k + 1, r + 1)
            v0 = r / ring
            v1 = (r + 1) / ring
            emit(p00, n00, region, u0, v0)
            emit(p10, n10, region, u1, v0)
            emit(p11, n11, region, u1, v1)
            emit(p00, n00, region, u0, v0)
            emit(p11, n11, region, u1, v1)
            emit(p01, n01, region, u0, v1)

    end_center = centers[segments]
    end_t = tangents[segments]
    n_end, b_end = frames[segments]
    outer = radius_at(1.0)
    inner = outer * 0.68
    for r in range(ring):
        a0 = 2.0 * math.pi * r / ring
        a1 = 2.0 * math.pi * (r + 1) / ring
        d0 = _add(_mul(n_end, math.cos(a0)), _mul(b_end, math.sin(a0)))
        d1 = _add(_mul(n_end, math.cos(a1)), _mul(b_end, math.sin(a1)))
        o0 = _add(end_center, _mul(d0, outer))
        o1 = _add(end_center, _mul(d1, outer))
        i0 = _add(end_center, _mul(d0, inner))
        i1 = _add(end_center, _mul(d1, inner))
        emit(o0, end_t, region, 1.0, 0.0)
        emit(o1, end_t, region, 1.0, 1.0)
        emit(i1, end_t, region, 1.0, 1.0)
        emit(o0, end_t, region, 1.0, 0.0)
        emit(i1, end_t, region, 1.0, 1.0)
        emit(i0, end_t, region, 1.0, 0.0)
        sunk = _sub(end_center, _mul(end_t, inner * 0.35))
        emit(i0, end_t, REGION_LUMEN, 0.0, 0.0)
        emit(i1, end_t, REGION_LUMEN, 1.0, 1.0)
        emit(sunk, end_t, REGION_LUMEN, 0.5, 0.5)
    return out


def _fix_winding(data: list[float]) -> None:
    """三角形の表が法線側を向くように頂点順を揃える。"""
    stride = FLOATS_PER_VERTEX
    tri = stride * 3
    for start in range(0, len(data), tri):
        p0 = (data[start], data[start + 1], data[start + 2])
        p1 = (data[start + stride], data[start + stride + 1], data[start + stride + 2])
        p2 = (
            data[start + 2 * stride],
            data[start + 2 * stride + 1],
            data[start + 2 * stride + 2],
        )
        face = _cross(_sub(p1, p0), _sub(p2, p0))
        n_avg = (
            data[start + 3] + data[start + stride + 3] + data[start + 2 * stride + 3],
            data[start + 4] + data[start + stride + 4] + data[start + 2 * stride + 4],
            data[start + 5] + data[start + stride + 5] + data[start + 2 * stride + 5],
        )
        if _dot(face, n_avg) < 0.0:
            a = start + stride
            b = start + 2 * stride
            data[a : a + stride], data[b : b + stride] = (
                data[b : b + stride],
                data[a : a + stride],
            )


def build_heart_mesh(*, rows: int = 84, cols: int = 132) -> HeartMesh:
    for chamber in _CHAMBERS:
        if origin_inside(chamber) >= 0.0:
            raise ValueError(f"原点が腔の外: {chamber.region}")
    data = _body(rows, cols)
    # 大動脈: 中央から立ち上がり、後ろ・患者の左へ弓を描く
    data += _tube(
        ((0.02, 0.26, 0.00), (0.00, 0.98, -0.02), (0.40, 1.30, -0.26), (0.70, 0.86, -0.50)),
        0.20,
        REGION_ARTERY,
        segments=40,
    )
    # 肺動脈幹: 右室の出口から大動脈の前を横切って左へ
    data += _tube(
        ((-0.22, 0.26, 0.34), (-0.20, 0.82, 0.42), (0.06, 1.06, 0.24), (0.40, 1.08, 0.06)),
        0.165,
        REGION_ARTERY,
        segments=32,
    )
    # 上大静脈: 右房の上からまっすぐ上へ
    data += _tube(
        ((-0.40, 0.56, -0.10), (-0.42, 0.82, -0.12), (-0.44, 1.02, -0.14), (-0.46, 1.26, -0.16)),
        0.13,
        REGION_VEIN,
        segments=18,
        root_flare=0.25,
    )
    _fix_winding(data)
    return HeartMesh(data=array("f", data), vertex_count=len(data) // FLOATS_PER_VERTEX)
