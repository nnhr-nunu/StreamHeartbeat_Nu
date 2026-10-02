"""リアル3 の断面（四腔断面）の切り口。

切る面は心臓の座標で固定。面より手前（カメラ側）の外皮と血管は断片シェーダーが捨て、
切り口そのものは平らな格子で埋める。格子の各頂点は、外皮と同じ方向の部位を持つので
頂点シェーダーの拍動で外皮と一緒に動く。切り口の模様は断片側で描く:
- 切った筋の面: 壁に沿って層をなす線維・壁の中の細い血管の切り口・淡い内膜・外の脂肪の小葉
- 腔の中: 切り口から奥へ落ちる壁と、向こう側の壁の内面（心室は肉柱の網、心房は櫛状筋）。
  張り出した切り口の縁が光の反対側へ影を落とす
- 構造: 乳頭筋と調節帯（筋の柱）、反りのある半透明の弁尖、扇に広がる腱索、大動脈弁の半月の膜
"""

from __future__ import annotations

import math

from stream_heartbeat.render.heart_mesh import (
    ORIGIN,
    Vec3,
    add,
    axial,
    dot,
    mul,
    norm,
    sub,
    surface,
    warp,
)

# 切る面: 大動脈の根元と両心室の中ほどを通り、心尖から心基部までを縦に割る
PLANE_POINT: Vec3 = (0.0, 0.0, 0.0)
PLANE_NORMAL: Vec3 = norm((0.576, 0.0, 1.0))
# 面の中の座標軸。s は患者の左（左室側）、t は心臓の長軸の上向き
PLANE_S: Vec3 = norm((1.0, 0.0, -0.576))
PLANE_T: Vec3 = (0.0, 1.0, 0.0)

_S_RANGE = (-1.15, 1.15)
_T_RANGE = (-1.35, 0.95)
# 外形の少し外まで切り口を伸ばし、外皮との継ぎ目に隙間を作らない
_RIM_MARGIN = 0.02


def plane_side(p: Vec3) -> float:
    """面からの符号付き距離。正がカメラ側（捨てる側）。"""
    return dot(sub(p, PLANE_POINT), PLANE_NORMAL)


def plane_point(s: float, t: float) -> Vec3:
    return add(add(PLANE_POINT, mul(PLANE_S, s)), mul(PLANE_T, t))


def inside_depth(p: Vec3) -> tuple[float, float]:
    """外皮までの深さ（中が正）と、外皮と同じ部位。形を絞る前の座標で測る。"""
    offset = sub(p, ORIGIN)
    dist = math.sqrt(dot(offset, offset))
    if dist < 1e-6:
        return 1.0, 0.0
    radius, region, _fat = surface(mul(offset, 1.0 / dist))
    return radius - dist, region


def build_section_cap(step: float) -> list[float]:
    """切り口の格子。頂点は位置・法線・部位・深さ・軸位置・面内座標・断面印。"""
    s0, s1 = _S_RANGE
    t0, t1 = _T_RANGE
    cols = int(math.ceil((s1 - s0) / step))
    rows = int(math.ceil((t1 - t0) / step))
    grid: list[list[tuple[Vec3, float, float, float, float]]] = []
    for i in range(rows + 1):
        t = t0 + (t1 - t0) * i / rows
        row = []
        for j in range(cols + 1):
            s = s0 + (s1 - s0) * j / cols
            p = plane_point(s, t)
            depth, region = inside_depth(p)
            row.append((warp(p), region, depth, s, t))
        grid.append(row)

    normal = PLANE_NORMAL
    out: list[float] = []

    def emit(i: int, j: int) -> None:
        pos, region, depth, s, t = grid[i][j]
        out.extend(pos)
        out.extend(normal)
        out.append(region)
        out.append(depth)
        out.append(axial(pos[1]))
        out.append(s)
        out.append(t)
        out.append(1.0)
        out.append(0.0)
        out.append(0.0)
        out.append(1.0)
        out.extend((0.0, 0.0))

    for i in range(rows):
        for j in range(cols):
            corners = (grid[i][j], grid[i + 1][j], grid[i][j + 1], grid[i + 1][j + 1])
            if max(c[2] for c in corners) < -_RIM_MARGIN:
                continue
            emit(i, j)
            emit(i + 1, j)
            emit(i + 1, j + 1)
            emit(i, j)
            emit(i + 1, j + 1)
            emit(i, j + 1)
    return out


