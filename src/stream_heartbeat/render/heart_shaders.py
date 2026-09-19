"""立体心臓のシェーダー。頂点側が拍動、断片側が質感。"""

from __future__ import annotations

from dataclasses import dataclass

VERTEX = """
#version 130
in vec3 aPos;
in vec3 aNormal;
in float aRegion;
in float aFat;
in float aAxial;
in vec2 aUv;

uniform mat4 uModel;
uniform mat4 uView;
uniform mat4 uProj;
uniform float uSqueeze;
uniform float uEject;
uniform float uFill;
uniform float uTime;

out vec3 vWorldPos;
out vec3 vNormal;
out float vRegion;
out float vFat;
out float vAxial;
out vec2 vUv;

const float TWIST_DEG = 18.0;

void main() {
    float lv = 1.0 - smoothstep(0.4, 0.6, aRegion);
    float ventricle = 1.0 - smoothstep(1.4, 1.6, aRegion);
    float rv = ventricle - lv;
    float atrium = smoothstep(1.4, 1.6, aRegion) * (1.0 - smoothstep(3.4, 3.6, aRegion));
    float artery = smoothstep(3.4, 3.6, aRegion) * (1.0 - smoothstep(4.4, 4.6, aRegion));
    float vein = smoothstep(4.4, 4.6, aRegion) * (1.0 - smoothstep(5.4, 5.6, aRegion));

    float ax = aAxial;
    float wall = lv * 1.0 + rv * 0.62;

    // 室は長軸へ向かって縮む。基部側は固定、心尖に近いほどよく縮む
    float radial = 1.0 - uSqueeze * 0.17 * wall * smoothstep(0.05, 0.55, ax);
    // 房は室が縮むあいだ血を溜めて少し膨らみ、充満で戻る
    float atr = 1.0 + atrium * (0.07 * uSqueeze - 0.05 * uFill);
    // 太い動脈は送り出しで太る。静脈は充満でわずかに
    float ves = 1.0 + artery * 0.12 * uEject + vein * 0.03 * uFill;

    vec3 p = aPos;
    vec3 n = aNormal;
    float s = radial * atr * ves;
    p.xz *= s;
    n.xz /= max(s, 1e-3);

    // 房室弁の面が心尖へ下がる。心尖はほぼ動かない
    float descend = uSqueeze * 0.11;
    p.y -= descend * ventricle * (1.0 - ax);
    p.y -= descend * atrium * clamp((0.78 - aPos.y) / 0.42, 0.0, 1.0);

    // 心尖が少し前へ突き上げる
    p.z += uSqueeze * 0.035 * ventricle * ax;

    // 長軸まわりの捩れ。心尖で最大
    float twist = radians(TWIST_DEG) * uSqueeze * ventricle * ax;
    float c = cos(twist);
    float sn = sin(twist);
    p.xz = mat2(c, -sn, sn, c) * p.xz;
    n.xz = mat2(c, -sn, sn, c) * n.xz;

    // 表面のごく弱い揺れ
    p += n * 0.003 * sin(uTime * 5.0 + aPos.x * 17.0 + aPos.y * 11.0);

    vec4 world = uModel * vec4(p, 1.0);
    vWorldPos = world.xyz;
    vNormal = normalize(mat3(uModel) * normalize(n));
    vRegion = aRegion;
    vFat = aFat;
    vAxial = ax;
    vUv = aUv;
    gl_Position = uProj * uView * world;
}
"""

_NOISE = """
float hash3(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vnoise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(mix(hash3(i + vec3(0, 0, 0)), hash3(i + vec3(1, 0, 0)), f.x),
            mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
        mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x),
            mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y),
        f.z);
}
float fbm(vec3 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
        v += a * vnoise(p);
        p = p * 2.03 + vec3(1.7, 9.2, 3.1);
        a *= 0.5;
    }
    return v;
}
float ridged(vec3 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 4; i++) {
        v += a * (1.0 - abs(2.0 * vnoise(p) - 1.0));
        p = p * 2.1 + vec3(3.3, 1.2, 7.7);
        a *= 0.5;
    }
    return v;
}
// ノイズの等高線を血管の網に使う。width が細さ
float veinLines(vec3 p, float width) {
    vec3 warp = vec3(fbm(p * 0.7), fbm(p * 0.7 + 11.0), fbm(p * 0.7 + 23.0)) - 0.5;
    float n = vnoise(p + warp * 1.6);
    return 1.0 - smoothstep(0.0, width, abs(n - 0.5));
}
"""

