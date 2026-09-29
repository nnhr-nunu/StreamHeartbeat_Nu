"""心臓 MRI（シネの輪切り）を OpenGL の断片シェーダーで描く。

胸の輪切りを足側から見た向き（画面上が体の前、画面右が体の左）で描く。心臓は
四腔断面で、心尖は体の左前（画面右上）を向き、右室が前（胸骨の裏）、左房が一番後ろ
（下行大動脈と背骨の前）に来る。血液が明るく心筋が暗いシネ MRI の見え方で、
色は赤みを帯びた白黒。パネル（角丸の四角）の外は描かない。

座標はパネルの高さの半分を 1 とし、中心が原点、x が画面右、y が画面下（体の後ろ）。
"""

from __future__ import annotations

from PySide6.QtGui import QOpenGLFunctions

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.chamber_glsl import SliceShader, fragment_program, valve_open

# シネ MRI は 1 拍を 20〜30 コマで撮る。粒の入れ替わりもそのくらい
MRI_FPS = 24.0

_UNIFORMS = """
uniform vec2 uViewport;
uniform vec4 uPanel;
uniform float uCorner;
uniform float uZoom;
uniform float uSqueeze;
uniform float uOpen;
uniform float uFrame;
uniform float uOpacity;
out vec4 fragColor;
"""

