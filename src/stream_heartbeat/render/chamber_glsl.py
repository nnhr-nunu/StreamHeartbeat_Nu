"""断面で描くスタイル（心エコー・MRI）が共有する四腔断面の形と、画素シェーダーの土台。

心臓は長軸に沿った座標 (a, l) で決める。a は心外膜の心尖からの距離（心基部へ正）、
l は横方向で正が左室側。長さの単位は、心尖から房室弁輪までがおよそ 0.5。
形は拡張末期を基準にし、収縮（uSqueeze 相当の sq）で腔が縮み壁が厚くなる。
弁輪が心尖へ寄る動きは rest_local で座標を伸ばして表す。
"""

from __future__ import annotations

from array import array

from PySide6.QtGui import QOpenGLFunctions, QVector2D, QVector4D
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

QUAD_VERTEX = """
#version 130
in vec2 aPos;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
}
"""

NOISE_GLSL = """
float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
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

// 境界だけを測る下見のときは模様を省いて軽くする
float nz(vec2 x, bool detail) {
    return detail ? vnoise(x) : 0.5;
}
"""

SDF_GLSL = """
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
"""

CHAMBER_GLSL = """
// 房室弁輪の高さ（心尖から）。三尖弁は僧帽弁より少し心尖寄り
const float MITRAL_A = 0.49;
const float TRICUSPID_A = 0.465;
const vec2 LV_C = vec2(0.30, 0.0);
const vec2 RV_C = vec2(0.33, -0.255);
const float RV_TILT = 0.24;
const vec2 LA_C = vec2(0.61, 0.005);
const vec2 LA_R = vec2(0.135, 0.112);
const vec2 RA_C = vec2(0.595, -0.262);
const vec2 RA_R = vec2(0.13, 0.10);
// 十字（房室中隔）。線維と脂肪が集まる所
const vec2 CRUX = vec2(0.475, -0.13);

vec2 lvRadii(float sq) { return vec2(0.255 * (1.0 - 0.05 * sq), 0.112 * (1.0 - 0.24 * sq)); }
vec2 rvRadii(float sq) { return vec2(0.19 * (1.0 - 0.04 * sq), 0.088 * (1.0 - 0.22 * sq)); }
float lvBody(vec2 q, float sq) { return sdEllipse(q - LV_C, lvRadii(sq)); }
float rvBody(vec2 q, float sq) { return sdEllipse(rot(q - RV_C, RV_TILT), rvRadii(sq)); }
float laBody(vec2 q) { return sdEllipse(q - LA_C, LA_R); }
float raBody(vec2 q) { return sdEllipse(q - RA_C, RA_R); }

// 長軸座標のいまの点 → 拡張末期の組織の位置。弁輪が心尖へ寄るぶん伸ばして戻す。
// 心房はそのぶん縦に広がる（心室が縮むあいだに心房へ血が溜まる）。
vec2 restLocal(vec2 al, float sq) {
    float a = al.x;
    float l = al.y;
    float base = MITRAL_A * (1.0 - 0.12 * sq);
    float a0 = a;
    if (a > 0.0 && a <= base) {
        a0 = a * MITRAL_A / base;
    } else if (a > base) {
        a0 = a + (MITRAL_A - base) * (1.0 - smoothstep(base, base + 0.36, a));
    }
    // 心臓から離れた所（胸壁や肺）は動かさない
    float w = 1.0 - smoothstep(0.30, 0.46, abs(l + 0.09));
    return vec2(mix(a, a0, w), l);
}

struct Heart {
    float cav;   // 血液のある腔（乳頭筋などを除く）までの符号付き距離
    float env;   // 心臓の外形（心外膜）までの符号付き距離
    float rv;    // 右室腔
    float mitralHalf;
};

Heart heartAt(vec2 q, float sq) {
    Heart h;
    // 腔（いまの形）。心室は弁輪で切る
    h.rv = max(rvBody(q, sq), q.x - TRICUSPID_A);
    float lv = max(lvBody(q, sq), q.x - MITRAL_A);
    float cav = min(min(lv, h.rv), min(laBody(q), raBody(q)));
    // 乳頭筋と調節帯は腔の中の筋
    vec2 lvr = lvRadii(sq);
    float pap = min(
        sdEllipse(q - vec2(0.34, lvr.y * 0.82), vec2(0.055, 0.018)),
        sdEllipse(q - vec2(0.38, -lvr.y * 0.80), vec2(0.042, 0.014))
    );
    float band = sdCapsule(q, vec2(0.25, -0.165), vec2(0.285, -0.33), 0.005);
    h.cav = max(cav, -min(pap, band));
    // 外形は拡張末期の腔に壁の厚みを足して決める（収縮で壁が厚くなる）
    h.env = smin(
        smin(lvBody(q, 0.0) - 0.058, rvBody(q, 0.0) - 0.030, 0.04),
        smin(laBody(q) - 0.012, raBody(q) - 0.012, 0.03),
        0.035
    );
    h.mitralHalf = lvr.y * sqrt(max(0.0, 1.0 - pow((MITRAL_A - LV_C.x) / lvr.x, 2.0)));
    return h;
}

// 弁尖 1 枚。hinge から、閉じると向かいの弁尖へ、開くと心尖へ倒れる。
// 角度は「向かいの付け根へ向く向き」から心尖側へ測る。負は心房側へたわむ。
// side=+1 は l の正側の付け根で、閉じると l の負側へ伸びる。
float leaflet(vec2 q, vec2 hinge, float side, float len, float openAmt) {
    float ang = mix(-0.20, 1.40, openAmt);
    float bend = mix(0.22, -0.18, openAmt);
    vec2 dir = vec2(-sin(ang), -side * cos(ang));
    vec2 dir2 = vec2(-sin(ang + bend), -side * cos(ang + bend));
    vec2 mid = hinge + dir * len * 0.5;
    vec2 tip = mid + dir2 * len * 0.5;
    float d = min(sdCapsule(q, hinge, mid, 0.0035), sdCapsule(q, mid, tip, 0.0045));
    return 1.0 - smoothstep(0.0, 0.0045, d);
}

// 僧帽弁（中隔側の前尖が長い）と三尖弁の 4 枚。0〜1 の濃さ
float valves(vec2 q, float sq, float mitralHalf, float openAmt) {
    float v = leaflet(q, vec2(MITRAL_A, -mitralHalf), -1.0, 0.105, openAmt);
    v = max(v, leaflet(q, vec2(MITRAL_A, mitralHalf), 1.0, 0.065, openAmt));
    float triHalf = rvRadii(sq).y * 0.82;
    vec2 tCenter = vec2(TRICUSPID_A, RV_C.y + 0.02);
    v = max(v, leaflet(q, tCenter + vec2(0.0, triHalf), 1.0, 0.075, openAmt));
    v = max(v, leaflet(q, tCenter - vec2(0.0, triHalf), -1.0, 0.09, openAmt));
    return v;
}
"""


