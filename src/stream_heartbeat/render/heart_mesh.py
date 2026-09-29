"""立体心臓の形を数式から起こす。

4 つの腔と 2 つの心耳を楕円体の滑らかな合成で作り、腔どうしの境目に溝（冠状溝・室間溝）を刻む。
心尖は細く絞り、後ろ（横隔膜側）は平たくする。
大血管は制御点を滑らかに通る管。大動脈は弓を描いて背中側へ降り、弓の上から首・頭へ 3 本が昇る。
座標は心臓の長軸が -Y（尖が下）の姿勢。体の上下は ANATOMY_ROLL_DEG だけ傾いた向き。
頂点ごとに位置・法線・部位・脂肪量・軸位置・UV・断面（切り口の印と切る面からの距離）・
付け根のなじみ・透かし・心耳らしさ（心耳の先ほど 1。心耳だけ別に動かす）を持つ。
左右の心耳は本体の半径の関数では張り出しを表せないので、別の小さなパーツとして最後に足す。
変形は頂点シェーダーが行う。
"""

from __future__ import annotations

import math
from array import array
from collections.abc import Callable
from dataclasses import dataclass

REGION_LV = 0.0
REGION_RV = 1.0
REGION_LA = 2.0
REGION_RA = 3.0
REGION_ARTERY = 4.0
REGION_VEIN = 5.0
REGION_LUMEN = 6.0

FLOATS_PER_VERTEX = 17
BASE_Y = 0.36
APEX_Y = -1.12
# 画面上で体の上下に合わせる傾き。心臓の長軸は体の縦から左下へ倒れている
ANATOMY_ROLL_DEG = 34.0
# 管の aAxial は心臓からの道のり ÷ この長さ（拍の波が伝わる位置）
PATH_SCALE = 3.2
# 血管の付け根をなじませる幅（本体側・管側）と、開いた先を透かして消す長さ
JOINT_REACH = 0.12
JOINT_ROOT = 0.24
TIP_FADE = 0.34

Vec3 = tuple[float, float, float]
SideFn = Callable[[Vec3], float]

ORIGIN: Vec3 = (0.0, 0.2, -0.1)


@dataclass(frozen=True)
class Chamber:
    center: Vec3
    radii: Vec3
    region: float
    yaw_deg: float = 0.0
    roll_deg: float = 0.0


CHAMBERS: list[Chamber] = [
    Chamber((0.12, -0.20, -0.08), (0.60, 0.94, 0.62), REGION_LV, roll_deg=-10.0),
    Chamber((-0.20, -0.02, 0.16), (0.60, 0.74, 0.46), REGION_RV, yaw_deg=20.0, roll_deg=8.0),
    Chamber((0.18, 0.50, -0.30), (0.50, 0.40, 0.44), REGION_LA),
    Chamber((-0.36, 0.40, -0.02), (0.46, 0.44, 0.42), REGION_RA, yaw_deg=-30.0),
]
# 心耳は原点の外にあるので、半径の合成にだけ加わる。
# 左心耳は原点から見て張り出しが裏へ回り込み、折れ目ができるので載せない
_AURICLES: list[Chamber] = [
    # 右心耳: 大動脈の根元を右前から覆う
    Chamber((-0.36, 0.46, 0.34), (0.24, 0.13, 0.17), REGION_RA, yaw_deg=30.0, roll_deg=20.0),
]

_SMOOTH_K = 0.05
_GROOVE_DEPTH = 0.03
_GROOVE_WIDTH = 0.045
_FAT_WIDTH = 0.14
_LUMP_AMOUNT = 0.045
# 心耳を混ぜ切る厚み
_AURICLE_FADE = 0.22
# 心尖へ向けて横幅を絞る量と、背面を平らにする量
_APEX_TAPER = 0.30
_APEX_AXIS = (0.10, -0.06)
_BACK_PLANE_Z = -0.52
_BACK_FLATTEN = 0.55


