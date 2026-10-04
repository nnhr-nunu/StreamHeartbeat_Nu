"""Blender の心臓のシェーダー。頂点側でシェイプキーを混ぜ、断片側で材質を描き分ける。

材質（uMaterial）: 0 赤（リアル）・1 グラデ・2 ガラス。グラデとガラスは Blender の材質の数値に
合わせてある（グラデ: 波の色 × 2 段の陰を、縁の暗さと比べて暗い方。ガラス: 水色・屈折 1.33・
細かいでこぼこ・スタジオの映り込み）。

ほかの心臓と同じく、太い血管の切り口の手前は透けて消える（vesselFade）。左心耳は心房の収縮と
一打ちで揺れる（auricleMove。Blender のアニメではほとんど動かない）。
心臓わしづかみでは指の所が凹む。
"""

from __future__ import annotations

from stream_heartbeat.render.grip_pose import GRIP_DENT_GLSL
from stream_heartbeat.render.heart_shaders import _NOISE

MATERIAL_REAL = "real"
MATERIAL_GRADIENT = "gradient"
MATERIAL_GLASS = "glass"
MATERIALS = (MATERIAL_REAL, MATERIAL_GRADIENT, MATERIAL_GLASS)
MATERIAL_INDEX = {key: i for i, key in enumerate(MATERIALS)}

# 血管の切り口（形の座標）: 真ん中・外向き・管の太さの半分・透けていく長さ。
# 上へ伸びる血管（上大静脈・大動脈の枝）は高さでまとめて消す（TOP_FADE）
VESSEL_ENDS = (
    ((0.422, 0.350, -0.593), (0.99, 0.06, -0.09), 0.116, 0.16),  # 左肺動脈
    ((-0.120, 0.640, -0.690), (0.00, -0.79, -0.61), 0.130, 0.14),  # 右肺動脈（後ろ）
    ((-0.176, 0.978, -0.079), (0.88, 0.37, -0.30), 0.077, 0.12),  # 大動脈弓の右の枝
    ((0.384, 0.465, -0.380), (0.86, 0.48, 0.20), 0.055, 0.09),  # 肺動脈の左上の枝
    ((0.490, 0.170, -0.600), (0.90, 0.00, -0.40), 0.055, 0.09),  # 左の肺静脈
    ((0.525, 0.040, -0.625), (0.90, -0.10, -0.40), 0.055, 0.09),
    ((-0.810, 0.218, -0.594), (-0.89, -0.36, -0.29), 0.092, 0.14),  # 右の肺静脈
    ((-0.810, 0.060, -0.550), (-0.90, -0.10, -0.30), 0.050, 0.09),
    ((-0.760, -0.050, -0.530), (-0.90, -0.20, -0.30), 0.045, 0.08),
    ((-0.658, 0.463, -0.514), (-0.24, 0.11, -0.96), 0.061, 0.10),
    ((-0.436, -0.591, -0.390), (-0.01, -0.93, -0.36), 0.170, 0.15),  # 下大静脈
)
TOP_FADE = (0.92, 1.17)
# 左心耳（画面の右上で、肺動脈の左に載る耳のような袋）の真ん中・広がりと、心房の中の点
# （ここから外向きに膨らむ）、揺れる向き。揺れ・しぼみ・膨らみの大きさ（形の長さ）
AURICLE_CENTER = (0.50, 0.11, 0.08)
AURICLE_RADIUS = (0.15, 0.12, 0.17)
AURICLE_INNER = (0.36, 0.05, -0.12)
AURICLE_FLAP = (0.35, -0.80, 0.50)
AURICLE_SWING = 0.04
AURICLE_SHRINK = 0.025
AURICLE_POP = 0.008


def _vec3(v: tuple[float, float, float]) -> str:
    return f"vec3({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f})"


_COUNT = len(VESSEL_ENDS)
_ENDS_C = ", ".join(_vec3(c) for c, _n, _r, _l in VESSEL_ENDS)
_ENDS_N = ", ".join(
    f"vec4({n[0]:.2f}, {n[1]:.2f}, {n[2]:.2f}, {r:.3f})" for _c, n, r, _l in VESSEL_ENDS
)
_ENDS_L = ", ".join(f"{length:.3f}" for _c, _n, _r, length in VESSEL_ENDS)