def fragment_program(uniforms: str, body: str) -> str:
    """版の宣言・共有部品・スタイル固有の本体を 1 つの断片シェーダーにまとめる。"""
    return "#version 130\n" + uniforms + NOISE_GLSL + SDF_GLSL + CHAMBER_GLSL + body


def valve_open(cycle: CardiacCycle) -> float:
    """房室弁の開き 0〜1。収縮中は閉じ、拡張早期に大きく開き、そのあとは半開きで漂う。"""
    if cycle.age < 0.08 or cycle.squeeze > 0.05:
        return 0.0
    x = max(0.0, min(1.0, (cycle.eject - 0.08) / 0.2))
    ejecting = x * x * (3.0 - 2.0 * x)
    return (1.0 - ejecting) * min(1.0, 0.45 + 0.7 * cycle.fill)


class SliceShaderError(RuntimeError):
    """断面用シェーダーの準備に失敗した。"""


UniformValue = float | tuple[float, float] | tuple[float, float, float, float]


class SliceShader:
    """窓全体を 1 枚の四角で覆い、断片シェーダーで画素ごとに描く。

    作成時にカレントなコンテキストが必要。描く範囲の外はシェーダーが捨てる。
    """

    def __init__(self, functions: QOpenGLFunctions, fragment: str) -> None:
        self._gl = functions
        self._vao = QOpenGLVertexArrayObject()
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        if not self._vao.create():
            raise SliceShaderError("頂点配列を作れません")
        self._vao.bind()
        if not self._vbo.create() or not self._vbo.bind():
            raise SliceShaderError("頂点バッファを作れません")
        quad = array("f", [-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1]).tobytes()
        self._vbo.allocate(quad, len(quad))
        self._vao.release()
        program = QOpenGLShaderProgram()
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, QUAD_VERTEX):
            raise SliceShaderError(f"頂点シェーダー: {program.log()}")
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment):
            raise SliceShaderError(f"断片シェーダー: {program.log()}")
        program.bindAttributeLocation("aPos", 0)
        if not program.link():
            raise SliceShaderError(f"リンク: {program.log()}")
        self._program = program

    def draw(self, width: int, height: int, uniforms: dict[str, UniformValue]) -> None:
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
        for name, value in uniforms.items():
            if isinstance(value, tuple) and len(value) == 2:
                program.setUniformValue(name, QVector2D(float(value[0]), float(value[1])))
            elif isinstance(value, tuple):
                program.setUniformValue(name, QVector4D(*(float(v) for v in value)))
            else:
                program.setUniformValue1f(name, float(value))
        gl.glDrawArrays(GL_TRIANGLES, 0, 6)
        program.release()
        self._vao.release()
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