def outline_rows(step: float = 0.05) -> list[tuple[float, float, float]]:
    """各高さ t での切り口の左右端。配置を決めるための確認用。"""
    rows = []
    t = _T_RANGE[0]
    while t <= _T_RANGE[1]:
        inside = [
            s
            for k in range(int((_S_RANGE[1] - _S_RANGE[0]) / 0.01) + 1)
            for s in (_S_RANGE[0] + 0.01 * k,)
            if inside_depth(plane_point(s, t))[0] > 0.0
        ]
        if inside:
            rows.append((t, min(inside), max(inside)))
        t += step
    return rows


# ---------------------------------------------------------------- 切り口の配置（面内座標 s, t）
# 腔は傾けた卵形: 中心・半径・傾き（度）・先細り（正で下すぼまり）
CAVITIES: dict[str, tuple[tuple[float, float], tuple[float, float], float, float]] = {
    "LV": ((0.30, -0.30), (0.25, 0.56), -8.0, 0.32),
    "RV": ((-0.37, -0.12), (0.31, 0.46), 10.0, 0.30),
    "LA": ((0.37, 0.45), (0.30, 0.26), -6.0, -0.10),
    "RA": ((-0.40, 0.42), (0.28, 0.26), 6.0, -0.10),
}
# 大動脈の根元: 両心房のあいだで切り口の上端へ抜ける管腔。底に大動脈弁
AORTA_ROOT = ((0.01, 0.64), (0.00, 1.00), 0.105)
SEPTUM = 0.13
AORTA_WALL = 0.07
ATRIAL_SEPTUM = 0.05
# 弁輪の線維の結び目（房と室の境目の左右）
ANNULUS = [(0.18, 0.21), (0.66, 0.20), (-0.66, 0.23), (-0.18, 0.21)]
ANNULUS_RADIUS = 0.035
# 弁: 付け根 2 点・閉じた先端 2 点・開いた先端 2 点
VALVES: dict[str, tuple[tuple[float, float], ...]] = {
    "MITRAL": (
        (0.18, 0.21),
        (0.66, 0.20),
        (0.41, 0.10),
        (0.43, 0.10),
        (0.26, -0.14),
        (0.58, -0.10),
    ),
    "TRICUSPID": (
        (-0.66, 0.23),
        (-0.18, 0.21),
        (-0.43, 0.12),
        (-0.41, 0.12),
        (-0.60, -0.08),
        (-0.24, -0.12),
    ),
    "AORTIC": (
        (-0.10, 0.60),
        (0.11, 0.60),
        (-0.005, 0.68),
        (0.015, 0.68),
        (-0.09, 0.80),
        (0.10, 0.80),
    ),
}
# 乳頭筋: 根元・先端・根元の太さ・先端の太さ
PAPILLARY: dict[str, tuple[tuple[float, float], tuple[float, float], float, float]] = {
    "LV_LATERAL": ((0.52, -0.60), (0.48, -0.24), 0.075, 0.034),
    "LV_SEPTAL": ((0.16, -0.66), (0.24, -0.30), 0.065, 0.030),
    "RV_ANTERIOR": ((-0.58, -0.42), (-0.52, -0.12), 0.060, 0.028),
}
MODERATOR_BAND = ((-0.13, -0.40), (-0.56, -0.33), 0.022)


def _vec(values: tuple[float, ...]) -> str:
    body_text = ", ".join(f"{v:.5f}" for v in values)
    return f"vec{len(values)}({body_text})"