@dataclass(frozen=True)
class HeartMesh:
    data: array
    vertex_count: int
    # これより後ろの頂点は断面の切り口。断面の見た目のときだけ描く
    section_start: int = -1
    # 血管の頂点の始まり。先を透かすので、不透明の後にもう一度描く
    tube_start: int = 0
    # 心耳のパーツの頂点の始まり（断面の切り口の後ろ）。心耳を別に動かす見た目のときだけ描く
    auricle_start: int = -1
    # 表面を這う冠動脈の頂点の始まり（心耳の後ろ、最後まで）。心耳と同じ見た目のときだけ描く
    coronary_start: int = -1

    @property
    def section_end(self) -> int:
        return self.vertex_count if self.auricle_start < 0 else self.auricle_start

    @property
    def triangle_count(self) -> int:
        return self.vertex_count // 3

    @property
    def body_vertex_count(self) -> int:
        return self.vertex_count if self.section_start < 0 else self.section_start


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def mul(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a: Vec3) -> Vec3:
    length = math.sqrt(dot(a, a))
    if length < 1e-9:
        return (0.0, 1.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


_ROLL = math.radians(ANATOMY_ROLL_DEG)
# 体の左（患者の左）・上・前を、心臓の座標で表した向き
BODY_LEFT: Vec3 = (math.cos(_ROLL), -math.sin(_ROLL), 0.0)
BODY_UP: Vec3 = (math.sin(_ROLL), math.cos(_ROLL), 0.0)
BODY_FRONT: Vec3 = (0.0, 0.0, 1.0)


def body(anchor: Vec3, left: float = 0.0, up: float = 0.0, front: float = 0.0) -> Vec3:
    """anchor から体の向きで動かした点。"""
    offset = add(add(mul(BODY_LEFT, left), mul(BODY_UP, up)), mul(BODY_FRONT, front))
    return add(anchor, offset)


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
    ox, oy, oz = _to_local(sub(ORIGIN, chamber.center), chamber)
    ax, ay, az = chamber.radii
    return (ox / ax) ** 2 + (oy / ay) ** 2 + (oz / az) ** 2 - 1.0


def _ray_ellipsoid(direction: Vec3, chamber: Chamber) -> float:
    """原点から direction へ進み、楕円体の奥側の壁に当たる距離。当たらなければ 0。"""
    ox, oy, oz = _to_local(sub(ORIGIN, chamber.center), chamber)
    dx, dy, dz = _to_local(direction, chamber)
    ax, ay, az = chamber.radii
    a = (dx / ax) ** 2 + (dy / ay) ** 2 + (dz / az) ** 2
    b = 2.0 * (dx * ox / ax**2 + dy * oy / ay**2 + dz * oz / az**2)
    c = (ox / ax) ** 2 + (oy / ay) ** 2 + (oz / az) ** 2 - 1.0
    disc = b * b - 4.0 * a * c
    if disc <= 0.0:
        return 0.0
    return max(0.0, (-b + math.sqrt(disc)) / (2.0 * a))


def _hash(ix: int, iy: int, iz: int) -> float:
    n = (ix * 1619 + iy * 31337 + iz * 6971) & 0x7FFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0x7FFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def value_noise(p: Vec3) -> float:
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
    a = value_noise(mul(p, 2.4))
    b = value_noise(add(mul(p, 5.1), (3.7, 1.3, 8.2)))
    c = value_noise(add(mul(p, 9.7), (1.1, 6.3, 2.9)))
    return (a - 0.5) * 0.6 + (b - 0.5) * 0.3 + (c - 0.5) * 0.15


def _chord(direction: Vec3, chamber: Chamber) -> tuple[float, float]:
    """原点から direction への線が楕円体を通る奥側の距離と、中を通る長さ。"""
    ox, oy, oz = _to_local(sub(ORIGIN, chamber.center), chamber)
    dx, dy, dz = _to_local(direction, chamber)
    ax, ay, az = chamber.radii
    a = (dx / ax) ** 2 + (dy / ay) ** 2 + (dz / az) ** 2
    b = 2.0 * (dx * ox / ax**2 + dy * oy / ay**2 + dz * oz / az**2)
    c = (ox / ax) ** 2 + (oy / ay) ** 2 + (oz / az) ** 2 - 1.0
    disc = b * b - 4.0 * a * c
    if disc <= 0.0:
        return 0.0, 0.0
    return max(0.0, (-b + math.sqrt(disc)) / (2.0 * a)), math.sqrt(disc) / a


def surface(direction: Vec3) -> tuple[float, float, float]:
    """方向ごとの半径・部位・脂肪量。形を絞る前の値。"""
    radii = [(_ray_ellipsoid(direction, chamber), chamber.region) for chamber in CHAMBERS]
    radii.sort(key=lambda item: item[0], reverse=True)
    top = radii[0][0]
    merged = _SMOOTH_K * math.log(sum(math.exp((r - top) / _SMOOTH_K) for r, _ in radii)) + top
    region = radii[0][1]
    # 心耳は外から被さる。中を通る長さが短い縁ほど薄く混ぜ、段差を作らない。
    # 部位（色と拍動）は下の腔のまま。部位を切り替えると境目が三角形のぎざぎざになる
    for auricle in _AURICLES:
        far, chord = _chord(direction, auricle)
        if far > merged:
            merged += (far - merged) * _smooth01(chord / _AURICLE_FADE)
    gap = radii[0][0] - radii[1][0]
    groove = _GROOVE_DEPTH * math.exp(-((gap / _GROOVE_WIDTH) ** 2))
    fat = math.exp(-((gap / _FAT_WIDTH) ** 2))
    probe = add(ORIGIN, mul(direction, merged))
    lumpy = merged * (1.0 + _LUMP_AMOUNT * _lumps(probe))
    # 溝は脂肪で少し埋まる
    lumpy += 0.012 * fat * (0.5 + 0.5 * value_noise(mul(probe, 7.0)))
    return lumpy - groove, region, fat


def _smooth01(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def warp(p: Vec3) -> Vec3:
    """楕円体の合成を心臓らしく崩す。心尖を細く、背面を平たく。"""
    x, y, z = p
    depth = max(0.0, min(1.0, (-0.25 - y) / 0.95))
    pinch = 1.0 - _APEX_TAPER * depth**1.6
    ax, az = _APEX_AXIS
    x = ax + (x - ax) * pinch
    z = az + (z - az) * pinch
    if z < _BACK_PLANE_Z:
        z = _BACK_PLANE_Z + (z - _BACK_PLANE_Z) * _BACK_FLATTEN
    return (x, y, z)


def axial(y: float) -> float:
    return max(0.0, min(1.0, (BASE_Y - y) / (BASE_Y - APEX_Y)))


def _vertex(
    out: list[float],
    pos: Vec3,
    normal: Vec3,
    region: float,
    fat: float,
    ax: float,
    u: float,
    v: float,
    side: float,
    cap: float = 0.0,
    joint: float = 0.0,
    fade: float = 1.0,
    auricle: float = 0.0,
    coronary: float = 0.0,
) -> None:
    out.extend(pos)
    out.extend(normal)
    out.append(region)
    out.append(fat)
    out.append(ax)
    out.append(u)
    out.append(v)
    out.append(cap)
    out.append(side)
    out.append(joint)
    out.append(fade)
    out.append(auricle)
    out.append(coronary)


def _no_contact(_p: Vec3) -> float:
    return 0.0


def _body(rows: int, cols: int, side: SideFn, contact: SideFn = _no_contact) -> list[float]:
    grid: list[list[tuple[Vec3, float, float, float]]] = []
    for i in range(rows + 1):
        theta = math.pi * i / rows
        row: list[tuple[Vec3, float, float, float]] = []
        for j in range(cols):
            phi = 2.0 * math.pi * j / cols
            direction = (
                math.sin(theta) * math.cos(phi),
                math.cos(theta),
                math.sin(theta) * math.sin(phi),
            )
            radius, region, fat = surface(direction)
            raw = add(ORIGIN, mul(direction, radius))
            row.append((warp(raw), region, fat, side(raw)))
        grid.append(row)

    normals: list[list[Vec3]] = []
    for i in range(rows + 1):
        row_n: list[Vec3] = []
        for j in range(cols):
            up = grid[max(0, i - 1)][j][0]
            down = grid[min(rows, i + 1)][j][0]
            left = grid[i][(j - 1) % cols][0]
            right = grid[i][(j + 1) % cols][0]
            n = norm(cross(sub(right, left), sub(down, up)))
            outward = sub(grid[i][j][0], ORIGIN)
            if dot(n, outward) < 0.0:
                n = mul(n, -1.0)
            if i == 0 or i == rows:
                n = (0.0, 1.0 if i == 0 else -1.0, 0.0)
            row_n.append(n)
        normals.append(row_n)

    joints = [[contact(grid[i][j][0]) for j in range(cols)] for i in range(rows + 1)]
    out: list[float] = []

    def emit(i: int, j: int) -> None:
        pos, region, fat, cut = grid[i][j % cols]
        _vertex(
            out,
            pos,
            normals[i][j % cols],
            region,
            fat,
            axial(pos[1]),
            j / cols,
            i / rows,
            cut,
            joint=joints[i][j % cols],
        )

    for i in range(rows):
        for j in range(cols):
            emit(i, j)
            emit(i + 1, j)
            emit(i + 1, j + 1)
            emit(i, j)
            emit(i + 1, j + 1)
            emit(i, j + 1)
    return out


def _catmull(p0: Vec3, p1: Vec3, p2: Vec3, p3: Vec3, u: float) -> Vec3:
    u2 = u * u
    u3 = u2 * u
    return tuple(
        0.5
        * (
            2.0 * p1[k]
            + (-p0[k] + p2[k]) * u
            + (2.0 * p0[k] - 5.0 * p1[k] + 4.0 * p2[k] - p3[k]) * u2
            + (-p0[k] + 3.0 * p1[k] - 3.0 * p2[k] + p3[k]) * u3
        )
        for k in range(3)
    )  # type: ignore[return-value]


def centerline(points: list[Vec3], per_span: int = 12) -> tuple[list[Vec3], list[float]]:
    """制御点をすべて通る滑らかな芯線と、始点からの道のり。"""
    ext = [points[0], *points, points[-1]]
    centers: list[Vec3] = []
    for i in range(1, len(ext) - 2):
        for k in range(per_span):
            centers.append(_catmull(ext[i - 1], ext[i], ext[i + 1], ext[i + 2], k / per_span))
    centers.append(points[-1])
    lengths = [0.0]
    for a, b in zip(centers[:-1], centers[1:]):
        lengths.append(lengths[-1] + math.sqrt(dot(sub(b, a), sub(b, a))))
    return centers, lengths


def path_at(points: list[Vec3], target: Vec3) -> float:
    """芯線上で target に一番近い所までの道のり。枝の付け根に使う。"""
    centers, lengths = centerline(points)
    best = min(
        range(len(centers)), key=lambda k: dot(sub(centers[k], target), sub(centers[k], target))
    )
    return lengths[best]


@dataclass(frozen=True)
class Vessel:
    points: list[Vec3]
    radius: float
    region: float
    end_radius: float | None = None
    root_flare: float = 0.35
    path_start: float = 0.0
    open_end: bool = True
    ring: int = 24
    # 断面で心臓と一緒に切るか。首へ昇る枝や静脈は切らずに残す
    cut: bool = True


def _uncut(_p: Vec3) -> float:
    return -1.0


def _tube(vessel: Vessel, side: SideFn) -> list[float]:
    if not vessel.cut:
        side = _uncut
    centers, lengths = centerline(vessel.points)
    total = max(lengths[-1], 1e-6)
    count = len(centers)
    tangents: list[Vec3] = []
    for k in range(count):
        ahead = centers[min(count - 1, k + 1)]
        behind = centers[max(0, k - 1)]
        tangents.append(norm(sub(ahead, behind)))

    frames: list[tuple[Vec3, Vec3]] = []
    t0 = tangents[0]
    helper = (1.0, 0.0, 0.0) if abs(t0[0]) < 0.9 else (0.0, 0.0, 1.0)
    n_prev = norm(cross(t0, helper))
    for t in tangents:
        n = norm(sub(n_prev, mul(t, dot(n_prev, t))))
        b = norm(cross(t, n))
        frames.append((n, b))
        n_prev = n

    r_end = vessel.end_radius if vessel.end_radius is not None else vessel.radius * 0.88
    fade_len = min(TIP_FADE, total * 0.6)

    def fade_at(k: int) -> float:
        # 開いた先は途切れさせず、細りながら透けて消える
        if not vessel.open_end:
            return 1.0
        return _smooth01((total - lengths[k]) / fade_len)

    def joint_at(k: int) -> float:
        return 1.0 - _smooth01(lengths[k] / JOINT_ROOT)

    def radius_at(k: int) -> float:
        u = lengths[k] / total
        flare = 1.0 + vessel.root_flare * math.exp(-lengths[k] / 0.14)
        thin = 0.78 + 0.22 * fade_at(k)
        return (vessel.radius + (r_end - vessel.radius) * u) * flare * thin

    def path(k: int) -> float:
        return min(1.0, (vessel.path_start + lengths[k]) / PATH_SCALE)

    ring = vessel.ring

    def vertex(k: int, r: int) -> tuple[Vec3, Vec3]:
        angle = 2.0 * math.pi * r / ring
        n, b = frames[k]
        normal = add(mul(n, math.cos(angle)), mul(b, math.sin(angle)))
        return add(centers[k], mul(normal, radius_at(k))), normal

    out: list[float] = []
    region = vessel.region

    def put(
        pos: Vec3, normal: Vec3, reg: float, ax: float, u: float, v: float, k: int
    ) -> None:
        _vertex(
            out, pos, normal, reg, 0.0, ax, u, v, side(pos), joint=joint_at(k), fade=fade_at(k)
        )

    for k in range(count - 1):
        u0 = lengths[k] / total
        u1 = lengths[k + 1] / total
        for r in range(ring):
            p00, n00 = vertex(k, r)
            p01, n01 = vertex(k, r + 1)
            p10, n10 = vertex(k + 1, r)
            p11, n11 = vertex(k + 1, r + 1)
            v0 = r / ring
            v1 = (r + 1) / ring
            put(p00, n00, region, path(k), u0, v0, k)
            put(p10, n10, region, path(k + 1), u1, v0, k + 1)
            put(p11, n11, region, path(k + 1), u1, v1, k + 1)
            put(p00, n00, region, path(k), u0, v0, k)
            put(p11, n11, region, path(k + 1), u1, v1, k + 1)
            put(p01, n01, region, path(k), u0, v1, k)

    last = count - 1
    if not vessel.open_end:
        # 枝分かれの所は丸く閉じる（枝の付け根に埋もれる）
        n_end, b_end = frames[last]
        end_t = tangents[last]
        tip = path(last)
        steps = 6

        def dome(level: int, r: int) -> tuple[Vec3, Vec3]:
            lat = 0.5 * math.pi * level / steps
            angle = 2.0 * math.pi * r / ring
            around = add(mul(n_end, math.cos(angle)), mul(b_end, math.sin(angle)))
            normal = norm(add(mul(around, math.cos(lat)), mul(end_t, math.sin(lat))))
            return add(centers[last], mul(normal, radius_at(last))), normal

        for level in range(steps):
            for r in range(ring):
                p00, n00 = dome(level, r)
                p01, n01 = dome(level, r + 1)
                p10, n10 = dome(level + 1, r)
                p11, n11 = dome(level + 1, r + 1)
                put(p00, n00, region, tip, 1.0, 0.0, last)
                put(p10, n10, region, tip, 1.0, 0.0, last)
                put(p11, n11, region, tip, 1.0, 1.0, last)
                put(p00, n00, region, tip, 1.0, 0.0, last)
                put(p11, n11, region, tip, 1.0, 1.0, last)
                put(p01, n01, region, tip, 1.0, 1.0, last)
        return out
    end_center = centers[last]
    end_t = tangents[last]
    n_end, b_end = frames[last]
    outer = radius_at(last)
    inner = outer * 0.72
    tip = path(last)
    for r in range(ring):
        a0 = 2.0 * math.pi * r / ring
        a1 = 2.0 * math.pi * (r + 1) / ring
        d0 = add(mul(n_end, math.cos(a0)), mul(b_end, math.sin(a0)))
        d1 = add(mul(n_end, math.cos(a1)), mul(b_end, math.sin(a1)))
        o0 = add(end_center, mul(d0, outer))
        o1 = add(end_center, mul(d1, outer))
        i0 = add(end_center, mul(d0, inner))
        i1 = add(end_center, mul(d1, inner))
        put(o0, end_t, region, tip, 1.0, 0.0, last)
        put(o1, end_t, region, tip, 1.0, 1.0, last)
        put(i1, end_t, region, tip, 1.0, 1.0, last)
        put(o0, end_t, region, tip, 1.0, 0.0, last)
        put(i1, end_t, region, tip, 1.0, 1.0, last)
        put(i0, end_t, region, tip, 1.0, 0.0, last)
        sunk = sub(end_center, mul(end_t, inner * 0.35))
        put(i0, end_t, REGION_LUMEN, tip, 0.0, 0.0, last)
        put(i1, end_t, REGION_LUMEN, tip, 1.0, 1.0, last)
        put(sunk, end_t, REGION_LUMEN, tip, 0.5, 0.5, last)
    return out


def great_vessels() -> list[Vessel]:
    """大動脈・首への 3 枝・肺動脈・大静脈・肺静脈。"""
    # 大動脈: 左室から昇り、右前から左後ろへ弓を描いて背中側を降りる
    asc_top = (0.04, 1.00, -0.04)
    arch_top = body(asc_top, left=0.20, up=0.16, front=-0.22)
    arch_back = body(arch_top, left=0.24, up=-0.08, front=-0.26)
    aorta_points = [
        (0.02, 0.18, 0.00),
        (0.00, 0.62, 0.03),
        asc_top,
        arch_top,
        arch_back,
        body(arch_back, left=0.04, up=-0.50, front=-0.06),
        body(arch_back, left=0.02, up=-1.35, front=-0.04),
    ]
    aorta = Vessel(aorta_points, 0.20, REGION_ARTERY, end_radius=0.15)

    # 弓の上から首・頭へ: 腕頭動脈・左総頸動脈・左鎖骨下動脈
    def branch(root: Vec3, left: float, up: float, radius: float) -> Vessel:
        mid = body(root, left=left * 0.35, up=up * 0.45)
        end = body(root, left=left, up=up)
        return Vessel(
            [root, mid, end],
            radius,
            REGION_ARTERY,
            end_radius=radius * 0.9,
            root_flare=0.55,
            path_start=path_at(aorta_points, root),
            ring=18,
            cut=False,
        )

    brachio_root = body(asc_top, left=0.05, up=0.10, front=-0.06)
    carotid_root = body(arch_top, left=-0.03, up=0.02, front=0.02)
    subclavian_root = body(arch_top, left=0.14, up=-0.01, front=-0.08)
    branches = [
        branch(brachio_root, -0.14, 0.60, 0.078),
        branch(carotid_root, 0.02, 0.58, 0.056),
        branch(subclavian_root, 0.22, 0.50, 0.060),
    ]

    # 肺動脈幹: 右室の出口から大動脈の前を昇り、弓の下で左右に分かれる
    pa_fork = (0.02, 0.92, 0.22)
    trunk_points = [(-0.22, 0.20, 0.34), (-0.20, 0.62, 0.42), pa_fork]
    trunk = Vessel(trunk_points, 0.165, REGION_ARTERY, end_radius=0.15, open_end=False)
    fork_path = path_at(trunk_points, pa_fork)
    left_pa = Vessel(
        [
            pa_fork,
            body(pa_fork, left=0.18, up=0.04, front=-0.18),
            body(pa_fork, left=0.34, up=-0.04, front=-0.50),
        ],
        0.13,
        REGION_ARTERY,
        end_radius=0.10,
        root_flare=0.1,
        path_start=fork_path,
    )
    right_pa = Vessel(
        [
            pa_fork,
            body(pa_fork, left=-0.12, up=-0.03, front=-0.30),
            body(pa_fork, left=-0.46, up=-0.10, front=-0.52),
        ],
        0.12,
        REGION_ARTERY,
        end_radius=0.095,
        root_flare=0.1,
        path_start=fork_path,
    )

    # 上大静脈は右房から真上へ、下大静脈は右房の後ろ下から下へ
    svc_root = (-0.40, 0.56, -0.10)
    svc = Vessel(
        [
            svc_root,
            body(svc_root, up=0.40, left=-0.02),
            body(svc_root, up=0.86, left=-0.04, front=-0.02),
        ],
        0.13,
        REGION_VEIN,
        root_flare=0.25,
        ring=20,
        cut=False,
    )
    ivc_root = (-0.42, 0.14, -0.26)
    ivc = Vessel(
        [ivc_root, body(ivc_root, up=-0.30, front=-0.04), body(ivc_root, up=-0.62, front=-0.06)],
        0.14,
        REGION_VEIN,
        root_flare=0.25,
        ring=20,
        cut=False,
    )
    # 肺静脈: 左房の後ろから左右 2 本ずつ
    pulmonary_veins = []
    for root, left in (
        ((0.40, 0.62, -0.56), 0.36),
        ((0.44, 0.40, -0.54), 0.34),
        ((-0.02, 0.64, -0.64), -0.34),
        ((0.02, 0.42, -0.64), -0.32),
    ):
        pulmonary_veins.append(
            Vessel(
                [
                    root,
                    body(root, left=left * 0.5, front=-0.08),
                    body(root, left=left, front=-0.18),
                ],
                0.055,
                REGION_VEIN,
                root_flare=0.4,
                ring=14,
                cut=False,
            )
        )
    return [aorta, *branches, trunk, left_pa, right_pa, svc, ivc, *pulmonary_veins]


def body_contact(vessels: list[Vessel]) -> SideFn:
    """本体の点が、心臓から生える血管の付け根にどれだけ近いか（0〜1）。"""
    samples: list[tuple[Vec3, float]] = []
    for vessel in vessels:
        if vessel.path_start > 0.0:
            continue
        centers, lengths = centerline(vessel.points)
        for c, length in zip(centers, lengths):
            if length > JOINT_ROOT:
                break
            flare = 1.0 + vessel.root_flare * math.exp(-length / 0.14)
            samples.append((c, vessel.radius * flare))

    def contact(p: Vec3) -> float:
        gap = min(math.sqrt(dot(sub(p, c), sub(p, c))) - r for c, r in samples)
        return math.exp(-((max(0.0, gap) / JOINT_REACH) ** 2))

    return contact


def fix_winding(data: list[float], start_vertex: int = 0) -> None:
    """三角形の表が法線側を向くように頂点順を揃える。"""
    stride = FLOATS_PER_VERTEX
    tri = stride * 3
    for start in range(start_vertex * stride, len(data), tri):
        p0 = (data[start], data[start + 1], data[start + 2])
        p1 = (data[start + stride], data[start + stride + 1], data[start + stride + 2])
        p2 = (
            data[start + 2 * stride],
            data[start + 2 * stride + 1],
            data[start + 2 * stride + 2],
        )
        face = cross(sub(p1, p0), sub(p2, p0))
        n_avg = (
            data[start + 3] + data[start + stride + 3] + data[start + 2 * stride + 3],
            data[start + 4] + data[start + stride + 4] + data[start + 2 * stride + 4],
            data[start + 5] + data[start + stride + 5] + data[start + 2 * stride + 5],
        )
        if dot(face, n_avg) < 0.0:
            a = start + stride
            b = start + 2 * stride
            data[a : a + stride], data[b : b + stride] = (
                data[b : b + stride],
                data[a : a + stride],
            )


def build_heart_mesh(*, rows: int = 84, cols: int = 132, section_step: float = 0.018) -> HeartMesh:
    # 断面・心耳・冠動脈は外形の関数を使うので、ここで遅れて読み込む
    from stream_heartbeat.render.heart_auricles import AURICLE_PARTS, auricle_lobe
    from stream_heartbeat.render.heart_coronary import coronary_parts, coronary_tube
    from stream_heartbeat.render.heart_section import build_section_cap, plane_side

    for chamber in CHAMBERS:
        if origin_inside(chamber) >= 0.0:
            raise ValueError(f"原点が腔の外: {chamber.region}")
    vessels = great_vessels()
    data = _body(rows, cols, plane_side, body_contact(vessels))
    tube_start = len(data) // FLOATS_PER_VERTEX
    for vessel in vessels:
        data += _tube(vessel, plane_side)
    section_start = len(data) // FLOATS_PER_VERTEX
    data += build_section_cap(section_step)
    auricle_start = len(data) // FLOATS_PER_VERTEX
    for part in AURICLE_PARTS:
        data += auricle_lobe(part)
    coronary_start = len(data) // FLOATS_PER_VERTEX
    for vessel in coronary_parts():
        data += coronary_tube(vessel)
    fix_winding(data)
    return HeartMesh(
        data=array("f", data),
        vertex_count=len(data) // FLOATS_PER_VERTEX,
        section_start=section_start,
        tube_start=tube_start,
        auricle_start=auricle_start,
        coronary_start=coronary_start,
    )
