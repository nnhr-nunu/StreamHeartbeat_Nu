"""心エコー（心尖部四腔像）を OpenGL の断片シェーダーで描く。

画素ごとに「組織の反射の強さ」を心臓の形から求め、スペックル（粒状の干渉模様）を掛け、
深さの減衰と対数圧縮を通して白黒にする。スペックルは組織に貼り付いて一緒に動き、
血液の中の粒は毎フレーム入れ替わる。扇の外は描かない（背景色が見える）。

描くのは 2 回。1 回目は粗い画へ明るさ（とカラードプラの速さ）を書き、2 回目で
走査線の横向きに広くにじませて窓へ重ねる（深いほど横に広がる。実機の横方向の分解能）。

座標は扇の半径を 1 とし、探触子（扇の要）を原点に x が画面右、y が深さ。
心臓の形は chamber_glsl の長軸座標 (a, l) で共有する。
"""

from __future__ import annotations

from PySide6.QtGui import QOpenGLFunctions

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.chamber_glsl import (
    DEFAULT_INTERVAL,
    SliceShaderError,
    fragment_program,
    motion_uniforms,
)
from stream_heartbeat.render.slice_post import BlurredSlice

# 実機のフレームレートに近い間隔で粒を入れ替える。カラードプラはもっと遅い
ECHO_FPS = 45.0
DOPPLER_FPS = 18.0
# 1 回目に描く粗い画の大きさ（窓に対して）
COARSE_FACTOR = 0.55
# カラードプラの箱（扇の中の小さな扇）: 角度の範囲（扇の半角に対する割合）と深さの範囲
DOPPLER_BOX = (-0.62, 0.58, 0.22, 0.94)

_COARSE_UNIFORMS = """
uniform vec2 uViewport;
uniform vec2 uCoarseScale;
uniform vec2 uApex;
uniform float uRadius;
uniform float uHalf;
uniform float uZoom;
uniform float uFrame;
uniform float uColorFrame;
uniform float uDoppler;
uniform vec4 uBox;
out vec4 fragColor;
"""

