"""心エコー（心尖部四腔像）を OpenGL の断片シェーダーで描く。

画素ごとに「組織の反射の強さ」を心臓の形から求め、スペックル（粒状の干渉模様）を掛け、
深さの減衰と対数圧縮を通して白黒にする。スペックルは組織に貼り付いて一緒に動き、
血液の中の粒は毎フレーム入れ替わる。扇の外は描かない（背景色が見える）。

座標は扇の半径を 1 とし、探触子（扇の要）を原点に x が画面右、y が深さ。
心臓の形は chamber_glsl の長軸座標 (a, l) で共有する。
"""

from __future__ import annotations

from PySide6.QtGui import QOpenGLFunctions

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.chamber_glsl import (
    SliceShader,
    SliceShaderError,
    fragment_program,
    valve_open,
)

# 実機のフレームレートに近い間隔で粒を入れ替える
ECHO_FPS = 45.0

_UNIFORMS = """
uniform vec2 uViewport;
uniform vec2 uApex;
uniform float uRadius;
uniform float uHalf;
uniform float uZoom;
uniform float uSqueeze;
uniform float uOpen;
uniform float uFrame;
uniform float uOpacity;
out vec4 fragColor;
"""

_BODY = """
// 扇の中の心臓の置き場所。APEX は心外膜の心尖、AX_U は長軸（心基部へ）、AX_V は左室側
const vec2 APEX = vec2(0.035, 0.115);
const vec2 AX_U = vec2(0.1392, 0.9903);
const vec2 AX_V = vec2(0.9903, -0.1392);
// スペックルの粒の大きさ（横は角度、縦は深さ）。横に長い
const float SPK_TH = 0.0145;
const float SPK_R = 0.0085;
// 標準の奥行きで心臓が扇に収まる大きさ
const float FIT = 0.95;

// 平均がおよそ 1 の干渉模様（2 つの揺らぎの二乗和）
float speckle(vec2 c) {
    float g1 = vnoise(c) * 2.0 - 1.0;
    // 格子の向きがそろって角張らないよう、2 つめは回して重ねる
    vec2 cr = vec2(0.8253 * c.x - 0.5646 * c.y, 0.5646 * c.x + 0.8253 * c.y) * 1.07;
    float g2 = vnoise(cr + vec2(31.7, 17.3)) * 2.0 - 1.0;
    return (g1 * g1 + g2 * g2) * 2.8;
}

vec2 toRest(vec2 p) {
    vec2 d = p - APEX;
    return restLocal(vec2(dot(d, AX_U), dot(d, AX_V)), uSqueeze);
}

vec2 restToScreen(vec2 q) {
    return APEX + AX_U * q.x + AX_V * q.y;
}

// 反射の強さ（スペックル前）。detail=false は境界の鏡面反射を測る用の滑らかな版
float echogenicity(vec2 p, bool detail) {
    vec2 q = toRest(p);
    float sq = uSqueeze;
    Heart h = heartAt(q, sq);
    float inHeart = 1.0 - smoothstep(-0.003, 0.003, h.env);
    float wall = inHeart * smoothstep(-0.005, 0.009, h.cav);

    float r = length(p);
    float e = 0.012 + 0.022 * smoothstep(0.35, 0.8, nz(p * 9.0 + 3.0, detail));
    // 肺にかかる外側は暗い
    e *= 1.0 - 0.8 * smoothstep(0.26, 0.42, abs(dot(p - APEX, AX_V) + 0.10));

    // 心膜。壁に沿う膜で、音波に向き合う心房の裏と左室の外側だけ明るい
    float peri = exp(-pow((h.env - 0.004) / 0.0055, 2.0));
    float lateral = smoothstep(0.12, 0.18, q.y) * (1.0 - smoothstep(0.45, 0.6, q.x));
    float periW = max(smoothstep(0.64, 0.76, q.x), 0.8 * lateral);
    e = max(e, peri * (0.05 + 0.40 * periW));

    // 心房の壁は薄く、心室より暗い
    float atrial = smoothstep(MITRAL_A - 0.02, MITRAL_A + 0.07, q.x);
    // 心房中隔は薄く、真ん中が抜けて見える
    float fossa = exp(-pow((q.x - 0.62) / 0.05, 2.0)) * exp(-pow((q.y + 0.125) / 0.03, 2.0));
    float myo = 0.105 * (0.75 + 0.5 * nz(q * 26.0 + 11.0, detail));
    myo *= (1.0 - 0.4 * atrial) * (1.0 - 0.8 * fossa);
    // 血液はほぼ黒。心尖寄りは近距離の反響でわずかにもやがかかる
    e = mix(e, 0.008 + 0.02 * exp(-r / 0.22), inHeart);
    e = mix(e, myo, wall);

    // 十字（房室中隔）は線維で明るい
    vec2 cruxD = q - CRUX;
    e += 0.12 * exp(-dot(cruxD, cruxD) / 0.0009) * inHeart;

    if (detail) {
        e = max(e, 0.42 * valves(q, sq, h.mitralHalf, uOpen) * inHeart);
        // 右室心尖の肉柱のざらつき
        float trab = (1.0 - smoothstep(0.18, 0.30, q.x)) * (1.0 - smoothstep(-0.004, 0.004, h.rv));
        e += trab * 0.03 * vnoise(q * 60.0);
    }

    // 胸壁（皮膚・脂肪・筋の層）と近距離のもや
    float layers = 0.12 + 0.12 * nz(vec2(atan(p.x, p.y) * 9.0, r * 90.0), detail);
    float nearMask = 1.0 - smoothstep(0.075, 0.11, r);
    e = mix(e, layers, nearMask);
    e += 0.05 * exp(-r / 0.06);
    return e;
}

void main() {
    vec2 frag = vec2(gl_FragCoord.x, uViewport.y - gl_FragCoord.y);
    vec2 ps = (frag - uApex) / uRadius;
    float r = length(ps);
    float th = atan(ps.x, ps.y);
    float px = 1.0 / uRadius;
    float mask = 1.0 - smoothstep(1.0 - 1.5 * px, 1.0, r);
    mask *= smoothstep(0.0, 1.5 * px, (uHalf - abs(th)) * r);
    mask *= smoothstep(0.012, 0.012 + 1.5 * px, r);
    if (mask <= 0.0) {
        discard;
    }

    // 奥行きの設定（拡大）は探触子を中心に中身だけ広げる
    vec2 p = ps / (uZoom * FIT);
    vec2 beam = ps / max(r, 1e-4);
    float e = echogenicity(p, true);
    float delta = 0.011 / (uZoom * FIT);
    float spec = abs(echogenicity(p + beam * delta, false) - echogenicity(p - beam * delta, false));
    e += 0.8 * spec;

    // スペックルは組織の位置に貼る（粒の大きさは画面の上で一定）
    vec2 m = restToScreen(toRest(p)) * (uZoom * FIT);
    vec2 cell = vec2(atan(m.x, m.y) / SPK_TH, length(m) / SPK_R);
    float s = speckle(cell) * 0.8 + speckle(cell * vec2(1.9, 2.2) + 7.0) * 0.2;
    vec2 jitter = vec2(hash12(vec2(uFrame, 1.7)), hash12(vec2(uFrame, 9.1))) * 400.0;
    vec2 live = vec2(th / SPK_TH, r / SPK_R) + jitter;
    float fresh = speckle(live);
    float blood = 1.0 - smoothstep(0.02, 0.06, e);
    s = mix(s, fresh, 0.14 + 0.7 * blood);

    // 深さの減衰と、扇の端の弱まり
    float gain = (0.85 + 0.25 * smoothstep(0.04, 0.30, r));
    gain *= 1.0 - 0.40 * smoothstep(0.45, 1.0, r);
    gain *= 1.0 - 0.55 * smoothstep(0.55, 1.0, abs(th) / uHalf);
    // 走査線ごとのわずかなむら
    float line = floor((th / uHalf * 0.5 + 0.5) * 128.0);
    gain *= 0.96 + 0.08 * hash12(vec2(line, 5.3));

    float intensity = e * s * gain + 0.004 * fresh;
    float v = log(1.0 + 55.0 * intensity) / log(56.0);
    v = clamp((v - 0.08) / 0.9, 0.0, 1.0);
    vec3 color = vec3(v) * vec3(0.94, 0.97, 1.0);
    fragColor = vec4(color, mask * uOpacity);
}
"""

ECHO_FRAGMENT = fragment_program(_UNIFORMS, _BODY)

EchoRendererError = SliceShaderError


class EchoRenderer:
    """現在のコンテキストで扇形の心エコーを描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions) -> None:
        self._shader = SliceShader(functions, ECHO_FRAGMENT)

    def draw(
        self,
        *,
        width: int,
        height: int,
        apex: tuple[float, float],
        radius: float,
        half_angle: float,
        zoom: float,
        cycle: CardiacCycle,
        time_s: float,
        opacity: float,
    ) -> None:
        """apex と radius は画面の画素（左上が原点）。"""
        self._shader.draw(
            width,
            height,
            {
                "uApex": (float(apex[0]), float(apex[1])),
                "uRadius": max(1.0, radius),
                "uHalf": half_angle,
                "uZoom": max(0.2, zoom),
                "uSqueeze": cycle.squeeze,
                "uOpen": valve_open(cycle),
                # 長時間でも精度が落ちないよう小さな番号に折り返す
                "uFrame": float(int(time_s * ECHO_FPS) % 4096),
                "uOpacity": max(0.0, min(1.0, opacity)),
            },
        )