_HEADER = """
#version 130
in vec3 vWorldPos;
in vec3 vNormal;
in float vRegion;
in float vFat;
in float vAxial;
in vec2 vUv;
uniform vec3 uCamPos;
uniform float uOpacity;
uniform float uTime;
uniform float uSqueeze;
uniform float uEject;
uniform float uFill;
uniform float uFatAmount;
uniform float uGloss;
uniform float uSaturation;
uniform float uCoronary;
out vec4 fragColor;
"""

FLESH_FRAGMENT = (
    _HEADER
    + _NOISE
    + """
vec3 regionBase(float r, vec3 p) {
    vec3 lv = vec3(0.58, 0.10, 0.17);
    vec3 rv = vec3(0.66, 0.17, 0.21);
    vec3 la = vec3(0.50, 0.12, 0.26);
    vec3 ra = vec3(0.55, 0.15, 0.27);
    vec3 artery = vec3(0.80, 0.42, 0.40);
    vec3 vein = vec3(0.46, 0.22, 0.38);
    vec3 lumen = vec3(0.14, 0.02, 0.03);
    vec3 c = lv;
    c = mix(c, rv, smoothstep(0.4, 0.6, r));
    c = mix(c, la, smoothstep(1.4, 1.6, r));
    c = mix(c, ra, smoothstep(2.4, 2.6, r));
    c = mix(c, artery, smoothstep(3.4, 3.6, r));
    c = mix(c, vein, smoothstep(4.4, 4.6, r));
    c = mix(c, lumen, smoothstep(5.4, 5.6, r));
    return c;
}

void main() {
    vec3 N = normalize(vNormal);
    vec3 V = normalize(uCamPos - vWorldPos);
    vec3 P = vWorldPos;
    float isVessel = smoothstep(3.4, 3.6, vRegion) * (1.0 - smoothstep(5.4, 5.6, vRegion));
    float isLumen = smoothstep(5.4, 5.6, vRegion);
    float isBody = 1.0 - smoothstep(3.4, 3.6, vRegion);

    vec3 base = regionBase(vRegion, P);
    float isRv = smoothstep(0.4, 0.6, vRegion) * (1.0 - smoothstep(1.4, 1.6, vRegion));

    // 筋線維の走行と表面のむら
    float fiber = fbm(vec3(P.x * 9.0, P.y * 30.0, P.z * 9.0));
    float pores = vnoise(P * 70.0);
    float mottle = fbm(P * 4.5 + 7.0);
    float blotch = fbm(P * 2.2 + 13.0);
    base *= 0.88 + 0.22 * fiber + 0.06 * (pores - 0.5);
    // 動脈の外膜は薄く白っぽい膜が乗り、細い栄養血管が走る
    float sheath = fbm(P * 12.0 + 40.0);
    vec3 sheathColor = vec3(0.92, 0.78, 0.74);
    base = mix(base, sheathColor, isVessel * smoothstep(0.45, 0.75, sheath) * 0.55);
    float vasa = smoothstep(0.90, 0.985, ridged(P * 14.0 + vec3(6.0, 2.0, 9.0)));
    base = mix(base, vec3(0.55, 0.10, 0.12), isVessel * vasa * 0.6);
    base = mix(base, base * vec3(1.22, 0.90, 0.92), (mottle - 0.5) * 1.1);
    // 血の滲んだ暗い斑と、うっ血の紫
    base = mix(base, vec3(0.30, 0.03, 0.08), smoothstep(0.62, 0.78, blotch) * 0.45);
    base = mix(base, base * vec3(0.9, 0.8, 1.15), smoothstep(0.3, 0.5, 1.0 - blotch) * 0.3);

    // 細い血管の網。溝の近くと心尖側で濃い。冠動脈を出すときは抑える
    float veinsFine = veinLines(P * 11.0 + vec3(2.0), 0.035) * isBody;
    float veinsMid = veinLines(P * 4.2 + vec3(9.0, 1.0, 4.0), 0.022) * isBody;
    base = mix(base, vec3(0.32, 0.03, 0.07),
               (veinsFine * 0.35 + veinsMid * 0.7) * mix(1.0, 0.28, uCoronary));

    // 心外膜脂肪。溝に沿って厚く、小葉状にむらがあり、右室前面にも斑に載る
    float fatField = vFat * 1.25 * (0.7 + 0.6 * fbm(P * 3.0 + 5.0));
    fatField += (fbm(P * 7.0 + 17.0) - 0.5) * 0.9 * smoothstep(0.02, 0.3, vFat);
    fatField += (fbm(P * 2.5 + 29.0) - 0.5) * 0.5;
    float extraFat = mix(1.0, 0.28, uCoronary);
    fatField += extraFat * isRv * 0.7
        * smoothstep(0.55, 0.72, fbm(P * 2.6 + 21.0)) * (1.0 - vAxial * 0.7);
    fatField += extraFat * 0.5
        * smoothstep(0.60, 0.78, fbm(P * 1.8 + 44.0)) * (1.0 - vAxial) * isBody;
    float fatMask = smoothstep(0.42, 0.62, fatField * uFatAmount);
    fatMask *= isBody;
    float lobule = fbm(P * 16.0);
    // 脂肪の縁は薄く透けて下の筋が見える
    float fatLevel = fatField * uFatAmount;
    float fatEdge = smoothstep(0.42, 0.50, fatLevel) - smoothstep(0.50, 0.75, fatLevel);
    vec3 fatColor = mix(vec3(0.96, 0.74, 0.36), vec3(0.98, 0.60, 0.46),
                        smoothstep(0.35, 0.65, lobule));
    fatColor *= 0.82 + 0.36 * lobule;

    // 冠動脈は溝を幹にして心尖・側面へ枝を出す。脂肪の下にも透ける
    float wobble = (fbm(P * 6.0 + 31.0) - 0.5) * mix(0.10, 0.055, uCoronary);
    float groove = vFat + wobble;
    float trunkLo = mix(0.86, 0.70, uCoronary);
    float trunkHi = mix(0.96, 0.90, uCoronary);
    float trunk = smoothstep(trunkLo, trunkHi, groove) * isBody;
    float trunkShade = smoothstep(trunkLo - 0.10, trunkLo, groove) * isBody - trunk;
    vec3 q = vec3(P.x * 2.3, P.y * 1.15, P.z * 2.3);
    float branchA = 1.0 - smoothstep(0.0, mix(0.016, 0.034, uCoronary),
                                     abs(vnoise(q + vec3(4.0, 8.0, 2.0)) - 0.5));
    float branchB = 1.0 - smoothstep(0.0, mix(0.012, 0.026, uCoronary),
                                     abs(vnoise(q * 1.55 + vec3(9.0, 1.0, 7.0)) - 0.47));
    float branches = (branchA * 0.9 + branchB * 0.6) * isBody;
    branches *= smoothstep(0.10, 0.52, vFat) * mix(0.22, 1.0, uCoronary);
    branches *= 0.5 + 0.5 * (1.0 - vAxial * 0.65);
    vec3 coronaryColor = mix(vec3(0.70, 0.12, 0.14), vec3(0.90, 0.16, 0.18), uCoronary);
    vec3 coronaryShade = vec3(0.36, 0.04, 0.06);

    vec3 albedo = mix(base, fatColor, fatMask);
    albedo = mix(albedo, mix(base, fatColor, 0.5) * vec3(1.05, 0.85, 0.85), fatEdge * 0.5);
    float hide = mix(0.45, 0.12, uCoronary);
    float coronaryVis = (trunk * mix(0.55, 1.0, uCoronary) + branches * mix(0.18, 0.82, uCoronary));
    coronaryVis *= (1.0 - fatMask * hide);
    albedo = mix(albedo, coronaryShade, clamp(trunkShade * mix(0.15, 0.7, uCoronary), 0.0, 1.0));
    albedo = mix(albedo, coronaryColor, clamp(coronaryVis, 0.0, 1.0));
    albedo = mix(albedo, vec3(0.12, 0.02, 0.03), isLumen);

    float gray = dot(albedo, vec3(0.3, 0.59, 0.11));
    albedo = mix(vec3(gray), albedo, uSaturation);

    // 照明。無影灯のように上前から強く、補助は右下、縁は後ろ
    vec3 L1 = normalize(vec3(-0.35, 0.85, 0.65));
    vec3 L2 = normalize(vec3(0.75, -0.25, 0.55));
    vec3 L3 = normalize(vec3(0.2, 0.3, -1.0));
    float nl1 = dot(N, L1);
    float wrap = clamp((nl1 + 0.4) / 1.4, 0.0, 1.0);
    float d1 = wrap * wrap;
    float d2 = max(dot(N, L2), 0.0) * 0.32;
    float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0) * max(dot(N, L3) * 0.5 + 0.5, 0.0) * 0.35;

    // 薄いところで赤く透ける
    float sss = pow(1.0 - max(dot(N, V), 0.0), 2.0) * 0.30 * (1.0 - fatMask);
    vec3 sssColor = vec3(0.85, 0.12, 0.12) * sss;

    vec3 H1 = normalize(L1 + V);
    float fresnel = 0.04 + 0.96 * pow(1.0 - max(dot(N, V), 0.0), 5.0);
    float wetBumps = 0.85 + 0.3 * fbm(P * 30.0);
    float specTight = pow(max(dot(N, H1), 0.0), 260.0) * (0.6 + 0.4 * fresnel) * 2.6 * uGloss;
    float specMid = pow(max(dot(N, H1), 0.0), 48.0) * 0.45 * uGloss * wetBumps;
    float specBroad = pow(max(dot(N, H1), 0.0), 10.0) * 0.14 * uGloss;
    vec3 H2 = normalize(L2 + V);
    float spec2 = pow(max(dot(N, H2), 0.0), 90.0) * 0.35 * uGloss;
    // 脂肪は濡れ光が弱く、動脈は強い
    float specScale = mix(1.0, 0.7, fatMask) * mix(1.0, 1.3, isVessel);
    float spec = (specTight + specMid + specBroad + spec2) * specScale;

    vec3 light = vec3(1.0, 0.96, 0.92) * d1 + vec3(0.55, 0.62, 0.78) * d2
        + vec3(0.9, 0.7, 0.7) * rim;
    vec3 color = albedo * (light + 0.10) + sssColor + spec * vec3(1.0, 0.97, 0.95);

    // 断面の内腔は暗く沈める
    color = mix(color, color * 0.35, isLumen);

    color = pow(color, vec3(0.92));
    fragColor = vec4(color, uOpacity);
}
"""
)