MODEL_MOTION_GLSL = f"""
const vec3 END_C[{_COUNT}] = vec3[{_COUNT}]({_ENDS_C});
const vec4 END_N[{_COUNT}] = vec4[{_COUNT}]({_ENDS_N});
const float END_L[{_COUNT}] = float[{_COUNT}]({_ENDS_L});
// 切り口で 0・透けていく長さより奥で 1。管の外（太さの 1.4〜2 倍より離れた所）は消さない
float vesselFade(vec3 p) {{
    float f = 1.0 - smoothstep({TOP_FADE[0]:.3f}, {TOP_FADE[1]:.3f}, p.y);
    for (int i = 0; i < {_COUNT}; i++) {{
        vec3 d = p - END_C[i];
        vec3 axis = normalize(END_N[i].xyz);
        float r = END_N[i].w;
        float along = dot(d, axis);
        float side = length(d - along * axis);
        float inside = 1.0 - smoothstep(1.4 * r, 2.0 * r, side);
        f = min(f, mix(1.0, smoothstep(0.0, END_L[i], -along), inside));
    }}
    return f;
}}

const vec3 AUR_CENTER = {_vec3(AURICLE_CENTER)};
const vec3 AUR_RADIUS = {_vec3(AURICLE_RADIUS)};
const vec3 AUR_INNER = {_vec3(AURICLE_INNER)};
const vec3 AUR_FLAP = {_vec3(AURICLE_FLAP)};
// 左心耳の動き: 一打ちで表面に沿って揺れ、心房が縮むとしぼむ。位置だけで決めるので、
// 心耳に重なった冠血管のパーツも同じだけ動く
vec3 auricleMove(vec3 p) {{
    float m = 1.0 - smoothstep(0.45, 1.0, length((p - AUR_CENTER) / AUR_RADIUS));
    if (m <= 0.0) return vec3(0.0);
    vec3 outward = normalize(p - AUR_INNER);
    vec3 along = normalize(AUR_FLAP - dot(AUR_FLAP, outward) * outward);
    return m * (along * uAurL * {AURICLE_SWING:.3f}
        + outward * (max(uAurL, 0.0) * {AURICLE_POP:.3f} - uAtriaL * {AURICLE_SHRINK:.3f}));
}}
"""

MODEL_VERTEX = (
    """
#version 130
in vec3 aPos;
in vec3 aNormal;
in vec2 aUv;
in vec3 aKey0;
in vec3 aKey1;
in vec3 aKey2;
in vec2 aCavity;

uniform mat4 uModel;
uniform mat3 uNormalMat;
uniform mat4 uView;
uniform mat4 uProj;
uniform vec3 uPosScale;
uniform vec3 uKeyScale;
uniform vec3 uWeights;
// 左房の収縮（0〜1）と左心耳の揺れ（-1〜1）。clock の atria_l / auricle_l
uniform float uAtriaL;
uniform float uAurL;

out vec3 vWorldPos;
out vec3 vObjPos;
out vec3 vNormal;
out vec2 vUv;
out vec2 vCavity;
out float vFade;
out vec2 vGrip;
"""
    + GRIP_DENT_GLSL
    + MODEL_MOTION_GLSL
    + """
void main() {
    vec3 rest = aPos * uPosScale;
    vec3 p = rest
        + aKey0 * (uWeights.x * uKeyScale.x)
        + aKey1 * (uWeights.y * uKeyScale.y)
        + aKey2 * (uWeights.z * uKeyScale.z);
    p += auricleMove(rest);
    vec4 world = uModel * vec4(p, 1.0);
    vNormal = normalize(uNormalMat * aNormal);
    // 手で掴まれた所は、指の下が凹んで指の間が盛り上がる（作った心臓と同じ式）
    vGrip = vec2(0.0);
    if (uHandOn > 0.5) {
        vec3 grip = gripContact(world.xyz);
        world.xyz += vNormal * grip.x;
        vGrip = grip.yz;
    }
    vWorldPos = world.xyz;
    vObjPos = rest;
    // 詰めた UV（0〜1）は、グラデの画の範囲そのまま（画の上が v の小さい側）
    vUv = aUv;
    vCavity = aCavity;
    vFade = vesselFade(rest);
    gl_Position = uProj * uView * world;
}
"""
)