_COARSE_BODY = """
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

vec2 toLocal(vec2 p) {
    vec2 d = p - APEX;
    return vec2(dot(d, AX_U), dot(d, AX_V));
}

vec2 restToScreen(vec2 q) {
    return APEX + AX_U * q.x + AX_V * q.y;
}

// 反射の強さ（スペックル前）。detail=false は境界の鏡面反射を測る用の滑らかな版
float echogenicity(vec2 p, bool detail) {
    vec2 q = restLocal(toLocal(p));
    Heart h = heartAt(q);
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
    // 心筋のきめは組織に貼る（縮むと壁と一緒に寄る）
    vec2 m = materialLocal(q);
    float myo = 0.105 * (0.72 + 0.56 * nz(m * 26.0 + 11.0, detail));
    myo *= (1.0 - 0.4 * atrial) * (1.0 - 0.8 * fossa);
    // 縮んで厚くなった壁は少し明るい
    myo *= 1.0 + 0.25 * mix(gSq, gSqLat, step(0.0, q.y));
    // 血液はほぼ黒。心尖寄りは近距離の反響でわずかにもやがかかる
    e = mix(e, 0.008 + 0.02 * exp(-r / 0.22), inHeart);
    e = mix(e, myo, wall);

    // 十字（房室中隔）は線維で明るい
    vec2 cruxD = q - CRUX;
    e += 0.12 * exp(-dot(cruxD, cruxD) / 0.0009) * inHeart;

    if (detail) {
        float chord;
        float vd = valveDist(q, h.mitralHalf, chord);
        // 弁尖は明るい帯。先の厚い所ほど強く返る
        float leaf = 1.0 - smoothstep(0.0, 0.007, vd);
        e = max(e, 0.48 * leaf * inHeart);
        // 腱索は細くかすかに、ときどき光る
        float cord = 1.0 - smoothstep(0.0, 0.004, chord);
        float glint = smoothstep(0.35, 0.8, vnoise(q * 70.0 + uFrame * 0.21));
        e += 0.05 * cord * inHeart * (1.0 - wall) * glint;
        // 右室心尖の肉柱のざらつき
        float trab = (1.0 - smoothstep(0.18, 0.30, q.x)) * (1.0 - smoothstep(-0.004, 0.004, h.rv));
        e += trab * 0.03 * vnoise(m * 60.0);
    }

    // 胸壁（皮膚・脂肪・筋の層）と近距離のもや
    float layers = 0.12 + 0.12 * nz(vec2(atan(p.x, p.y) * 9.0, r * 90.0), detail);
    float nearMask = 1.0 - smoothstep(0.075, 0.11, r);
    e = mix(e, layers, nearMask);
    e += 0.05 * exp(-r / 0.06);
    return e;
}

// カラードプラ。探触子へ向かう血を正（赤）、遠ざかる血を負（青）。速すぎると折り返す
vec2 doppler(vec2 p, vec2 ps, float e) {
    float r = length(ps);
    float th = atan(ps.x, ps.y) / uHalf;
    float inBox = step(uBox.x, th) * step(th, uBox.y) * step(uBox.z, r) * step(r, uBox.w);
    if (inBox < 0.5) {
        return vec2(0.0, 0.0);
    }
    vec2 q = restLocal(toLocal(p));
    Heart h = heartAt(q);
    float blood = (1.0 - smoothstep(-0.006, 0.0, h.cav)) * (1.0 - smoothstep(-0.003, 0.003, h.env));
    // 走査線の向きと長軸のなす角で速さが目減りする
    vec2 beam = p / max(length(p), 1e-4);
    float v = inflow(q) * abs(dot(beam, AX_U)) * 1.2;
    // 流れの乱れ（ドプラの画の更新ごとに入れ替わる）
    float t = uColorFrame;
    float turb = vnoise(q * 38.0 + vec2(t * 1.7, t * 0.9)) - 0.5;
    v *= 0.85 + 0.6 * turb;
    v += 0.12 * (vnoise(q * 90.0 + vec2(t * 3.1, 7.0)) - 0.5) * step(0.25, abs(v));
    // 遅い動き（壁）は消す。組織が明るい所には色を載せない
    float power = blood * smoothstep(0.07, 0.16, abs(v)) * (1.0 - smoothstep(0.05, 0.12, e));
    float wrapped = v - 2.0 * sign(v) * floor((abs(v) + 1.0) * 0.5);
    return vec2(wrapped, power);
}

void main() {
    setMotion();
    vec2 frag = vec2(gl_FragCoord.x, uViewport.y - gl_FragCoord.y) / uCoarseScale;
    vec2 ps = (frag - uApex) / uRadius;
    float r = length(ps);
    float th = atan(ps.x, ps.y);
    // 扇の少し外まで描いておく（2 回目のにじみで縁が黒く欠けないように）
    if (r > 1.06 || abs(th) > uHalf + 0.06) {
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
    vec2 m = restToScreen(materialLocal(restLocal(toLocal(p)))) * (uZoom * FIT);
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

    vec2 dop = uDoppler > 0.5 ? doppler(p, ps, e) : vec2(0.0);
    fragColor = vec4(v, 0.5 + 0.5 * clamp(dop.x, -1.0, 1.0), dop.y, 1.0);
}
"""