def _constants() -> str:
    lines = [
        f"const vec3 SEC_S = {_vec(PLANE_S)};",
        f"const vec3 SEC_T = {_vec(PLANE_T)};",
    ]
    for name, (center, radii, tilt, taper) in CAVITIES.items():
        lines.append(f"const vec4 {name}_CAV = {_vec((*center, *radii))};")
        lines.append(f"const vec2 {name}_SHAPE = {_vec((math.radians(tilt), taper))};")
    (a, b, r) = AORTA_ROOT
    lines.append(f"const vec2 AO_A = {_vec(a)};")
    lines.append(f"const vec2 AO_B = {_vec(b)};")
    lines.append(f"const float AO_R = {r:.5f};")
    lines.append(f"const float SEPTUM = {SEPTUM:.5f};")
    lines.append(f"const float AO_WALL = {AORTA_WALL:.5f};")
    lines.append(f"const float ATRIAL_SEPTUM = {ATRIAL_SEPTUM:.5f};")
    for k, point in enumerate(ANNULUS):
        lines.append(f"const vec2 ANNULUS{k} = {_vec(point)};")
    lines.append(f"const float ANNULUS_R = {ANNULUS_RADIUS:.5f};")
    for name, points in VALVES.items():
        for label, point in zip(("A1", "A2", "C1", "C2", "O1", "O2"), points):
            lines.append(f"const vec2 {name}_{label} = {_vec(point)};")
    for name, (base, tip, rb, rt) in PAPILLARY.items():
        lines.append(f"const vec2 {name}_BASE = {_vec(base)};")
        lines.append(f"const vec2 {name}_TIP = {_vec(tip)};")
        lines.append(f"const vec2 {name}_R = {_vec((rb, rt))};")
    (ma, mb, mr) = MODERATOR_BAND
    lines.append(f"const vec2 MOD_A = {_vec(ma)};")
    lines.append(f"const vec2 MOD_B = {_vec(mb)};")
    lines.append(f"const float MOD_R = {mr:.5f};")
    return "\n".join(lines) + "\n"


SECTION_AXES_GLSL = f"const vec3 SEC_S = {_vec(PLANE_S)};\nconst vec3 SEC_T = {_vec(PLANE_T)};\n"