MECH_FRAGMENT = (
    _HEADER
    + _NOISE
    + """
void main() {
    vec3 N = normalize(vNormal);
    vec3 V = normalize(uCamPos - vWorldPos);
    vec3 P = vWorldPos;
    float isVessel = smoothstep(3.4, 3.6, vRegion) * (1.0 - smoothstep(5.4, 5.6, vRegion));
    float isLumen = smoothstep(5.4, 5.6, vRegion);
    float isBody = 1.0 - smoothstep(3.4, 3.6, vRegion);
    float pulse = max(uSqueeze, uEject * 0.8);

    // 外板のパネル割り。段ごとにずらしたレンガ状で、継ぎ目に面取り
    vec2 cell = vUv * vec2(9.0, 6.0);
    cell.x += 0.5 * mod(floor(cell.y), 2.0);
    vec2 f = abs(fract(cell) - 0.5);
    float edge = max(f.x, f.y);
    float seam = smoothstep(0.44, 0.47, edge) * isBody;
    float bevel = smoothstep(0.34, 0.44, edge) * (1.0 - seam) * isBody;
    // 面取りは光源側で明るく、反対で暗い
    vec2 towards = sign(fract(cell) - 0.5);
    float bevelDir = (f.x > f.y ? towards.x : -towards.y) * 0.5 + 0.5;
    float groove = smoothstep(0.55, 0.95, vFat) * isBody;
    float rivet = 0.0;
    float rivetHi = 0.0;
    {
        // 各パネルの四隅にリベット。左上に小さなハイライト
        vec2 rc = abs(fract(cell) - 0.5) - vec2(0.40);
        rivet = (1.0 - smoothstep(0.035, 0.05, length(rc))) * isBody;
        float hi = length(rc + vec2(0.012, -0.012));
        rivetHi = (1.0 - smoothstep(0.0, 0.03, hi)) * isBody;
    }
    float brushed = fbm(vec3(P.x * 40.0, P.y * 3.0, P.z * 40.0));
    float wear = fbm(P * 6.0 + 3.0);
    float scratches = smoothstep(0.75, 0.9, ridged(vec3(P.x * 30.0, P.y * 2.0, P.z * 30.0)));

    vec3 steel = vec3(0.32, 0.35, 0.40) * (0.82 + 0.3 * brushed) * (1.0 - 0.25 * scratches);
    vec3 dark = vec3(0.05, 0.06, 0.08);
    vec3 brass = vec3(0.74, 0.54, 0.24) * (0.85 + 0.3 * wear);
    vec3 chrome = vec3(0.66, 0.70, 0.76) * (0.9 + 0.2 * brushed);
    vec3 glow = vec3(0.0, 0.85, 1.0);
    vec3 red = vec3(1.0, 0.30, 0.12);

    vec3 albedo = steel;
    albedo *= 1.0 + bevel * (bevelDir * 0.5 - 0.25);
    albedo = mix(albedo, dark, seam);
    albedo = mix(albedo, brass, groove * (1.0 - seam) * 0.85);
    albedo = mix(albedo, chrome, isVessel);
    // 管には締め輪
    float band = smoothstep(0.42, 0.47, abs(fract(vUv.x * 5.0) - 0.5)) * isVessel;
    albedo = mix(albedo, vec3(0.10, 0.10, 0.12), band * 0.8);
    albedo = mix(albedo, vec3(0.02, 0.02, 0.02), isLumen);
    albedo = mix(albedo, albedo * 0.7, rivet);
    albedo = mix(albedo, albedo * 1.6, rivetHi);

    vec3 L1 = normalize(vec3(-0.5, 0.8, 0.6));
    vec3 L2 = normalize(vec3(0.8, -0.2, 0.4));
    float d1 = max(dot(N, L1), 0.0);
    float d2 = max(dot(N, L2), 0.0) * 0.4;
    vec3 H1 = normalize(L1 + V);
    vec3 H2 = normalize(L2 + V);
    float metal = mix(0.75, 1.0, isVessel) * (1.0 - seam * 0.9);
    float spec = pow(max(dot(N, H1), 0.0), mix(28.0, 120.0, isVessel)) * metal;
    spec += pow(max(dot(N, H2), 0.0), 40.0) * 0.4 * metal;
    float fres = pow(1.0 - max(dot(N, V), 0.0), 4.0);
    vec3 env = mix(vec3(0.10, 0.12, 0.16), vec3(0.55, 0.62, 0.72), fres);

    vec3 color = albedo * (d1 * vec3(1.0, 0.98, 0.95) + d2 * vec3(0.6, 0.7, 0.9) + 0.16)
        + spec * vec3(1.0) * (0.6 + 0.4 * fres) + env * 0.35 * albedo;

    // 継ぎ目と内腔が拍で光り、外板の下から光が漏れる
    float flicker = 0.9 + 0.1 * sin(uTime * 40.0 + P.y * 30.0);
    float glowAmt = seam * (0.35 + 1.4 * pulse) * flicker;
    vec3 pulseColor = mix(glow, red, smoothstep(0.3, 0.9, uEject));
    color += pulseColor * glowAmt;
    color += pulseColor * bevel * (1.0 - bevelDir) * 0.25 * pulse;
    color += pulseColor * isLumen * (0.5 + 1.2 * pulse);
    color += glow * groove * 0.20 * pulse;

    fragColor = vec4(color, uOpacity);
}
"""
)

