"""心エコー（心尖部四腔像）を OpenGL の断片シェーダーで描く。

画素ごとに「組織の反射の強さ」を心臓の形から求め、スペックル（粒状の干渉模様）を掛け、
深さの減衰と対数圧縮を通して白黒にする。スペックルは組織に貼り付いて一緒に動き、
血液の中の粒は毎フレーム入れ替わる。扇の外は描かない（背景色が見える）。

座標は扇の半径を 1 とし、探触子（扇の要）を原点に x が画面右、y が深さ。
心臓はその中で長軸（心尖→心基部）に沿った座標 (a, l) で形を決める。
a は心尖からの距離、l は横方向で正が左室側（画面右）。
"""

from __future__ import annotations

from array import array

from PySide6.QtGui import QOpenGLFunctions, QVector2D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)

from stream_heartbeat.clock import CardiacCycle

GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_ONE = 0x0001

# 実機のフレームレートに近い間隔で粒を入れ替える
ECHO_FPS = 45.0

ECHO_VERTEX = """
#version 130
in vec2 aPos;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
}
"""

ECHO_FRAGMENT = """
#version 130
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

// 心臓の置き場所。APEX は心外膜の心尖、AX_U は長軸（心基部へ）、AX_V は左室側
const vec2 APEX = vec2(0.035, 0.115);
const vec2 AX_U = vec2(0.1392, 0.9903);
const vec2 AX_V = vec2(0.9903, -0.1392);
// 房室弁輪の高さ（心尖から）。三尖弁は僧帽弁より少し心尖寄り
const float MITRAL_A = 0.49;
const float TRICUSPID_A = 0.465;
// スペックルの粒の大きさ（横は角度、縦は深さ）。横に長い
const float SPK_TH = 0.0145;
const float SPK_R = 0.0085;
// 標準の奥行きで心臓が扇に収まる大きさ
const float FIT = 0.95;

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 x);

// 境界の鏡面反射を測るときは模様を省いて軽くする
float nz(vec2 x, bool detail) {
    return detail ? vnoise(x) : 0.5;
}

float vnoise(vec2 x) {
    vec2 i = floor(x);
    vec2 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash12(i);
    float b = hash12(i + vec2(1.0, 0.0));
    float c = hash12(i + vec2(0.0, 1.0));
    float d = hash12(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

// 平均がおよそ 1 の干渉模様（2 つの揺らぎの二乗和）
float speckle(vec2 c) {
    float g1 = vnoise(c) * 2.0 - 1.0;
    // 格子の向きがそろって角張らないよう、2 つめは回して重ねる
    vec2 cr = vec2(0.8253 * c.x - 0.5646 * c.y, 0.5646 * c.x + 0.8253 * c.y) * 1.07;
    float g2 = vnoise(cr + vec2(31.7, 17.3)) * 2.0 - 1.0;
    return (g1 * g1 + g2 * g2) * 2.8;
}

vec2 rot(vec2 p, float a) {
    float c = cos(a);
    float s = sin(a);
    return vec2(c * p.x - s * p.y, s * p.x + c * p.y);
}

float sdEllipse(vec2 p, vec2 r) {
    float k0 = length(p / r);
    float k1 = length(p / (r * r));
    return k0 * (k0 - 1.0) / max(k1, 1e-5);
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

// ---------------------------------------------------------------- 形（拡張末期を基準）

vec2 lvRadii(float sq) { return vec2(0.255 * (1.0 - 0.05 * sq), 0.112 * (1.0 - 0.24 * sq)); }
vec2 rvRadii(float sq) { return vec2(0.19 * (1.0 - 0.04 * sq), 0.088 * (1.0 - 0.22 * sq)); }
const vec2 LV_C = vec2(0.30, 0.0);
const vec2 RV_C = vec2(0.33, -0.255);
const float RV_TILT = 0.24;
const vec2 LA_C = vec2(0.61, 0.005);
const vec2 LA_R = vec2(0.135, 0.112);
const vec2 RA_C = vec2(0.595, -0.262);
const vec2 RA_R = vec2(0.13, 0.10);

float lvBody(vec2 q, float sq) { return sdEllipse(q - LV_C, lvRadii(sq)); }
float rvBody(vec2 q, float sq) { return sdEllipse(rot(q - RV_C, RV_TILT), rvRadii(sq)); }
// 心房は心室が縮むあいだに広がる（弁輪が心尖へ下がるぶん。座標の写しで表す）
float laBody(vec2 q) { return sdEllipse(q - LA_C, LA_R); }
float raBody(vec2 q) { return sdEllipse(q - RA_C, RA_R); }

// 画面の点 → 拡張末期の組織の位置。弁輪が心尖へ寄るぶん長軸方向に伸ばして戻す
vec2 toRest(vec2 p) {
    vec2 d = p - APEX;
    float a = dot(d, AX_U);
    float l = dot(d, AX_V);
    float base = MITRAL_A * (1.0 - 0.12 * uSqueeze);
    float a0 = a;
    if (a > 0.0 && a <= base) {
        a0 = a * MITRAL_A / base;
    } else if (a > base) {
        a0 = a + (MITRAL_A - base) * (1.0 - smoothstep(base, base + 0.36, a));
    }
    // 心臓から離れた胸壁や肺は動かさない
    float w = 1.0 - smoothstep(0.30, 0.46, abs(l + 0.09));
    return vec2(mix(a, a0, w), l);
}

vec2 restToScreen(vec2 q) {
    return APEX + AX_U * q.x + AX_V * q.y;
}

// 弁尖 1 枚。hinge から、閉じると向かいの弁尖へ、開くと心尖へ倒れる
float leaflet(vec2 q, vec2 hinge, float side, float len, float openAmt) {
    // 角度は「向かいの付け根へ向く向き」から心尖側へ測る。負は心房側へたわむ
    // side=+1 は l の正側の付け根で、閉じると l の負側へ伸びる
    float ang = mix(-0.20, 1.40, openAmt);
    float bend = mix(0.22, -0.18, openAmt);
    vec2 dir = vec2(-sin(ang), -side * cos(ang));
    vec2 dir2 = vec2(-sin(ang + bend), -side * cos(ang + bend));
    vec2 mid = hinge + dir * len * 0.5;
    vec2 tip = mid + dir2 * len * 0.5;
    float d = min(sdCapsule(q, hinge, mid, 0.0035), sdCapsule(q, mid, tip, 0.0045));
    return 1.0 - smoothstep(0.0, 0.0045, d);
}

// 反射の強さ（スペックル前）。detail=false は境界の鏡面反射を測る用の滑らかな版
float echogenicity(vec2 p, bool detail) {
    vec2 q = toRest(p);
    float sq = uSqueeze;

    // 腔（いまの形）。心室は弁輪で切る
    float lv = max(lvBody(q, sq), q.x - MITRAL_A);
    float rv = max(rvBody(q, sq), q.x - TRICUSPID_A);
    float la = laBody(q);
    float ra = raBody(q);
    float cav = min(min(lv, rv), min(la, ra));

    // 乳頭筋と調節帯は腔の中の筋
    vec2 lvr = lvRadii(sq);
    float pap = min(
        sdEllipse(q - vec2(0.34, lvr.y * 0.82), vec2(0.055, 0.018)),
        sdEllipse(q - vec2(0.38, -lvr.y * 0.80), vec2(0.042, 0.014))
    );
    float band = sdCapsule(q, vec2(0.25, -0.165), vec2(0.285, -0.33), 0.005);
    cav = max(cav, -min(pap, band));

    // 心臓の外形は拡張末期の腔に壁の厚みを足して決める（収縮で壁が厚くなる）
    float env = smin(
        smin(lvBody(q, 0.0) - 0.058, rvBody(q, 0.0) - 0.030, 0.04),
        smin(laBody(q) - 0.012, raBody(q) - 0.012, 0.03),
        0.035
    );
    float inHeart = 1.0 - smoothstep(-0.003, 0.003, env);
    float wall = inHeart * smoothstep(-0.005, 0.009, cav);

    float r = length(p);
    float e = 0.012 + 0.022 * smoothstep(0.35, 0.8, nz(p * 9.0 + 3.0, detail));
    // 肺にかかる外側は暗い
    e *= 1.0 - 0.8 * smoothstep(0.26, 0.42, abs(dot(p - APEX, AX_V) + 0.10));

    // 心膜。壁に沿う膜で、音波に向き合う心房の裏と左室の外側だけ明るい
    float peri = exp(-pow((env - 0.004) / 0.0055, 2.0));
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
    float mitralHalf = lvr.y * sqrt(max(0.0, 1.0 - pow((MITRAL_A - LV_C.x) / lvr.x, 2.0)));
    vec2 cruxD = q - vec2(0.475, -0.13);
    e += 0.12 * exp(-dot(cruxD, cruxD) / 0.0009) * inHeart;

    if (detail) {
        float v = 0.0;
        // 僧帽弁: 中隔側（前尖）が長い
        v = max(v, leaflet(q, vec2(MITRAL_A, -mitralHalf), -1.0, 0.105, uOpen));
        v = max(v, leaflet(q, vec2(MITRAL_A, mitralHalf), 1.0, 0.065, uOpen));
        // 三尖弁
        float triHalf = rvRadii(sq).y * 0.82;
        vec2 tCenter = vec2(TRICUSPID_A, RV_C.y + 0.02);
        v = max(v, leaflet(q, tCenter + vec2(0.0, triHalf), 1.0, 0.075, uOpen));
        v = max(v, leaflet(q, tCenter - vec2(0.0, triHalf), -1.0, 0.09, uOpen));
        e = max(e, 0.42 * v * inHeart);
        // 右室心尖の肉柱のざらつき
        float trab = (1.0 - smoothstep(0.18, 0.30, q.x)) * (1.0 - smoothstep(-0.004, 0.004, rv));
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
    float alpha = mask * uOpacity;
    fragColor = vec4(color, alpha);
}
"""