MODEL_FRAGMENT = (
    """
#version 130
in vec3 vWorldPos;
in vec3 vObjPos;
in vec3 vNormal;
in vec2 vUv;
in vec2 vCavity;
in float vFade;
in vec2 vGrip;

uniform vec3 uCamPos;
uniform int uMaterial;
uniform float uOpacity;
uniform float uPulse;
uniform sampler2D uGradient;
uniform sampler2D uEnv;
uniform float uEnvYaw;
// 0: 不透明な所だけ / 1: 透けて消えていく血管の先だけ / 2: 全部（ガラス）
uniform int uPass;

out vec4 fragColor;

const float PI = 3.14159265;
"""
    + _NOISE
    + """
vec3 toLinear(vec3 c) { return pow(c, vec3(2.2)); }
vec3 toScreen(vec3 c) { return pow(max(c, 0.0), vec3(1.0 / 2.2)); }

// Blender の AgX に近い、明るい所をなだらかに寝かせる色の変換（直線の色 → 画面の色）
vec3 softTone(vec3 c) {
    c = c / (c + vec3(0.6)) * 1.6;
    return toScreen(c);
}

vec3 envAt(vec3 dir) {
    float c = cos(uEnvYaw);
    float s = sin(uEnvYaw);
    dir = vec3(c * dir.x + s * dir.z, dir.y, -s * dir.x + c * dir.z);
    float u = atan(dir.x, -dir.z) / (2.0 * PI) + 0.5;
    float v = acos(clamp(dir.y, -1.0, 1.0)) / PI;
    return toLinear(texture(uEnv, vec2(u, v)).rgb);
}

// 誘電体の反射の割合（Blender の Fresnel ノードと同じ式）
float fresnelIor(float cosi, float eta) {
    float c = abs(cosi);
    float g = eta * eta - 1.0 + c * c;
    if (g <= 0.0) return 1.0;
    g = sqrt(g);
    float a = (g - c) / (g + c);
    float b = (c * (g + c) - 1.0) / (c * (g - c) + 1.0);
    return 0.5 * a * a * (1.0 + b * b);
}

vec3 realColor(vec3 n, vec3 v) {
    vec3 key = normalize(vec3(-0.45, 0.62, 0.66));
    vec3 fill = normalize(vec3(0.75, -0.1, 0.55));
    vec3 rim = normalize(vec3(0.3, 0.5, -0.85));
    float fine = vCavity.x;
    float broad = vCavity.y;
    // 心筋の地の色（深い紅〜赤）に、低いむらと筋の流れ（色は直線の値）
    float mottle = fbm(vObjPos * 3.2);
    float fibers = vnoise(vec3(vObjPos.x * 9.0, vObjPos.y * 26.0, vObjPos.z * 9.0));
    vec3 muscle = mix(vec3(0.16, 0.010, 0.014), vec3(0.42, 0.030, 0.030), mottle);
    muscle *= 0.88 + 0.16 * fibers;
    // 太い血管（上の方）も心筋と同じ深い紅でなじませる。大動脈・肺動脈はわずかに明るく、
    // 左の大静脈はわずかに暗い
    float top = smoothstep(0.28, 0.75, vObjPos.y);
    vec3 artery = mix(vec3(0.20, 0.016, 0.020), vec3(0.44, 0.040, 0.040), mottle);
    vec3 vein = mix(vec3(0.11, 0.008, 0.018), vec3(0.26, 0.018, 0.032), mottle);
    vec3 vessel = mix(artery, vein, smoothstep(-0.25, -0.5, vObjPos.x));
    vec3 albedo = mix(muscle, vessel, top);
    // 溝（冠動脈の通り道・心房と心室の境）には黄色い脂肪
    float fat = smoothstep(0.2, 0.8, broad) * (1.0 - top) * (0.5 + 0.5 * fbm(vObjPos * 6.0));
    albedo = mix(albedo, vec3(0.62, 0.36, 0.10), fat * 0.7);
    // 浮き出た冠血管は暗い紅
    float ridge = smoothstep(0.1, 0.55, -fine) * (1.0 - top);
    albedo = mix(albedo, vec3(0.13, 0.008, 0.02), ridge * 0.75);
    // 縮むとほんの少し血の気が増す
    albedo *= 1.0 + 0.07 * uPulse;

    float wrap = 0.3;
    float diff = max(0.0, (dot(n, key) + wrap) / (1.0 + wrap));
    float fillD = max(0.0, dot(n, fill)) * 0.3;
    float occl = 1.0 - 0.6 * max(0.0, fine) - 0.4 * max(0.0, broad);
    // 影も黒ではなく、透けた肉の深い赤
    vec3 light = vec3(1.25, 1.15, 1.1) * diff + vec3(0.45, 0.5, 0.65) * fillD
        + vec3(0.22, 0.06, 0.06);
    vec3 color = albedo * light * occl;
    // 濡れたつや（広いつやと、細かくきらっとするつや）
    float wet = 0.55 + 0.45 * vnoise(vObjPos * 18.0);
    vec3 h = normalize(key + v);
    float spec = pow(max(0.0, dot(n, h)), 40.0) * 0.18 + pow(max(0.0, dot(n, h)), 260.0) * 1.2;
    vec3 h2 = normalize(fill + v);
    spec += pow(max(0.0, dot(n, h2)), 110.0) * 0.22;
    color += vec3(1.0, 0.92, 0.9) * spec * wet * occl * (1.0 - fat * 0.6);
    float edge = pow(1.0 - max(0.0, dot(n, v)), 3.0);
    color += vec3(0.30, 0.05, 0.06) * edge * max(0.0, dot(n, rim) + 0.4) * 0.6;
    return toScreen(color / (color + vec3(0.9)) * 1.9);
}

vec3 gradientColor(vec3 n, vec3 v) {
    vec3 wave = toLinear(texture(uGradient, vUv).rgb);
    // Blender は スタジオの HDRI だけで照らしている。右上の前から当たる光で近づける
    vec3 key = normalize(vec3(0.42, 0.72, 0.55));
    float lightAmount = 0.62 * max(0.0, dot(n, key)) + 0.5 * (0.5 + 0.5 * n.y) + 0.12;
    lightAmount *= 1.0 - 0.6 * max(0.0, vCavity.x);
    // 2 段の陰（Shader to RGB → 一定のランプ）。境だけ少しなめらかに
    float lit = smoothstep(0.74, 0.79, lightAmount * 0.8);
    vec3 cel = mix(vec3(0.416, 0.345, 0.902), vec3(1.0), lit);
    vec3 body = cel * wave;
    // 縁: Fresnel（IOR 2.9）を白 → 紫のランプへ。暗い方を取る
    float f = fresnelIor(dot(n, v), 2.9);
    vec3 rimRamp = mix(vec3(1.0), vec3(0.309, 0.099, 0.489), clamp(f / 0.559, 0.0, 1.0));
    vec3 color = min(rimRamp, body);
    color *= 1.0 + 0.05 * uPulse;
    return softTone(color * 1.1);
}

vec3 bumpNormal(vec3 n) {
    // Blender の Noise（Object 座標・Scale 1.5）を Bump にしたもの。差分で高さの傾きを取る
    vec3 p = vObjPos * 1.5 * 4.0;
    float e = 0.02;
    float h0 = fbm(p);
    vec3 grad = vec3(
        fbm(p + vec3(e, 0.0, 0.0)), fbm(p + vec3(0.0, e, 0.0)), fbm(p + vec3(0.0, 0.0, e))
    ) - vec3(h0);
    grad /= e;
    return normalize(n - 0.035 * (grad - n * dot(grad, n)));
}

vec4 glassColor(vec3 n, vec3 v) {
    n = bumpNormal(n);
    float cosv = dot(n, v);
    float f = fresnelIor(cosv, 1.33);
    // Blender の色 (0.122, 0.678, 1.0) は AgX で青紫寄りに柔らかく写る。見た目に合わせて青へ寄せる
    vec3 tint = vec3(0.24, 0.50, 1.0);
    vec3 refl = envAt(reflect(-v, n));
    vec3 refr = envAt(refract(-v, n, 1.0 / 1.33));
    // 透けた先は水色に染まり、少し明るく持ち上げる（スタジオの HDRI は暗い）
    vec3 body = refr * tint * 3.2 + tint * 0.22;
    vec3 color = mix(body, refl * 2.6, f);
    // 表面の凹凸（血管）の縁がきらっとする
    color += tint * 0.25 * max(0.0, -vCavity.x);
    // スタジオの明かり（右上の橙・左の青）のきらめき
    vec3 warm = normalize(vec3(0.55, 0.5, 0.65));
    vec3 cool = normalize(vec3(-0.7, 0.25, 0.6));
    color += vec3(1.0, 0.62, 0.32) * pow(max(0.0, dot(n, normalize(warm + v))), 160.0) * 2.2;
    color += vec3(0.45, 0.62, 1.0) * pow(max(0.0, dot(n, normalize(cool + v))), 120.0) * 1.4;
    color *= 1.0 + 0.05 * uPulse;
    float alpha = clamp(0.42 + 0.9 * f + 0.25 * dot(refl, vec3(0.33)), 0.0, 1.0);
    return vec4(softTone(color), alpha);
}

void main() {
    bool faded = vFade < 0.995;
    if ((uPass == 0 && faded) || (uPass == 1 && !faded)) {
        discard;
    }
    vec3 n = normalize(vNormal);
    vec3 v = normalize(uCamPos - vWorldPos);
    // 裏面（ガラスの奥の面）は法線を返す
    if (!gl_FrontFacing) n = -n;
    // 指の影（手が浮いて見えないよう、指のすぐ脇を暗くする）
    float shade = 1.0 - 0.55 * clamp(vGrip.x, 0.0, 0.9);
    if (uMaterial == 2) {
        vec4 g = glassColor(n, v);
        fragColor = vec4(g.rgb * shade, g.a * uOpacity * vFade);
        return;
    }
    vec3 color = uMaterial == 1 ? gradientColor(n, v) : realColor(n, v);
    // 消えていく血管の先は少し暗く沈める（作った心臓と同じ）
    color *= shade * mix(0.72, 1.0, vFade);
    fragColor = vec4(color, uOpacity * vFade);
}
"""
)