_BODY = """
// 心臓の置き場所（パネル座標）。AX_U は長軸（心基部へ）、AX_V は左室側。
// HEART_C に心臓の真ん中（長軸座標で a=0.38, l=-0.10 の所）が来る
const vec2 AX_U = vec2(-0.7220, 0.6919);
const vec2 AX_V = vec2(0.6919, 0.7220);
const vec2 HEART_C = vec2(0.08, -0.04);
// 長軸座標 1 がパネル座標でいくつか
const float HEART_K = 1.0;
const vec2 APEX = HEART_C - HEART_K * (0.38 * AX_U - 0.10 * AX_V);
// 拡大の中心（心臓の少し右寄り）
const vec2 ZOOM_C = vec2(0.06, 0.0);

// 信号の強さ（シネ MRI）
const float S_BLOOD = 0.92;
const float S_MYO = 0.24;
const float S_FAT = 0.84;
const float S_MUSCLE = 0.30;
const float S_LUNG = 0.03;
const float S_MEDIA = 0.40;

float sdRoundBox(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

// d<0 の中で 1、境目は w の幅でなめらかにする
float inside(float d, float w) {
    return 1.0 - smoothstep(-w, w, d);
}

// 肺の中の血管の断面。格子ごとに 1 つ、丸い点を置く
float vesselDots(vec2 p, float freq) {
    vec2 g = p * freq;
    vec2 cell = floor(g);
    vec2 c = cell + 0.2 + 0.6 * vec2(hash12(cell), hash12(cell + 17.0));
    float r = 0.08 + 0.18 * hash12(cell + 41.0);
    return (1.0 - smoothstep(r - 0.06, r + 0.06, length(g - c))) * step(0.45, hash12(cell + 7.0));
}

// 骨（外側の皮質は暗く、中の髄は中くらい）
float bone(float s, vec2 p, vec2 c, vec2 r, float marrow) {
    float d = sdEllipse(p - c, r);
    s = mix(s, 0.06, inside(d, 0.004));
    return mix(s, marrow, inside(d + 0.012, 0.004));
}

float signal(vec2 p) {
    float sq = uSqueeze;
    float s = 0.0;

    // 体の外形。皮下脂肪（明るい）→ 胸壁の筋 → 胸の中
    float body = sdEllipse(p - vec2(0.0, 0.04), vec2(0.88, 0.66));
    // 背中側は少し平ら
    body = max(body, p.y - 0.66);
    s = mix(s, S_FAT, inside(body, 0.005));
    float wallIn = body + 0.055;
    s = mix(s, S_MUSCLE * (0.85 + 0.3 * vnoise(p * 30.0)), inside(wallIn, 0.006));
    float thorax = body + 0.105;
    s = mix(s, S_MEDIA * (0.85 + 0.3 * vnoise(p * 14.0)), inside(thorax, 0.006));

    // 心臓（長軸座標へ移して形を求める）
    vec2 d = p - APEX;
    vec2 al = vec2(dot(d, AX_U), dot(d, AX_V)) / HEART_K;
    vec2 q = restLocal(al, sq);
    Heart h = heartAt(q, sq);
    float env = h.env * HEART_K;

    // 肺（信号なし）。心臓と縦隔に押されて凹む
    float lungL = sdEllipse(rot(p - vec2(0.47, 0.04), -0.20), vec2(0.34, 0.50));
    float lungR = sdEllipse(rot(p - vec2(-0.45, 0.01), 0.15), vec2(0.36, 0.52));
    float lung = max(min(lungL, lungR), thorax + 0.02);
    lung = max(lung, -(env - 0.05));
    lung = max(lung, -sdEllipse(p - vec2(0.0, 0.45), vec2(0.22, 0.24)));
    float vessels = vesselDots(p + 3.0, 16.0) * 0.30 + vesselDots(p, 31.0) * 0.18;
    s = mix(s, S_LUNG + vessels, inside(lung, 0.006));

    // 胸骨・肋骨・背骨
    s = bone(s, p, vec2(0.0, -0.545), vec2(0.075, 0.034), 0.50);
    for (int i = 0; i < 4; i++) {
        float t = 0.75 + float(i) * 0.50;
        for (int k = 0; k < 2; k++) {
            float side = k == 0 ? 1.0 : -1.0;
            vec2 c = vec2(side * 0.80 * sin(t), 0.04 - 0.585 * cos(t));
            s = bone(s, p, c, vec2(0.030, 0.021), 0.36);
        }
    }
    // 背骨の両脇の筋
    for (int k = 0; k < 2; k++) {
        float side = k == 0 ? 1.0 : -1.0;
        float m = sdEllipse(p - vec2(side * 0.19, 0.545), vec2(0.10, 0.07));
        s = mix(s, S_MUSCLE * 0.9, inside(m, 0.006));
    }
    s = bone(s, p, vec2(0.0, 0.46), vec2(0.12, 0.10), 0.45);
    // 脊柱管の髄液は明るい
    s = mix(s, 0.86, inside(sdEllipse(p - vec2(0.0, 0.595), vec2(0.04, 0.034)), 0.004));

    // 下行大動脈（背骨の左前）と食道
    float aorta = sdEllipse(p - vec2(0.165, 0.335), vec2(0.058, 0.058));
    s = mix(s, 0.10, inside(aorta - 0.008, 0.004));
    s = mix(s, S_BLOOD, inside(aorta, 0.004));
    s = mix(s, 0.32, inside(sdEllipse(p - vec2(0.03, 0.315), vec2(0.028, 0.024)), 0.004));

    // 心臓のまわりの脂肪（房室の溝と右室の前で厚い）と、その外の心膜（暗い線）
    float fatW = 0.012 + 0.035 * exp(-pow((q.x - 0.48) / 0.06, 2.0));
    fatW += 0.02 * (1.0 - smoothstep(-0.38, -0.30, q.y));
    s = mix(s, S_FAT * 0.92, inside(env - fatW * HEART_K, 0.005));
    float peri = abs(env - (fatW + 0.005) * HEART_K);
    s = mix(s, 0.10, (1.0 - smoothstep(0.0, 0.004, peri)) * 0.8);

    // 心筋と血液
    s = mix(s, S_MYO * (0.9 + 0.2 * vnoise(q * 30.0)), inside(env, 0.004));
    float blood = inside(h.cav * HEART_K, 0.004) * inside(env, 0.004);
    // 速い流れの所は少し暗む（弁の先と心尖の肉柱）
    float flow = 0.12 * uOpen * exp(-pow((q.x - 0.40) / 0.08, 2.0)) * exp(-pow(q.y / 0.06, 2.0));
    float trab = (1.0 - smoothstep(0.16, 0.32, q.x)) * inside(h.rv, 0.01);
    trab *= 0.35 * smoothstep(0.55, 0.85, vnoise(q * 70.0));
    s = mix(s, S_BLOOD - flow - trab, blood);
    // 弁は明るい血液の中の暗い線
    s = mix(s, 0.16, valves(q, sq, h.mitralHalf, uOpen) * inside(env, 0.004));
    return s;
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
    vec2 ps = (frag - center) / unit;
    vec2 p = ZOOM_C + (ps - ZOOM_C) / uZoom;

    float s = signal(p);
    // 受信コイルの近く（体の表面）ほど明るい
    s *= 0.80 + 0.30 * smoothstep(0.25, 0.85, length(p - vec2(0.0, 0.05)));
    // 雑音（撮像ごとに入れ替わる）。信号が無い所にも薄く残る
    vec2 cell = floor(frag / max(1.0, unit / 220.0));
    float n1 = hash12(cell + vec2(uFrame * 7.13, 3.1)) - 0.5;
    float n2 = hash12(cell + vec2(11.7, uFrame * 5.71)) - 0.5;
    float v = length(vec2(s + n1 * 0.07, n2 * 0.07));
    v = clamp(v, 0.0, 1.0);

    vec3 lo = vec3(0.52, 0.07, 0.11);
    vec3 hi = vec3(1.0, 0.70, 0.74);
    vec3 color = v * mix(lo, hi, smoothstep(0.1, 0.95, v)) + pow(v, 4.0) * 0.18;
    fragColor = vec4(min(color, vec3(1.0)), mask * uOpacity);
}
"""

MRI_FRAGMENT = fragment_program(_UNIFORMS, _BODY)


class MriRenderer:
    """現在のコンテキストで MRI のパネルを描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions) -> None:
        self._shader = SliceShader(functions, MRI_FRAGMENT)

    def draw(
        self,
        *,
        width: int,
        height: int,
        panel: tuple[float, float, float, float],
        corner: float,
        zoom: float,
        cycle: CardiacCycle,
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
                "uZoom": max(0.3, zoom),
                "uSqueeze": cycle.squeeze,
                "uOpen": valve_open(cycle),
                "uFrame": float(int(time_s * MRI_FPS) % 4096),
                "uOpacity": max(0.0, min(1.0, opacity)),
            },
        )
