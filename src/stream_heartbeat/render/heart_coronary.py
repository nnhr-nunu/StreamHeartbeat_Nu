"""表面を這う冠動脈と静脈。細い管として作り、下の心室と一緒に動かす（生々しい見た目だけ）。

道筋は原点から見た向き（方位・仰角、度）で決める。幹は腔の境目の溝をたどって求め、
枝は幹の途中から決めた向きへ伸ばす。どれも表面の上に置き直し、少し蛇行させる。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from stream_heartbeat.render.heart_mesh import (
    CHAMBERS,
    ORIGIN,
    Vec3,
    _ray_ellipsoid,
    _smooth01,
    _vertex,
    add,
    axial,
    centerline,
    cross,
    mul,
    norm,
    sub,
    surface,
    warp,
)

# 頂点の印（シェーダーが色と膨らみを分ける）
ARTERY = 1.0
VEIN = 2.0
# 腔の並び（CHAMBERS の順）
_LV, _RV, _LA, _RA = 0, 1, 2, 3
# 管の断面の分割と、芯線の刻み
_RING = 8
_STEP = 0.014
# 房室の溝を走る管は、房が膨らんでも埋もれないよう心室側へ少しずらす（度）
_AV_SHIFT = 3.0

Angles = tuple[float, float]


def direction(az: float, el: float) -> Vec3:
    """方位（0 が前、+ が患者の左）と仰角（+ が上）から向き。"""
    a, e = math.radians(az), math.radians(el)
    return (math.cos(e) * math.sin(a), math.sin(e), math.cos(e) * math.cos(a))


def _gap(d: Vec3, a: int, b: int) -> float:
    return _ray_ellipsoid(d, CHAMBERS[a]) - _ray_ellipsoid(d, CHAMBERS[b])


def _root(f: Callable[[float], float], lo: float, hi: float) -> float | None:
    f_lo = f(lo)
    if f_lo * f(hi) > 0.0:
        return None
    for _ in range(36):
        mid = 0.5 * (lo + hi)
        f_mid = f(mid)
        if f_mid * f_lo > 0.0:
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def groove_by_el(a: int, b: int, els: list[float], lo: float, hi: float) -> list[Angles]:
    """仰角ごとに、腔 a と b の境目の方位を探す（縦に走る溝）。"""
    points: list[Angles] = []
    for el in els:
        az = _root(lambda x, el=el: _gap(direction(x, el), a, b), lo, hi)
        if az is not None:
            points.append((az, el))
    return points


def groove_by_az(a: int, b: int, azs: list[float], lo: float, hi: float) -> list[Angles]:
    """方位ごとに、腔 a と b の境目の仰角を探す（横に回る溝）。"""
    points: list[Angles] = []
    for az in azs:
        el = _root(lambda x, az=az: _gap(direction(az, x), a, b), lo, hi)
        if el is not None:
            points.append((az, el - _AV_SHIFT))
    return points


def _span(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [start + k * step for k in range(count + 1)]


@lru_cache(maxsize=1)
def trunks() -> dict[str, list[Angles]]:
    """溝を走る幹。前室間溝（左前下行枝）・左の房室溝（回旋枝）・右の房室溝（右冠動脈）。"""
    lad = groove_by_el(_LV, _RV, _span(18.0, -58.0, -4.0), -60.0, 100.0)
    # 溝が尽きた先は心尖を少し回り込む
    lad += [(-15.0, -66.0), (-2.0, -74.0), (12.0, -82.0)]
    lcx = groove_by_az(_LA, _LV, _span(62.0, 150.0, 8.0), -30.0, 80.0)
    rca = groove_by_az(_RA, _RV, _span(-22.0, -110.0, -8.0), -30.0, 80.0)
    return {"lad": lad, "lcx": lcx, "rca": rca}


def _along(path: list[Angles], fraction: float) -> Angles:
    """制御点の並びの途中（割合）の向き。枝の付け根に使う。"""
    x = fraction * (len(path) - 1)
    i = min(len(path) - 2, int(x))
    t = x - i
    (a0, e0), (a1, e1) = path[i], path[i + 1]
    return (a0 + (a1 - a0) * t, e0 + (e1 - e0) * t)


@dataclass(frozen=True)
class Coronary:
    """表面の管。道筋・根元と先の太さ・動脈か静脈か・蛇行の強さと位相。"""

    path: list[Angles]
    r0: float
    r1: float
    kind: float = ARTERY
    wiggle: float = 0.010
    phase: float = 0.0


@lru_cache(maxsize=1)
def coronary_parts() -> list[Coronary]:
    t = trunks()
    lad, lcx, rca = t["lad"], t["lcx"], t["rca"]

    def branch(parent: list[Angles], at: float, rest: list[Angles]) -> list[Angles]:
        return [_along(parent, at), *rest]

    # 前室間静脈は左前下行枝の左室側に沿って上り、大心静脈として左の房室溝へ回る
    aiv = [(az + 6.0, el) for az, el in lad[2:-4]][::-1]
    gcv = [(az, el - 5.0) for az, el in lcx[1:7]]
    return [
        Coronary(lad, 0.024, 0.009, wiggle=0.005, phase=0.3),
        Coronary(lcx, 0.021, 0.011, wiggle=0.004, phase=1.1),
        Coronary(rca, 0.024, 0.012, wiggle=0.004, phase=2.0),
        # 対角枝（左室の前外側へ）
        Coronary(branch(lad, 0.22, [(30.0, -14.0), (47.0, -31.0), (60.0, -50.0)]), 0.015, 0.006,
                 phase=0.7),
        Coronary(branch(lad, 0.50, [(22.0, -40.0), (36.0, -57.0), (45.0, -70.0)]), 0.013, 0.005,
                 phase=2.6),
        # 鈍縁枝（左室の側面を心尖へ）
        Coronary(branch(lcx, 0.30, [(92.0, 6.0), (97.0, -20.0), (98.0, -45.0), (95.0, -62.0)]),
                 0.015, 0.006, phase=1.9),
        Coronary(branch(lcx, 0.66, [(118.0, -14.0), (121.0, -38.0), (119.0, -56.0)]), 0.013,
                 0.004, phase=4.1),
        # 右室枝と鋭縁枝（右室の前と下の縁）
        Coronary(branch(rca, 0.28, [(-36.0, 18.0), (-26.0, 0.0), (-19.0, -16.0)]), 0.012, 0.005,
                 phase=3.3),
        Coronary(branch(rca, 0.56, [(-66.0, -12.0), (-58.0, -32.0), (-48.0, -50.0)]), 0.014,
                 0.005, phase=5.0),
        # 静脈は動脈より太く暗い
        Coronary(aiv + gcv, 0.019, 0.023, VEIN, wiggle=0.006, phase=0.9),
        Coronary([(100.0, 22.0), (105.0, -4.0), (107.0, -30.0), (104.0, -50.0)], 0.016, 0.010,
                 VEIN, phase=2.2),
        Coronary([(-62.0, 22.0), (-50.0, 5.0), (-40.0, -12.0), (-33.0, -27.0)], 0.015, 0.009,
                 VEIN, phase=4.4),
    ]


def _on_surface(point: Vec3, lift: float) -> Vec3:
    unit = norm(sub(point, ORIGIN))
    radius, _region, _fat = surface(unit)
    return add(ORIGIN, mul(unit, radius + lift))


def _resample(points: list[Vec3], step: float) -> list[Vec3]:
    centers, lengths = centerline(points, per_span=16)
    total = lengths[-1]
    count = max(2, int(total / step) + 1)
    out: list[Vec3] = []
    k = 0
    for i in range(count + 1):
        s = total * i / count
        while k < len(lengths) - 2 and lengths[k + 1] < s:
            k += 1
        span = max(lengths[k + 1] - lengths[k], 1e-9)
        t = (s - lengths[k]) / span
        out.append(add(centers[k], mul(sub(centers[k + 1], centers[k]), t)))
    return out


def _host(unit: Vec3) -> tuple[float, float]:
    """下の心室（左室 0 〜 右室 1、境目は間の値）と溝の脂肪の量。"""
    share = _smooth01(0.5 + _gap(unit, _RV, _LV) / 0.05)
    return share, surface(unit)[2]


def coronary_tube(part: Coronary) -> list[float]:
    """管 1 本分の頂点。表面から 6 割ほど出して置き、先は閉じる。"""
    rough = [_on_surface(add(ORIGIN, direction(az, el)), 0.0) for az, el in part.path]
    base = _resample(rough, _STEP)
    count = len(base)
    # 表面に沿って横へ蛇行させ、表面の上に置き直す
    centers: list[Vec3] = []
    for k, c in enumerate(base):
        u = k / (count - 1)
        ahead = base[min(count - 1, k + 1)]
        behind = base[max(0, k - 1)]
        side = norm(cross(sub(ahead, behind), sub(c, ORIGIN)))
        w = math.sin(u * 17.0 + part.phase) * 0.6 + math.sin(u * 41.0 + part.phase * 2.3) * 0.4
        # 付け根は親の管から離れない
        w *= part.wiggle * _smooth01(u * 8.0)
        radius = part.r0 + (part.r1 - part.r0) * u
        centers.append(_on_surface(add(c, mul(side, w)), radius * 0.25))

    out: list[float] = []
    rings: list[list[tuple[Vec3, Vec3]]] = []
    for k, c in enumerate(centers):
        u = k / (count - 1)
        tangent = norm(sub(centers[min(count - 1, k + 1)], centers[max(0, k - 1)]))
        outward = norm(sub(c, ORIGIN))
        side = norm(cross(tangent, outward))
        up = norm(cross(side, tangent))
        # 両端は丸く閉じる（付け根は親の管や心耳の下に隠れる）
        head = 1.0 - min(1.0, k / 3.0)
        tail = max(0.0, (u - 0.92) / 0.08)
        close = math.sqrt(max(0.0, 1.0 - head * head)) * math.sqrt(max(0.0, 1.0 - tail * tail))
        radius = (part.r0 + (part.r1 - part.r0) * u) * close
        ring: list[tuple[Vec3, Vec3]] = []
        for j in range(_RING):
            a = 2.0 * math.pi * j / _RING
            # 表面に押されて少し平たい断面
            offset = add(mul(side, math.cos(a) * radius), mul(up, math.sin(a) * radius * 0.8))
            normal = norm(add(mul(side, math.cos(a) * 0.8), mul(up, math.sin(a))))
            ring.append((warp(add(c, offset)), normal))
        rings.append(ring)

    hosts = [_host(norm(sub(c, ORIGIN))) for c in centers]

    def emit(k: int, j: int) -> None:
        pos, normal = rings[k][j % _RING]
        region, fat = hosts[k]
        _vertex(out, pos, normal, region, fat, axial(pos[1]), k / (count - 1), j / _RING, -1.0,
                coronary=part.kind)

    for k in range(count - 1):
        for j in range(_RING):
            emit(k, j)
            emit(k + 1, j)
            emit(k + 1, j + 1)
            emit(k, j)
            emit(k + 1, j + 1)
            emit(k, j + 1)
    return out