SCAN_FRAGMENT = (
    _HEADER
    + _NOISE
    + """
uniform vec3 uTintDense;
uniform vec3 uTintThin;
uniform float uGrain;
uniform float uDensity;
void main() {
    vec3 N = normalize(vNormal);
    vec3 V = normalize(uCamPos - vWorldPos);
    float facing = abs(dot(N, V));
    float isLumen = smoothstep(5.4, 5.6, vRegion);
    // 正面ほど厚く写り、縁ほど薄い。両面を加算して密度にする
    float density = (0.09 + 0.20 * pow(facing, 0.6)) * uDensity;
    density *= (1.0 - isLumen * 0.7);
    // 管は壁が薄いので淡く、根元は体の中に埋まっているのでさらに薄く
    float isTube = smoothstep(3.4, 3.6, vRegion) * (1.0 - smoothstep(5.4, 5.6, vRegion));
    density *= mix(1.0, 0.55 * smoothstep(0.05, 0.45, vUv.x), isTube);
    float grain = fbm(vWorldPos * 26.0 + vec3(uTime * 1.7, uTime * 0.9, 0.0));
    float grain2 = vnoise(vWorldPos * 90.0 + vec3(0.0, uTime * 13.0, uTime * 7.0));
    density *= 1.0 + uGrain * (grain - 0.5) + uGrain * 0.35 * (grain2 - 0.5);
    // 室が縮むと壁が厚く濃く写る
    density *= 1.0 + 0.25 * uSqueeze * (1.0 - smoothstep(3.4, 3.6, vRegion));
    vec3 color = mix(uTintThin, uTintDense, clamp(density * 2.2, 0.0, 1.0)) * density;
    fragColor = vec4(color * uOpacity, 1.0);
}
"""
)