_SECTION_FUNCTIONS = """
// 無影灯の向き（照明と同じ）
const vec3 KEY_LIGHT = vec3(-0.31088, 0.75500, 0.57735);
float gSq;
float gOpenAV;
float gOpenAo;

vec2 rot2(vec2 p, float a) {
    float c = cos(a);
    float s = sin(a);
    return vec2(c * p.x + s * p.y, -s * p.x + c * p.y);
}
float sdOval(vec2 p, vec4 o, vec2 shape, vec2 scale) {
    vec2 q = rot2(p - o.xy, shape.x);
    vec2 r = o.zw * scale;
    float ty = clamp(q.y / r.y, -1.0, 1.0);
    float rx = r.x * (1.0 + shape.y * ty);
    return (length(q / vec2(rx, r.y)) - 1.0) * min(rx, r.y);
}
float sdCapsule(vec2 p, vec2 a, vec2 b, float r) {
    vec2 pa = p - a;
    vec2 ba = b - a;
    float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    return length(pa - ba * h) - r;
}
float smin(float a, float b, float k) {
    float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
    return mix(b, a, h) - k * h * (1.0 - h);
}

// 細胞状の模様。x はいちばん近い点まで、y は 2 番目との差（小さいほど細胞の境目）
vec2 cells(vec2 p, float seed) {
    vec2 g = floor(p);
    vec2 f = fract(p);
    float d1 = 8.0;
    float d2 = 8.0;
    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 o = vec2(float(i), float(j));
            vec2 h = vec2(hash3(vec3(g + o, seed)), hash3(vec3(g + o, seed + 7.3)));
            vec2 r = o + 0.15 + 0.7 * h - f;
            float d = dot(r, r);
            if (d < d1) {
                d2 = d1;
                d1 = d;
            } else if (d < d2) {
                d2 = d;
            }
        }
    }
    d1 = sqrt(d1);
    return vec2(d1, sqrt(d2) - d1);
}

// 腔の縁のでこぼこ。心室は肉柱で大きく、心房と大動脈はなめらか
float rimRough(vec2 p, float amount) {
    float n = vnoise(vec3(p * 8.0, 4.0)) - 0.5;
    float n2 = vnoise(vec3(p * 21.0, 9.0)) - 0.5;
    return (n * 0.020 + n2 * 0.010) * amount;
}

// 血の入る空間の距離（中が負）。室は縮むと細り、房は溜めて膨らむ
float cavityField(vec2 p, out float ventricle, out float atrium, out float aorta) {
    float lv = sdOval(p, LV_CAV, LV_SHAPE, vec2(1.0 - 0.30 * gSq, 1.0 - 0.07 * gSq));
    float rv = sdOval(p, RV_CAV, RV_SHAPE, vec2(1.0 - 0.24 * gSq, 1.0 - 0.05 * gSq));
    // 心尖寄りほど肉柱でざらつく
    float apexward = 1.0 - smoothstep(-0.45, 0.05, p.y);
    lv += rimRough(p, 0.5 + apexward);
    rv += rimRough(p + 3.1, 0.6 + apexward);
    float atr = 1.0 + 0.07 * gSq - 0.04 * uFill;
    float la = sdOval(p, LA_CAV, LA_SHAPE, vec2(atr)) + rimRough(p + 7.7, 0.25);
    float ra = sdOval(p, RA_CAV, RA_SHAPE, vec2(atr)) + rimRough(p + 5.3, 0.35);
    float ao = sdCapsule(p, AO_A, AO_B, AO_R * (1.0 + 0.10 * uEject));
    float left = smin(lv, la, 0.07);
    float right = smin(rv, ra, 0.07);
    right = max(right, -(lv - SEPTUM));
    right = max(right, -(la - ATRIAL_SEPTUM));
    left = max(left, -(ao - AO_WALL));
    right = max(right, -(ao - AO_WALL));
    float cav = min(min(left, right), ao);
    // 弁輪の線維の結び目は腔へ少し張り出す
    cav = max(cav, -(length(p - ANNULUS0) - ANNULUS_R));
    cav = max(cav, -(length(p - ANNULUS1) - ANNULUS_R));
    cav = max(cav, -(length(p - ANNULUS2) - ANNULUS_R));
    cav = max(cav, -(length(p - ANNULUS3) - ANNULUS_R));
    float v = min(lv, rv);
    float a = min(la, ra);
    ventricle = step(v, min(a, ao));
    atrium = step(a, min(v, ao));
    aorta = step(ao, min(v, a));
    return cav;
}

// 腔の中の構造（乳頭筋・弁尖・腱索・調節帯）。
// best.xy は軸からのずれ（半径で割った値）、best.z は種類（0: 筋 / 1: 弁尖 / 2: 腱索）、
// best.w は根元 0 から先 1 までの位置
void takeCone(vec2 p, vec2 a, vec2 b, float ra, float rb, float kind, float u0, float u1,
              inout float bestD, inout vec4 best) {
    vec2 pa = p - a;
    vec2 ba = b - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
    vec2 off = pa - ba * h;
    float r = mix(ra, rb, h);
    float d = length(off) - r;
    if (d < bestD) {
        bestD = d;
        // ずれは「向き」も持たせる（光の側の縁を明るくするため）
        best = vec4(off / max(r, 1e-4), kind, mix(u0, u1, h));
    }
}
vec2 bezier(vec2 a, vec2 m, vec2 b, float u) {
    return mix(mix(a, m, u), mix(m, b, u), u);
}
// 弁尖: 付け根から先へ、反りのある膜。先の縁は結節で少し厚い。
// 返す値は先の点（腱索を付ける所）。half は膜の半ばの点
vec2 takeLeaflet(vec2 p, vec2 root, vec2 tip, float bow, float thick,
                 inout float bestD, inout vec4 best, out vec2 half) {
    vec2 dir = tip - root;
    vec2 side = normalize(vec2(-dir.y, dir.x));
    vec2 ctrl = mix(root, tip, 0.5) + side * bow;
    vec2 prev = root;
    for (int i = 1; i <= 5; i++) {
        float u = float(i) / 5.0;
        vec2 cur = bezier(root, ctrl, tip, u);
        float u0 = u - 0.2;
        float r0 = thick * mix(1.0, 0.62, u0) + thick * 0.35 * smoothstep(0.75, 1.0, u0);
        float r1 = thick * mix(1.0, 0.62, u) + thick * 0.35 * smoothstep(0.75, 1.0, u);
        takeCone(p, prev, cur, r0, r1, 1.0, u0, u, bestD, best);
        prev = cur;
    }
    half = bezier(root, ctrl, tip, 0.55);
    return tip;
}
// 腱索: 乳頭筋の先から弁尖の先と半ばへ、細い白い糸が扇に広がる
void takeChordae(vec2 p, vec2 from, vec2 half, vec2 tip, float seed,
                 inout float bestD, inout vec4 best) {
    for (int i = 0; i < 5; i++) {
        float u = float(i) / 4.0;
        vec2 to = mix(half, tip, u) + vec2(0.0, 0.006 * sin(seed + float(i) * 2.1));
        // 根元は束ねて少し太く、先は細い
        vec2 split = mix(from, to, 0.18);
        takeCone(p, from, split, 0.0055, 0.0045, 2.0, 0.0, 0.18, bestD, best);
        takeCone(p, split, to, 0.0034, 0.0024, 2.0, 0.18, 1.0, bestD, best);
    }
}
float structures(vec2 p, out vec4 best) {
    float bestD = 1.0;
    best = vec4(0.0);
    vec2 lvC = LV_CAV.xy;
    vec2 rvC = RV_CAV.xy;
    // 乳頭筋は縮むと腔の中心へ寄って太る
    vec2 lvLatTip = mix(LV_LATERAL_TIP, lvC, 0.22 * gSq);
    vec2 lvSepTip = mix(LV_SEPTAL_TIP, lvC, 0.22 * gSq);
    vec2 rvTip = mix(RV_ANTERIOR_TIP, rvC, 0.18 * gSq);
    float fat = 1.0 + 0.18 * gSq;
    takeCone(p, LV_LATERAL_BASE, lvLatTip, LV_LATERAL_R.x * fat, LV_LATERAL_R.y * fat,
             0.0, 0.0, 1.0, bestD, best);
    takeCone(p, LV_SEPTAL_BASE, lvSepTip, LV_SEPTAL_R.x * fat, LV_SEPTAL_R.y * fat,
             0.0, 0.0, 1.0, bestD, best);
    takeCone(p, RV_ANTERIOR_BASE, rvTip, RV_ANTERIOR_R.x * fat, RV_ANTERIOR_R.y * fat,
             0.0, 0.0, 1.0, bestD, best);
    // 調節帯は真ん中がわずかに細い筋の橋
    vec2 modB = mix(MOD_B, rvC, 0.1 * gSq);
    vec2 modM = mix(MOD_A, modB, 0.5) + vec2(0.0, -0.012);
    takeCone(p, MOD_A, modM, MOD_R * 1.15, MOD_R * 0.85, 0.0, 0.0, 0.5, bestD, best);
    takeCone(p, modM, modB, MOD_R * 0.85, MOD_R * 1.05, 0.0, 0.5, 1.0, bestD, best);

    // 房室弁: 閉じると心房側へふくらみ、開くと心室の壁へ寄って反る
    vec2 half;
    vec2 tip;
    float bowM = mix(0.035, -0.045, gOpenAV);
    tip = takeLeaflet(p, MITRAL_A1, mix(MITRAL_C1, MITRAL_O1, gOpenAV), -bowM, 0.0125,
                      bestD, best, half);
    takeChordae(p, lvSepTip, half, tip, 1.0, bestD, best);
    tip = takeLeaflet(p, MITRAL_A2, mix(MITRAL_C2, MITRAL_O2, gOpenAV), bowM, 0.011,
                      bestD, best, half);
    takeChordae(p, lvLatTip, half, tip, 2.0, bestD, best);
    float bowT = mix(0.03, -0.04, gOpenAV);
    tip = takeLeaflet(p, TRICUSPID_A1, mix(TRICUSPID_C1, TRICUSPID_O1, gOpenAV), -bowT, 0.011,
                      bestD, best, half);
    takeChordae(p, rvTip, half, tip, 3.0, bestD, best);
    tip = takeLeaflet(p, TRICUSPID_A2, mix(TRICUSPID_C2, TRICUSPID_O2, gOpenAV), bowT, 0.011,
                      bestD, best, half);
    takeChordae(p, rvTip, half, tip, 4.0, bestD, best);
    // 大動脈弁: 閉じると 2 枚の半月の膜が椀の形に合わさり、開くと壁へ寄る
    float bowA = mix(-0.03, 0.012, gOpenAo);
    takeLeaflet(p, AORTIC_A1, mix(AORTIC_C1, AORTIC_O1, gOpenAo), bowA, 0.009,
                bestD, best, half);
    takeLeaflet(p, AORTIC_A2, mix(AORTIC_C2, AORTIC_O2, gOpenAo), -bowA, 0.009,
                bestD, best, half);
    return bestD;
}

// 腔の奥（向こう側の壁の内面）の凹凸の高さ 0〜1。
// 心室は肉柱の網（長軸に沿って伸びる）、心房は櫛状筋（平行な畝）、大動脈はなめらか。
// 細い赤い筋がうねって群がると血管の束のようで気味悪く見えるので、筋は太く低くなだらかにし、
// 細かい二重の網は薄く、心房の畝はまばらで浅くする
float floorHeight(vec2 p, float ventricle, float atrium) {
    vec2 w = p + 0.04 * vec2(vnoise(vec3(p * 5.0, 1.0)), vnoise(vec3(p * 5.0, 6.0)));
    vec2 c = cells(w * vec2(5.0, 2.4), 3.0);
    // 太さのむらのある筋の網。高さも場所ごとに違う
    float thick = 0.22 + 0.20 * vnoise(vec3(w * 6.0, 8.0));
    float net = (1.0 - smoothstep(0.0, thick, c.y)) * (0.5 + 0.2 * vnoise(vec3(w * 11.0, 3.0)));
    vec2 c2 = cells(w * vec2(13.0, 6.0), 11.0);
    net = max(net, 0.12 * (1.0 - smoothstep(0.02, 0.20, c2.y)));
    // 心房の櫛状筋はゆるく波打つ浅い畝
    vec2 cw = w + 0.04 * vec2(vnoise(vec3(w * 7.0, 2.0)), vnoise(vec3(w * 7.0, 9.0)));
    float comb = 0.5 + 0.5 * sin(cw.x * 30.0 + cw.y * 6.0 + 4.0 * vnoise(vec3(cw * 3.0, 4.0)));
    comb = smoothstep(0.25, 1.0, comb) * (0.4 + 0.6 * vnoise(vec3(cw * 6.0, 5.0)));
    return ventricle * net + atrium * comb * 0.42 + 0.10 * vnoise(vec3(w * 20.0, 6.0));
}

// 切り口の色・法線・艶。p は面内座標、depth は外皮までの深さ
void sectionSurface(vec2 p, float depth, vec3 N, vec3 S, vec3 T,
                    out vec3 albedo, out vec3 normal, out float gloss) {
    gSq = uSqueeze;
    gOpenAV = 1.0 - smoothstep(0.02, 0.30, uSqueeze);
    gOpenAo = smoothstep(0.08, 0.45, uEject);

    float ventricle;
    float atrium;
    float aorta;
    float cav = cavityField(p, ventricle, atrium, aorta);
    float e = 0.004;
    float dv;
    float da;
    float dao;
    vec2 grad = vec2(
        cavityField(p + vec2(e, 0.0), dv, da, dao) - cavityField(p - vec2(e, 0.0), dv, da, dao),
        cavityField(p + vec2(0.0, e), dv, da, dao) - cavityField(p - vec2(0.0, e), dv, da, dao)
    ) / (2.0 * e);
    vec2 g = grad / max(length(grad), 1e-4);

    // ---- 切った筋の面
    // 線維は壁に沿って層をなす（腔からの距離に沿った縞）。ゆがませて生の組織のむらにする
    vec2 w = p + 0.03 * vec2(fbm(vec3(p * 5.0, 2.0)), fbm(vec3(p * 5.0, 8.0)));
    float layer = fbm(vec3(cav * 55.0 + 3.0 * fbm(vec3(w * 3.0, 4.0)), w.x * 2.0, w.y * 2.0));
    float fiber = vnoise(vec3(cav * 160.0, w * 9.0));
    float grain = vnoise(vec3(w * 70.0, 3.0));
    float broad = fbm(vec3(p * 2.5, 11.0));
    vec3 deep = vec3(0.42, 0.04, 0.06);
    vec3 mid = vec3(0.66, 0.10, 0.10);
    vec3 bright = vec3(0.80, 0.21, 0.17);
    vec3 muscle = mix(deep, mid, smoothstep(0.25, 0.60, layer) * 0.85 + 0.15);
    muscle = mix(muscle, bright, smoothstep(0.62, 0.88, layer) * 0.5);
    muscle *= 0.90 + 0.10 * fiber + 0.06 * (grain - 0.5);
    muscle *= 0.92 + 0.16 * broad;
    // 内膜の下は少し明るい赤、壁の真ん中は暗い（血の滲み）
    muscle = mix(muscle, vec3(0.78, 0.22, 0.20), (1.0 - smoothstep(0.0, 0.05, cav)) * 0.35);
    // 壁の中を走る細い血管の切り口（暗い点と淡い縁）
    vec2 vc = cells(w * 26.0, 21.0);
    float vesselPick = step(0.82, hash3(vec3(floor(w * 26.0), 5.0)));
    float hole = (1.0 - smoothstep(0.035, 0.07, vc.x)) * vesselPick * smoothstep(0.02, 0.05, cav);
    float holeRim = (smoothstep(0.03, 0.06, vc.x) - smoothstep(0.07, 0.11, vc.x)) * vesselPick;
    muscle = mix(muscle, vec3(0.86, 0.55, 0.50), holeRim * 0.35 * smoothstep(0.02, 0.05, cav));
    muscle = mix(muscle, vec3(0.20, 0.02, 0.03), hole * 0.85);
    // 内膜は薄く淡い膜（白く抜けすぎない）
    float endo = 1.0 - smoothstep(0.0, 0.009, cav);
    muscle = mix(muscle, vec3(0.90, 0.66, 0.62), endo * 0.55);

    // 外膜の脂肪。房室の溝と心尖で厚く、小葉のつぶつぶ
    float groove = exp(-pow((p.y - 0.20) / 0.13, 2.0)) + 0.6 * exp(-pow((p.y + 0.95) / 0.18, 2.0));
    float fatThick = 0.010 + 0.075 * groove * (0.55 + 0.9 * fbm(vec3(p * 6.0, 9.0)));
    float fatMask = 1.0 - smoothstep(fatThick - 0.010, fatThick + 0.004, depth);
    fatMask *= smoothstep(0.02, 0.2, groove + 0.04);
    vec2 lob = cells(w * 34.0, 31.0);
    vec3 fatColor = mix(vec3(0.95, 0.72, 0.30), vec3(0.99, 0.88, 0.56),
                        smoothstep(0.0, 0.5, lob.x));
    fatColor *= 0.86 + 0.16 * smoothstep(0.0, 0.12, lob.y);
    muscle = mix(muscle, fatColor, fatMask);
    // 心外膜は濡れた薄い膜
    float epi = 1.0 - smoothstep(0.0, 0.010, depth);
    muscle = mix(muscle, vec3(0.90, 0.66, 0.60), epi * 0.45);
    // 弁輪の線維（淡い黄みの白）
    float ring = 0.0;
    ring = max(ring, 1.0 - smoothstep(ANNULUS_R * 0.4, ANNULUS_R * 1.25, length(p - ANNULUS0)));
    ring = max(ring, 1.0 - smoothstep(ANNULUS_R * 0.4, ANNULUS_R * 1.25, length(p - ANNULUS1)));
    ring = max(ring, 1.0 - smoothstep(ANNULUS_R * 0.4, ANNULUS_R * 1.25, length(p - ANNULUS2)));
    ring = max(ring, 1.0 - smoothstep(ANNULUS_R * 0.4, ANNULUS_R * 1.25, length(p - ANNULUS3)));
    muscle = mix(muscle, vec3(0.92, 0.80, 0.68), ring * 0.55);
    // 大動脈の壁は白っぽい弾性の層
    float aoWall = 1.0 - smoothstep(0.0, AO_WALL * 0.9,
                                    sdCapsule(p, AO_A, AO_B, AO_R * (1.0 + 0.10 * uEject)));
    muscle = mix(muscle, vec3(0.90, 0.72, 0.66) * (0.9 + 0.15 * fiber), aoWall * 0.7);

    // 切り口は濡れて緩くうねる。縁は丸く落ちて厚みが見える
    float broadT = fbm(vec3(p * 2.5, 17.0));
    vec3 wallNormal = N + S * ((broad - 0.5) * 0.45 + (fiber - 0.5) * 0.10)
                        + T * ((broadT - 0.5) * 0.45 + (grain - 0.5) * 0.06);
    float lip = 1.0 - smoothstep(0.0, 0.016, cav);
    wallNormal -= (S * g.x + T * g.y) * lip * 0.9;
    vec2 outward = normalize(p - vec2(0.0, -0.25));
    float edge = 1.0 - smoothstep(0.0, 0.022, depth);
    wallNormal += (S * outward.x + T * outward.y) * edge * 0.9;
    wallNormal = normalize(wallNormal);

    // ---- 腔の中。手前は切り口から奥へ落ちる壁、その先は向こう側の壁の内面
    float inside = -cav;
    vec2 toLight = normalize(vec2(dot(KEY_LIGHT, S), dot(KEY_LIGHT, T)) + vec2(1e-4));
    // 落ちる壁: 腔の中心を向く急な面。肉柱が奥へ縦に流れる
    float drop = 1.0 - smoothstep(0.0, 0.05, inside);
    float hFloor = floorHeight(p, ventricle, atrium);
    float hx = floorHeight(p + vec2(0.006, 0.0), ventricle, atrium) - hFloor;
    float hy = floorHeight(p + vec2(0.0, 0.006), ventricle, atrium) - hFloor;
    // 凹凸の陰影は控えめに（照り返しの筋が細い血管のように光らない）
    vec3 floorNormal = normalize(N - (S * hx + T * hy) * 3.8 * (1.0 - aorta));
    vec3 dropNormal = normalize(N * 0.45 - (S * g.x + T * g.y) * 0.9);
    vec3 bowlNormal = normalize(mix(floorNormal, dropNormal, drop));
    // 筋と谷の色の差も小さく、くすんだ赤にまとめる
    vec3 ridge = mix(vec3(0.56, 0.14, 0.13), vec3(0.64, 0.20, 0.18), hFloor);
    vec3 crevice = vec3(0.40, 0.08, 0.09);
    vec3 back = mix(crevice, ridge, smoothstep(0.0, 0.8, hFloor));
    back = mix(back, vec3(0.62, 0.30, 0.30), aorta * 0.7);
    back = mix(back, mix(vec3(0.38, 0.05, 0.07), vec3(0.62, 0.14, 0.13), fiber), drop * 0.8);
    // 切り口の縁は張り出して、光の側の縁の下へ影を落とす
    float d1s;
    float d2s;
    float d3s;
    float caster = cavityField(p + toLight * 0.08, d1s, d2s, d3s);
    float shadow = smoothstep(-0.03, 0.02, caster) * (1.0 - drop * 0.6);
    float occl = mix(0.80, 1.0, smoothstep(0.0, 0.6, hFloor));
    occl *= 1.0 - 0.30 * smoothstep(0.05, 0.3, inside);
    float shade = mix(1.0, 0.32, shadow) * occl;
    // 奥は遠いので少し冷たく沈む
    back = mix(back, back * vec3(0.80, 0.78, 0.95), smoothstep(0.04, 0.25, inside));

    vec4 st;
    float sd = structures(p, st);
    float structMask = (1.0 - smoothstep(-0.0015, 0.0015, sd)) * step(0.0, inside + 0.01);
    // 構造の足元に落ちる影（光と反対へずらして柔らかく）
    vec4 st2;
    float sdShadow = structures(p + toLight * 0.022, st2);
    shade *= mix(0.55, 1.0, smoothstep(-0.004, 0.02, sdShadow) + structMask);
    vec2 off = st.xy;
    float ratio = min(length(off), 1.0);
    vec3 cyl = normalize((S * off.x + T * off.y) + N * sqrt(max(0.0, 1.0 - ratio * ratio)));
    float isLeaf = step(0.5, st.z) * (1.0 - step(1.5, st.z));
    float isChord = step(1.5, st.z);
    float isMuscle = 1.0 - isLeaf - isChord;
    // 乳頭筋・調節帯: 長さ方向に筋の筋（すじ）が走る赤い柱
    float stri = vnoise(vec3(st.w * 26.0, off.x * 2.5, 3.0));
    vec3 muscleStruct = mix(vec3(0.56, 0.08, 0.09), vec3(0.80, 0.22, 0.18), 0.35 + 0.5 * stri);
    muscleStruct *= 0.75 + 0.25 * smoothstep(0.0, 0.4, st.w);
    // 弁尖: 半透明の淡い膜。薄い真ん中は下の暗さが透け、縁と先は厚く白い
    vec3 leafColor = mix(vec3(0.94, 0.85, 0.72), vec3(0.98, 0.93, 0.84), st.w);
    float leafOpacity = 0.62 + 0.38 * ratio * ratio + 0.2 * smoothstep(0.8, 1.0, st.w);
    vec3 leaf = mix(back * shade, leafColor, clamp(leafOpacity, 0.0, 1.0));
    // 腱索: 濡れて光る細い白い糸
    vec3 chordColor = vec3(0.97, 0.95, 0.92);
    vec3 structColor = muscleStruct * isMuscle + leaf * isLeaf + chordColor * isChord;

    float inCav = smoothstep(-0.002, 0.002, inside);
    albedo = mix(muscle, back * shade, inCav);
    normal = normalize(mix(wallNormal, bowlNormal, inCav));
    gloss = mix(1.15, 0.45 * (1.0 - shadow * 0.6), inCav);
    albedo = mix(albedo, structColor, structMask);
    normal = normalize(mix(normal, cyl, structMask));
    gloss = mix(gloss, mix(1.0, 1.5, isLeaf + isChord), structMask);
}
"""

SECTION_GLSL = _constants() + _SECTION_FUNCTIONS
