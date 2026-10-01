"""オシャレ2（ポリゴン風の心臓）の断片シェーダーの本体。

面ごとに平らな陰を付け、心尖の珊瑚色から心基部・血管のすみれ色へ移る色を面ごとに少しずらし、
三角形の辺に細い明るい線を引く。頂点側（拍動）はリアルと同じものを使う。
"""

from __future__ import annotations

POLY_BODY = """
const vec3 POLY_KEY = vec3(-0.45, 0.70, 0.55);
const vec3 POLY_FILL = vec3(0.62, -0.20, 0.70);

// 0（心尖）→ 1（上の血管）の色。珊瑚の橙 → ピンク → すみれ → 藍
vec3 polyPalette(float t) {
    vec3 a = vec3(1.00, 0.55, 0.30);
    vec3 b = vec3(1.00, 0.30, 0.50);
    vec3 c = vec3(0.70, 0.30, 0.92);
    vec3 d = vec3(0.32, 0.26, 0.82);
    t = clamp(t, 0.0, 1.0);
    if (t < 0.40) {
        return mix(a, b, t / 0.40);
    }
    if (t < 0.75) {
        return mix(b, c, (t - 0.40) / 0.35);
    }
    return mix(c, d, (t - 0.75) / 0.25);
}

void main() {
    passGate();
    vec3 P = vWorldPos;
    vec3 V = normalize(uCamPos - P);
    // 面の平らな向き（拍で動いたあとの形から求める）
    vec3 Nf = normalize(cross(dFdx(P), dFdy(P)));
    if (dot(Nf, V) < 0.0) {
        Nf = -Nf;
    }
    // 面ごとのゆらぎ（同じ面は同じ向きなので、向きから決める）
    float facet = hash3(floor(Nf * 37.0) + vec3(0.5));

    float isTube = smoothstep(3.4, 3.6, vRegion);
    float isVein = smoothstep(4.4, 4.6, vRegion) * (1.0 - smoothstep(5.4, 5.6, vRegion));
    float t = mix(0.80 * pow(1.0 - vAxial, 1.3), 0.62 + 0.26 * vAxial, isTube);
    t = mix(t, 0.86 + 0.14 * vAxial, isVein);
    vec3 base = polyPalette(t + (facet - 0.5) * 0.16);

    vec3 L = normalize(POLY_KEY);
    float diff = max(dot(Nf, L), 0.0);
    float fill = max(dot(Nf, normalize(POLY_FILL)), 0.0);
    float rim = pow(1.0 - max(dot(Nf, V), 0.0), 2.0);
    vec3 color = base * (0.34 + 0.72 * diff + 0.16 * fill);
    color += rim * vec3(0.62, 0.48, 1.0) * 0.30;
    vec3 H = normalize(L + V);
    color += pow(max(dot(Nf, H), 0.0), 36.0) * 0.30 * vec3(1.0, 0.95, 1.0);
    // 拍の瞬間は全体がわずかに明るむ
    color *= 1.0 + 0.14 * uSqueeze;

    // 三角形の辺の細い線
    vec3 bary = vec3(vUv, 1.0 - vUv.x - vUv.y);
    float edge = min(min(bary.x, bary.y), bary.z);
    float line = 1.0 - smoothstep(0.0, fwidth(edge) * 1.4, edge);
    color = mix(color, vec3(1.0, 0.93, 0.98), line * 0.30);

    fragColor = vec4(pow(color, vec3(0.95)), uOpacity * vFade);
}
"""