@dataclass(frozen=True)
class Look:
    key: str
    label: str
    program: str
    fat_amount: float = 1.0
    gloss: float = 1.0
    saturation: float = 1.0
    coronary: float = 0.0
    additive: bool = False
    tint_dense: tuple[float, float, float] = (1.0, 1.0, 1.0)
    tint_thin: tuple[float, float, float] = (1.0, 1.0, 1.0)
    grain: float = 0.0
    density: float = 1.0
    size_factor: float = 1.0


REALISTIC_LOOKS: list[Look] = [
    Look("surgical", "手術寄り", "flesh", fat_amount=1.0, gloss=1.0, saturation=1.0, coronary=0.22),
    Look(
        "anatomy",
        "教科書寄り",
        "flesh",
        fat_amount=0.48,
        gloss=0.62,
        saturation=0.96,
        coronary=1.0,
    ),
]

STYLE_LOOKS: dict[str, Look] = {
    "mech": Look("mech", "機械", "mech"),
    "xray": Look(
        "xray",
        "レントゲン",
        "scan",
        additive=True,
        tint_dense=(0.80, 0.84, 0.88),
        tint_thin=(0.34, 0.37, 0.42),
        grain=0.35,
        density=1.35,
        size_factor=0.80,
    ),
    "mri": Look(
        "mri",
        "MRI",
        "scan",
        additive=True,
        tint_dense=(1.0, 0.58, 0.62),
        tint_thin=(0.55, 0.05, 0.10),
        grain=0.9,
        size_factor=0.88,
    ),
}

DEFAULT_REALISTIC_LOOK = "surgical"


def realistic_look(key: str) -> Look:
    for look in REALISTIC_LOOKS:
        if look.key == key:
            return look
    return REALISTIC_LOOKS[0]


def fragment_source(program: str) -> str:
    if program == "mech":
        return MECH_FRAGMENT
    if program == "scan":
        return SCAN_FRAGMENT
    return FLESH_FRAGMENT