def valve_open(cycle: CardiacCycle) -> float:
    """房室弁の開き 0〜1。収縮中は閉じ、拡張早期に大きく開き、そのあとは半開きで漂う。"""
    if cycle.age < 0.08 or cycle.squeeze > 0.05:
        return 0.0
    x = max(0.0, min(1.0, (cycle.eject - 0.08) / 0.2))
    ejecting = x * x * (3.0 - 2.0 * x)
    return (1.0 - ejecting) * min(1.0, 0.45 + 0.7 * cycle.fill)


class EchoRendererError(RuntimeError):
    """エコー用シェーダーの準備に失敗した。"""


class EchoRenderer:
    """現在のコンテキストで扇形の心エコーを描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions) -> None:
        self._gl = functions
        self._vao = QOpenGLVertexArrayObject()
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        if not self._vao.create():
            raise EchoRendererError("頂点配列を作れません")
        self._vao.bind()
        if not self._vbo.create() or not self._vbo.bind():
            raise EchoRendererError("頂点バッファを作れません")
        quad = array("f", [-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1]).tobytes()
        self._vbo.allocate(quad, len(quad))
        self._vao.release()
        program = QOpenGLShaderProgram()
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, ECHO_VERTEX):
            raise EchoRendererError(f"頂点シェーダー: {program.log()}")
        if not program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, ECHO_FRAGMENT
        ):
            raise EchoRendererError(f"断片シェーダー: {program.log()}")
        program.bindAttributeLocation("aPos", 0)
        if not program.link():
            raise EchoRendererError(f"リンク: {program.log()}")
        self._program = program

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
        gl = self._gl
        gl.glViewport(0, 0, width, height)
        gl.glDisable(GL_DEPTH_TEST)
        gl.glDisable(GL_CULL_FACE)
        gl.glEnable(GL_BLEND)
        gl.glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        program = self._program
        self._vao.bind()
        program.bind()
        self._vbo.bind()
        program.enableAttributeArray(0)
        program.setAttributeBuffer(0, GL_FLOAT, 0, 2, 8)
        program.setUniformValue("uViewport", QVector2D(float(width), float(height)))
        program.setUniformValue("uApex", QVector2D(float(apex[0]), float(apex[1])))
        program.setUniformValue1f("uRadius", float(max(1.0, radius)))
        program.setUniformValue1f("uHalf", float(half_angle))
        program.setUniformValue1f("uZoom", float(max(0.2, zoom)))
        program.setUniformValue1f("uSqueeze", float(cycle.squeeze))
        program.setUniformValue1f("uOpen", float(valve_open(cycle)))
        # 長時間でも精度が落ちないよう小さな番号に折り返す
        program.setUniformValue1f("uFrame", float(int(time_s * ECHO_FPS) % 4096))
        program.setUniformValue1f("uOpacity", float(max(0.0, min(1.0, opacity))))
        gl.glDrawArrays(GL_TRIANGLES, 0, 6)
        program.release()
        self._vao.release()
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