_FINAL = """#version 130
uniform vec2 uViewport;
uniform vec2 uCoarseSize;
uniform sampler2D uCoarse;
uniform vec2 uApex;
uniform float uRadius;
uniform float uHalf;
uniform float uOpacity;
uniform float uDoppler;
uniform vec4 uBox;
out vec4 fragColor;

vec3 dopplerColor(float v) {
    // 赤（暗い赤 → 赤 → 橙黄）と青（紺 → 青 → 水色）
    float a = abs(v);
    vec3 toward = mix(vec3(0.45, 0.0, 0.02), vec3(1.0, 0.12, 0.05), smoothstep(0.05, 0.45, a));
    toward = mix(toward, vec3(1.0, 0.86, 0.25), smoothstep(0.55, 1.0, a));
    vec3 away = mix(vec3(0.02, 0.04, 0.45), vec3(0.08, 0.30, 1.0), smoothstep(0.05, 0.45, a));
    away = mix(away, vec3(0.45, 0.95, 1.0), smoothstep(0.55, 1.0, a));
    return v >= 0.0 ? toward : away;
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

    // 走査線の横向きに広くにじませる（深いほど広い）。縦（深さ）は少しだけ
    vec2 beam = ps / max(r, 1e-4);
    vec2 lat = vec2(beam.y, -beam.x);
    vec2 toUv = vec2(1.0, -1.0) / uViewport;
    vec2 uv = gl_FragCoord.xy / uViewport;
    float spread = uRadius * (0.0030 + 0.0105 * r);
    float axial = uRadius * 0.0028;
    vec4 acc = vec4(0.0);
    float wsum = 0.0;
    for (int i = -3; i <= 3; i++) {
        for (int j = -1; j <= 1; j++) {
            float w = exp(-0.5 * float(i * i) / 2.6 - 0.5 * float(j * j) / 0.8);
            vec2 off = (lat * float(i) * spread / 3.0 + beam * float(j) * axial) * toUv;
            acc += texture(uCoarse, uv + off) * w;
            wsum += w;
        }
    }
    acc /= wsum;
    // 真ん中は少しだけ強めに残して、ぼけすぎないようにする
    vec4 here = texture(uCoarse, uv);
    vec4 c = mix(acc, here, 0.18);

    float v = c.r;
    vec3 color = vec3(v) * vec3(0.94, 0.97, 1.0);
    if (uDoppler > 0.5) {
        float tn = th / uHalf;
        float inBox = step(uBox.x, tn) * step(tn, uBox.y) * step(uBox.z, r) * step(r, uBox.w);
        float vel = c.g * 2.0 - 1.0;
        float pw = smoothstep(0.22, 0.48, c.b) * inBox;
        color = mix(color, dopplerColor(vel), pw);
        // 箱の縁（細い灰色の線）
        float edgeT = min(abs(tn - uBox.x), abs(tn - uBox.y)) * uHalf * r / px;
        float edgeR = min(abs(r - uBox.z), abs(r - uBox.w)) / px;
        float onT = (1.0 - smoothstep(0.6, 1.6, edgeT)) * step(uBox.z, r) * step(r, uBox.w);
        float onR = (1.0 - smoothstep(0.6, 1.6, edgeR)) * step(uBox.x, tn) * step(tn, uBox.y);
        color = mix(color, vec3(0.62, 0.66, 0.72), max(onT, onR) * 0.75);
    }
    fragColor = vec4(color, mask * uOpacity);
}
"""

ECHO_COARSE = fragment_program(_COARSE_UNIFORMS, _COARSE_BODY)
ECHO_FINAL = _FINAL

EchoRendererError = SliceShaderError


class EchoRenderer:
    """現在のコンテキストで扇形の心エコーを描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions) -> None:
        self._slice = BlurredSlice(functions, ECHO_COARSE, ECHO_FINAL)

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
        interval: float = DEFAULT_INTERVAL,
        doppler: bool = False,
    ) -> None:
        """apex と radius は画面の画素（左上が原点）。doppler でカラードプラを重ねる。"""
        sector = {
            "uApex": (float(apex[0]), float(apex[1])),
            "uRadius": max(1.0, radius),
            "uHalf": half_angle,
            "uDoppler": 1.0 if doppler else 0.0,
            "uBox": DOPPLER_BOX,
        }
        coarse = {
            **sector,
            **motion_uniforms(cycle, interval, time_s),
            "uZoom": max(0.2, zoom),
            # 長時間でも精度が落ちないよう小さな番号に折り返す
            "uFrame": float(int(time_s * ECHO_FPS) % 4096),
            "uColorFrame": float(int(time_s * DOPPLER_FPS) % 4096),
        }
        final = {**sector, "uOpacity": max(0.0, min(1.0, opacity))}
        self._slice.draw(width, height, COARSE_FACTOR, coarse, final)
