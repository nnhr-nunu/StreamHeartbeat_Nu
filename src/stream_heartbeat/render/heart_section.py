"""リアル2 の断面（四腔断面）の切り口。

切る面は心臓の座標で固定。面より手前（カメラ側）の外皮と血管は断片シェーダーが捨て、
切り口そのものは平らな格子で埋める。格子の各頂点は、外皮と同じ方向の部位を持つので
頂点シェーダーの拍動で外皮と一緒に動く。切り口の模様（筋・腔・弁・乳頭筋）は断片側で描く。
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

// 血の入る空間の距離（中が負）。室は縮むと細り、房は溜めて膨らむ
float cavityField(vec2 p, out float ventricle, out float atrium, out float aorta) {
    float lv = sdOval(p, LV_CAV, LV_SHAPE, vec2(1.0 - 0.30 * gSq, 1.0 - 0.07 * gSq));
    float rv = sdOval(p, RV_CAV, RV_SHAPE, vec2(1.0 - 0.24 * gSq, 1.0 - 0.05 * gSq));
    float atr = 1.0 + 0.07 * gSq - 0.04 * uFill;
    float la = sdOval(p, LA_CAV, LA_SHAPE, vec2(atr));
    float ra = sdOval(p, RA_CAV, RA_SHAPE, vec2(atr));
    float ao = sdCapsule(p, AO_A, AO_B, AO_R * (1.0 + 0.10 * uEject));
    float left = smin(lv, la, 0.07);
    float right = smin(rv, ra, 0.07);
    right = max(right, -(lv - SEPTUM));
    right = max(right, -(la - ATRIAL_SEPTUM));
    left = max(left, -(ao - AO_WALL));
    right = max(right, -(ao - AO_WALL));
    float cav = min(min(left, right), ao);
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

// 腔の中の構造（乳頭筋・弁尖・腱索）。best.xy は軸からのずれ（半径で割った値）、best.z は種類
void takeCone(vec2 p, vec2 a, vec2 b, float ra, float rb, float kind,
              inout float bestD, inout vec3 best) {
    vec2 pa = p - a;
    vec2 ba = b - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
    vec2 off = pa - ba * h;
    float r = mix(ra, rb, h);
    float d = length(off) - r;
    if (d < bestD) {
        bestD = d;
        best = vec3(off / max(r, 1e-4), kind);
    }
}
void takeLeaflet(vec2 p, vec2 root, vec2 tip, float bow, inout float bestD, inout vec3 best,
                 out vec2 mid) {
    vec2 dir = tip - root;
    vec2 side = normalize(vec2(-dir.y, dir.x));
    mid = mix(root, tip, 0.5) + side * bow;
    takeCone(p, root, mid, 0.016, 0.012, 1.0, bestD, best);
    takeCone(p, mid, tip, 0.012, 0.008, 1.0, bestD, best);
}
void takeChordae(vec2 p, vec2 from, vec2 mid, vec2 tip, inout float bestD, inout vec3 best) {
    takeCone(p, from, mix(mid, tip, 0.35), 0.006, 0.004, 2.0, bestD, best);
    takeCone(p, from, mix(mid, tip, 0.7), 0.006, 0.004, 2.0, bestD, best);
    takeCone(p, from, tip, 0.006, 0.004, 2.0, bestD, best);
}
float structures(vec2 p, out vec3 best) {
    float bestD = 1.0;
    best = vec3(0.0);
    vec2 lvC = LV_CAV.xy;
    vec2 rvC = RV_CAV.xy;
    // 乳頭筋は縮むと腔の中心へ寄る
    vec2 lvLatTip = mix(LV_LATERAL_TIP, lvC, 0.22 * gSq);
    vec2 lvSepTip = mix(LV_SEPTAL_TIP, lvC, 0.22 * gSq);
    vec2 rvTip = mix(RV_ANTERIOR_TIP, rvC, 0.18 * gSq);
    takeCone(p, LV_LATERAL_BASE, lvLatTip, LV_LATERAL_R.x, LV_LATERAL_R.y, 0.0, bestD, best);
    takeCone(p, LV_SEPTAL_BASE, lvSepTip, LV_SEPTAL_R.x, LV_SEPTAL_R.y, 0.0, bestD, best);
    takeCone(p, RV_ANTERIOR_BASE, rvTip, RV_ANTERIOR_R.x, RV_ANTERIOR_R.y, 0.0, bestD, best);
    takeCone(p, MOD_A, mix(MOD_B, rvC, 0.1 * gSq), MOD_R, MOD_R * 0.8, 0.0, bestD, best);

    vec2 mid;
    vec2 tip;
    tip = mix(MITRAL_C1, MITRAL_O1, gOpenAV);
    takeLeaflet(p, MITRAL_A1, tip, -0.025, bestD, best, mid);
    takeChordae(p, lvSepTip, mid, tip, bestD, best);
    tip = mix(MITRAL_C2, MITRAL_O2, gOpenAV);
    takeLeaflet(p, MITRAL_A2, tip, 0.025, bestD, best, mid);
    takeChordae(p, lvLatTip, mid, tip, bestD, best);
    tip = mix(TRICUSPID_C1, TRICUSPID_O1, gOpenAV);
    takeLeaflet(p, TRICUSPID_A1, tip, -0.02, bestD, best, mid);
    takeChordae(p, rvTip, mid, tip, bestD, best);
    tip = mix(TRICUSPID_C2, TRICUSPID_O2, gOpenAV);
    takeLeaflet(p, TRICUSPID_A2, tip, 0.02, bestD, best, mid);
    takeChordae(p, rvTip, mid, tip, bestD, best);
    tip = mix(AORTIC_C1, AORTIC_O1, gOpenAo);
    takeLeaflet(p, AORTIC_A1, tip, 0.015, bestD, best, mid);
    tip = mix(AORTIC_C2, AORTIC_O2, gOpenAo);
    takeLeaflet(p, AORTIC_A2, tip, -0.015, bestD, best, mid);
    return bestD;
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

    // ---- 切った筋の面。腔の縁に沿って層が走り、内膜は白く、外は脂肪と心外膜
    float fib = fbm(vec3(cav * 60.0, p.x * 3.0 + p.y * 2.0, p.y * 3.0));
    float grain = vnoise(vec3(p * 45.0, 3.0));
    float streak = fbm(vec3(p.x * 18.0 + cav * 70.0, p.y * 18.0, 5.0));
    float broad = fbm(vec3(p * 3.0, 11.0));
    vec3 muscle = mix(vec3(0.50, 0.03, 0.04), vec3(0.86, 0.10, 0.07), smoothstep(0.25, 0.75, fib));
    muscle *= 0.92 + 0.12 * grain;
    muscle = mix(muscle, vec3(0.93, 0.45, 0.40), smoothstep(0.70, 0.86, streak) * 0.22);
    float endo = 1.0 - smoothstep(0.0, 0.012, cav);
    muscle = mix(muscle, vec3(0.96, 0.84, 0.82), endo * 0.9);

    float groove = exp(-pow((p.y - 0.20) / 0.13, 2.0)) + 0.6 * exp(-pow((p.y + 0.95) / 0.18, 2.0));
    float fatThick = 0.012 + 0.07 * groove * (0.6 + 0.8 * fbm(vec3(p * 6.0, 9.0)));
    float fatMask = 1.0 - smoothstep(fatThick - 0.012, fatThick, depth);
    float lobule = fbm(vec3(p * 38.0, 1.0));
    vec3 fatColor = mix(vec3(0.96, 0.76, 0.34), vec3(0.99, 0.86, 0.52), lobule);
    muscle = mix(muscle, fatColor, fatMask * smoothstep(0.02, 0.2, groove + 0.05));
    float epi = 1.0 - smoothstep(0.0, 0.012, depth);
    muscle = mix(muscle, vec3(0.92, 0.70, 0.66), epi * 0.6);

    // 切り口は濡れて緩くうねる。細かい筋で光が散る
    float broadT = fbm(vec3(p * 3.0, 17.0));
    vec3 wallNormal = normalize(N + S * ((broad - 0.5) * 0.9 + (fib - 0.5) * 0.25)
                                + T * ((broadT - 0.5) * 0.9 + (grain - 0.5) * 0.08));

    // ---- 腔の奥の壁。肉柱の筋、房は櫛状筋。縁の真下は影
    float inside = -cav;
    float bowl = clamp(inside / 0.22, 0.0, 1.0);
    vec2 q = p + vec2(fbm(vec3(p * 5.0, 2.0)), fbm(vec3(p * 5.0, 7.0))) * 0.08;
    float trab = ridged(vec3(q.x * 16.0, q.y * 4.5, 1.0));
    float comb = ridged(vec3(q.x * 4.0, q.y * 18.0, 4.0));
    float relief = mix(trab, comb, atrium);
    vec3 back = mix(vec3(0.26, 0.02, 0.04), vec3(0.74, 0.14, 0.12), smoothstep(0.45, 0.95, relief));
    back = mix(back, vec3(0.72, 0.40, 0.40), aorta * 0.6);
    // 光は左上から。切り口の縁が張り出して、光の側の縁の下へ影を落とす
    vec2 toLight = normalize(vec2(dot(KEY_LIGHT, S), dot(KEY_LIGHT, T)) + vec2(1e-4));
    float d1s;
    float d2s;
    float d3s;
    float caster = cavityField(p + toLight * 0.07, d1s, d2s, d3s);
    float shadow = smoothstep(-0.02, 0.02, caster);
    float shade = mix(1.0, 0.35, shadow) * (1.0 - 0.45 * bowl);
    shade *= mix(0.55, 1.0, smoothstep(0.0, 0.025, inside));
    // 奥の壁の側面は腔の中心を向く（すり鉢）
    float slope = 1.6 * (1.0 - smoothstep(0.0, 0.16, inside));
    vec3 bowlNormal = normalize(N * 0.7 - (S * g.x + T * g.y) * slope
                                + S * (relief - 0.5) * 0.6 * (1.0 - aorta));

    vec3 st;
    float sd = structures(p, st);
    float structMask = (1.0 - smoothstep(-0.002, 0.002, sd)) * step(0.0, inside + 0.01);
    // 構造の足元に落ちる影
    shade *= mix(0.55, 1.0, smoothstep(0.0, 0.035, sd));
    vec2 off = st.xy;
    float ratio = min(length(off), 1.0);
    vec3 cyl = normalize((S * off.x + T * off.y) + N * sqrt(max(0.0, 1.0 - ratio * ratio)));
    vec3 structColor = vec3(0.88, 0.50, 0.46);
    structColor = mix(structColor, vec3(0.97, 0.86, 0.76), step(0.5, st.z));
    structColor = mix(structColor, vec3(0.99, 0.95, 0.92), step(1.5, st.z));
    structColor *= 0.85 + 0.25 * vnoise(vec3(p * 60.0, 2.0));

    float inCav = smoothstep(-0.003, 0.003, inside);
    albedo = mix(muscle, back * shade, inCav);
    normal = normalize(mix(wallNormal, bowlNormal, inCav));
    gloss = mix(1.3, 0.55 * (1.0 - shadow * 0.7), inCav);
    albedo = mix(albedo, structColor, structMask);
    normal = normalize(mix(normal, cyl, structMask));
    gloss = mix(gloss, 1.4, structMask);
}
"""

SECTION_GLSL = _constants() + _SECTION_FUNCTIONS
