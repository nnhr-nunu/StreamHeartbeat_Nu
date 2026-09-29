"""胸部レントゲン（正面像）の背景を OpenGL の断片シェーダーで描く。

X 線の写り方に合わせ、厚く密なものほど明るく足し合わせる。軟部（首・肩・胸壁）、
暗い肺野と血管影、気管、横隔膜と胃泡、骨（鎖骨・肋骨・肩甲骨・上腕骨頭・脊椎）を
描く。骨は外側の皮質が明るく中が淡い。心臓の影はこの上に立体心臓を足して描く。
座標はパネルの高さの半分を 1 とし、中心が原点、x が画面右（体の左）、y が画面下。
"""

from __future__ import annotations

from PySide6.QtGui import QOpenGLFunctions

from stream_heartbeat.render.chamber_glsl import NOISE_GLSL, SDF_GLSL, SliceShader

XRAY_FPS = 12.0

_UNIFORMS = """
uniform vec2 uViewport;
uniform vec4 uPanel;
uniform float uCorner;
uniform float uFrame;
uniform float uOpacity;
out vec4 fragColor;
"""

_BODY = """
float sdRoundBox(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float inside(float d, float w) {
    return 1.0 - smoothstep(-w, w, d);
}

// 2 次ベジェの近くを線分で近似した距離
float sdBezier(vec2 p, vec2 a, vec2 b, vec2 c) {
    float d = 1e3;
    vec2 prev = a;
    for (int i = 1; i <= 8; i++) {
        float t = float(i) / 8.0;
        vec2 q = mix(mix(a, b, t), mix(b, c, t), t);
        d = min(d, sdCapsule(p, prev, q, 0.0));
        prev = q;
    }
    return d;
}

// 骨の帯。縁（皮質）がやや明るく、中は淡い。w は帯の半分の幅
float boneBand(float d, float w, float strength) {
    float body = inside(d - w, 0.005);
    float rim = exp(-pow((d - w * 0.80) / (w * 0.25), 2.0));
    return strength * body * (0.62 + 0.38 * rim);
}

// 肋骨。後ろ（背骨から横へ弓なりに出て、胸の外側で下へ回る）は濃く、
// 前（外側から内へ下りる）は淡く、胸骨の手前で軟骨になって消える
float ribs(vec2 p, float belly) {
    float acc = 0.0;
    for (int i = 0; i < 10; i++) {
        float k = float(i);
        float y0 = -0.64 + k * 0.098 + 0.0025 * k * k;
        float w = 0.016 + 0.0016 * k;
        float lateral = 0.52 + 0.30 * smoothstep(-0.5, 3.5, k) - 0.02 * k * step(6.0, k);
        for (int s = 0; s < 2; s++) {
            float side = s == 0 ? 1.0 : -1.0;
            vec2 q = vec2(p.x * side, p.y);
            vec2 a = vec2(0.075, y0);
            vec2 top = vec2(lateral * 0.60, y0 - 0.025 - 0.006 * k);
            vec2 wall = vec2(lateral, y0 + 0.15 + 0.014 * k);
            float post = sdBezier(q, a, top, wall);
            // 外へ行くほど太る
            float grow = 1.0 + 0.6 * smoothstep(0.1, 0.7, q.x);
            float lower = 1.0 - 0.75 * belly;
            acc += boneBand(post, w * grow, 0.20) * lower;
            float ant = sdBezier(q, wall + vec2(-0.01, 0.05),
                                 vec2(lateral * 0.74, y0 + 0.34),
                                 vec2(0.24, y0 + 0.50 + 0.012 * k));
            float fadeIn = smoothstep(0.20, 0.42, q.x);
            acc += boneBand(ant, w * 1.1, 0.075) * fadeIn * lower;
        }
    }
    return acc;
}

// 胸椎は縦隔の影に淡く透ける。椎体の縁と椎弓根、棘突起
float spine(vec2 p) {
    float acc = 0.0;
    acc += 0.05 * inside(abs(p.x) - 0.075, 0.015);
    for (int i = 0; i < 18; i++) {
        float yc = -0.92 + float(i) * 0.104;
        float body = sdRoundBox(p - vec2(0.0, yc), vec2(0.066, 0.041), 0.018);
        acc += 0.035 * inside(body, 0.01) + 0.03 * exp(-pow(body / 0.008, 2.0));
        for (int s = 0; s < 2; s++) {
            float side = s == 0 ? 1.0 : -1.0;
            float ped = sdEllipse(p - vec2(side * 0.043, yc - 0.012), vec2(0.014, 0.020));
            acc += 0.04 * exp(-pow(ped / 0.006, 2.0));
        }
        float spinous = sdEllipse(p - vec2(0.0, yc + 0.02), vec2(0.010, 0.024));
        acc += 0.03 * inside(spinous, 0.008);
    }
    return acc;
}

float shoulderBones(vec2 p) {
    float acc = 0.0;
    for (int s = 0; s < 2; s++) {
        float side = s == 0 ? 1.0 : -1.0;
        vec2 q = vec2(p.x * side, p.y);
        // 鎖骨: 胸骨の上から外へ、少し下がってから肩へ上がる S 字
        float d = sdBezier(q, vec2(0.07, -0.64), vec2(0.30, -0.58), vec2(0.46, -0.66));
        d = min(d, sdBezier(q, vec2(0.46, -0.66), vec2(0.58, -0.72), vec2(0.70, -0.74)));
        acc += boneBand(d, 0.030, 0.32);
        // 肩甲骨: 肺の上外側に淡く重なる縁
        vec2 a = vec2(0.56, -0.66);
        vec2 b = vec2(0.46, -0.10);
        vec2 c = vec2(0.76, -0.44);
        float edge = min(sdCapsule(q, a, b, 0.0), sdCapsule(q, b, c, 0.0));
        edge = min(edge, sdCapsule(q, c, a, 0.0));
        acc += 0.06 * exp(-pow(edge / 0.010, 2.0));
        // 上腕骨頭と肩峰
        float head = sdEllipse(q - vec2(0.90, -0.70), vec2(0.14, 0.13));
        acc += boneBand(head + 0.12, 0.12, 0.30);
        float acromion = sdCapsule(q, vec2(0.68, -0.76), vec2(0.86, -0.82), 0.025);
        acc += 0.15 * inside(acromion, 0.01);
    }
    return acc;
}

float density(vec2 p) {
    // 体の輪郭: 首から肩へなで下ろし、脇の下から胴
    float ax = abs(p.x);
    float shoulderLine = -0.80 + 0.10 * smoothstep(0.18, 0.40, ax);
    shoulderLine += 0.06 * smoothstep(0.6, 1.0, ax);
    float neck = inside(ax - 0.19, 0.03);
    float torso = inside(ax - 0.96, 0.03);
    torso *= smoothstep(shoulderLine - 0.03, shoulderLine + 0.05, p.y);
    float bodyMask = max(torso, neck);
    float d = 0.22 * bodyMask + 0.06 * smoothstep(0.62, 0.98, ax) * bodyMask;

    // 横隔膜: 右（画面左）が少し高いドーム。下はお腹で明るい
    float domeR = 0.50 + 0.30 * pow(abs(p.x + 0.42) / 0.56, 2.0);
    float domeL = 0.58 + 0.30 * pow(abs(p.x - 0.44) / 0.56, 2.0);
    float dome = p.x < 0.0 ? domeR : domeL;
    float belly = smoothstep(dome - 0.01, dome + 0.012, p.y);

    // 肺野（暗い）。肺尖は鎖骨の上へ少し出て、下は横隔膜まで。縦隔の分は抜く
    float lung = 0.0;
    for (int s = 0; s < 2; s++) {
        float side = s == 0 ? 1.0 : -1.0;
        vec2 q = vec2(p.x * side, p.y);
        float shape = sdEllipse(q - vec2(0.46, 0.0), vec2(0.38, 0.76));
        shape = max(shape, 0.12 + 0.05 * smoothstep(-0.2, 0.3, q.y) - q.x);
        lung = max(lung, inside(shape, 0.025));
    }
    lung *= 1.0 - belly;
    d -= 0.15 * lung;

    // 肺の血管影。肺門から広がる枝ほど細く淡い
    for (int s = 0; s < 2; s++) {
        float side = s == 0 ? 1.0 : -1.0;
        vec2 q = vec2(p.x * side, p.y);
        vec2 rel = q - vec2(0.19, -0.05);
        float ang = atan(rel.y, rel.x);
        float r = length(rel);
        float veins = pow(abs(sin(ang * 9.0 + 2.0 * vnoise(q * 5.0) + r * 4.0)), 24.0);
        veins *= exp(-r / 0.26) * smoothstep(0.03, 0.10, r);
        d += 0.09 * veins * lung;
        // 肺門の濃い影
        d += 0.06 * exp(-pow(r / 0.07, 2.0)) * lung;
    }
    d += 0.04 * lung * (vnoise(p * 24.0) - 0.5);

    // お腹（横隔膜の下）と、左の横隔膜の下の胃の空気
    d += 0.22 * belly * bodyMask;
    d -= 0.12 * inside(sdEllipse(p - vec2(0.40, 0.76), vec2(0.13, 0.065)), 0.03) * belly;

    // 気管（暗い空気の柱）と左右の気管支
    float trachea = sdCapsule(p, vec2(0.0, -1.0), vec2(0.0, -0.24), 0.042);
    trachea = min(trachea, sdCapsule(p, vec2(0.0, -0.24), vec2(-0.12, -0.10), 0.028));
    trachea = min(trachea, sdCapsule(p, vec2(0.0, -0.24), vec2(0.14, -0.08), 0.026));
    d -= 0.07 * inside(trachea, 0.012) * (1.0 - belly);

    // 縦隔の影（背骨の前）。上は大動脈弓のこぶ
    d += 0.06 * inside(ax - 0.13, 0.04) * (1.0 - belly) * bodyMask;
    d += 0.07 * inside(sdEllipse(p - vec2(0.12, -0.30), vec2(0.07, 0.06)), 0.02);

    d += (ribs(p, belly) + shoulderBones(p)) * bodyMask;
    d += spine(p);
    return max(d, 0.0);
}

void main() {
    vec2 frag = vec2(gl_FragCoord.x, uViewport.y - gl_FragCoord.y);
    vec2 extent = uPanel.zw * 0.5;
    vec2 center = uPanel.xy + extent;
    float box = sdRoundBox(frag - center, extent, uCorner);
    float mask = 1.0 - smoothstep(-1.0, 0.5, box);
    if (mask <= 0.0) {
        discard;
    }
    float unit = uPanel.w * 0.5;
    vec2 p = (frag - center) / unit;
    float d = density(p);
    // フィルムの粒と、縁の減光
    vec2 cell = floor(frag / max(1.0, unit / 260.0));
    float grain = hash12(cell + vec2(uFrame * 3.1, uFrame * 1.7)) - 0.5;
    d += 0.025 * grain;
    d *= 1.0 - 0.35 * smoothstep(0.75, 1.35, length(p * vec2(0.9, 1.0)));
    float v = clamp(d, 0.0, 1.0);
    v = pow(v, 0.9);
    vec3 color = vec3(0.05, 0.06, 0.08) + v * vec3(0.86, 0.90, 0.96);
    fragColor = vec4(color, mask * uOpacity);
}
"""

XRAY_FRAGMENT = "#version 130\n" + _UNIFORMS + NOISE_GLSL + SDF_GLSL + _BODY


class XrayRenderer:
    """現在のコンテキストで胸部レントゲンのパネルを描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions) -> None:
        self._shader = SliceShader(functions, XRAY_FRAGMENT)

    def draw(
        self,
        *,
        width: int,
        height: int,
        panel: tuple[float, float, float, float],
        corner: float,
        time_s: float,
        opacity: float,
    ) -> None:
        """panel は左上を原点とする画素の (x, y, 幅, 高さ)。"""
        self._shader.draw(
            width,
            height,
            {
                "uPanel": panel,
                "uCorner": max(0.0, corner),
                "uFrame": float(int(time_s * XRAY_FPS) % 4096),
                "uOpacity": max(0.0, min(1.0, opacity)),
            },
        )
