"""断面で描くスタイル（心エコー・MRI）が共有する四腔断面の形と、画素シェーダーの土台。

心臓は長軸に沿った座標 (a, l) で決める。a は心外膜の心尖からの距離（心基部へ正）、
l は横方向で正が左室側。長さの単位は、心尖から房室弁輪までがおよそ 0.5。
形は拡張末期を基準にし、収縮で腔が縮み壁が厚くなる。縮み方は部位ごとに違い（中隔は早く浅く、
側壁は遅れて深く、右室の自由壁は大きく）、拍ごとに少しむらがあり、心臓ごと拍で揺れて呼吸で漂う。
弁輪が心尖へ寄る動きと心臓ごとの揺れは restLocal で座標を戻して表す。
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
from stream_heartbeat.render.gl_platform import glsl

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
// 拡張末期の腔の半径
const vec2 LV_R0 = vec2(0.255, 0.112);
const vec2 RV_R0 = vec2(0.19, 0.088);
// 十字（房室中隔）。線維と脂肪が集まる所
const vec2 CRUX = vec2(0.475, -0.13);
// 心臓全体が揺れるときの中心
const vec2 HEART_MID = vec2(0.36, -0.10);

// ---- 動き。main の初めに setMotion() で決める
uniform float uAge;
uniform float uInterval;
uniform float uTime;
uniform float uSeed;
uniform float uOpen;
uniform float uOpenT;
uniform float uAtriaL;
uniform float uAtriaR;

float gSq;     // 中隔（いちばん早く、浅く縮む）
float gSqLat;  // 左室の側壁（遅れて、深く縮む）
float gSqRv;   // 右室の自由壁（ふいごのように大きく動く）
vec2 gShift;   // 心臓全体のずれ（拍の揺れと呼吸）
float gTurn;   // 心臓全体の回り
float gVar;    // 拍ごとのむら（0〜1）

float envelope(float dt, float s, float p, float e) {
    if (dt <= s || dt >= e) {
        return 0.0;
    }
    return dt <= p ? smoothstep(s, p, dt) : 1.0 - smoothstep(p, e, dt);
}

// 拍の起点から delay 秒遅れて縮み始める部位の収縮（clock の squeeze と同じ形）
float squeezeAt(float delay, float stretch) {
    float sys = clamp(uInterval * 0.36, 0.20, 0.34);
    return envelope(uAge - delay, 0.0, 0.05 * stretch, sys * 0.78 * stretch);
}

void setMotion() {
    gVar = hash12(vec2(uSeed, 3.7));
    float varB = hash12(vec2(uSeed, 8.1));
    gSq = squeezeAt(0.0, 1.0) * (0.92 + 0.16 * gVar);
    gSqLat = squeezeAt(0.032, 1.10) * (0.94 + 0.18 * varB);
    gSqRv = squeezeAt(0.018, 1.06) * (0.90 + 0.20 * hash12(vec2(uSeed, 5.3)));
    // 拍のたびに心臓ごと少し回って寄り、呼吸でゆっくり漂う
    float rock = squeezeAt(0.045, 1.25);
    float breath = uTime * 6.2832 / 4.4;
    gShift = vec2(-0.012 * rock + 0.010 * sin(breath), 0.010 * rock + 0.007 * sin(breath + 1.3));
    gTurn = (0.050 + 0.02 * varB) * rock + 0.012 * sin(breath + 0.4);
}

// 内膜の細かな凹凸（肉柱）。向きで決めるので壁と一緒に動く
float bumps(vec2 d, float seed) {
    vec2 u = d / max(length(d), 1e-4);
    return (vnoise(u * 3.5 + seed) - 0.5) * 0.010 + (vnoise(u * 9.0 + seed * 1.7) - 0.5) * 0.006;
}

// 左室の腔の半径。中隔側（l<0）は浅く、側壁は遅れて深く縮み、心尖寄りほど細る
vec2 lvRadiiAt(vec2 d) {
    float lat = smoothstep(-0.05, 0.05, d.y);
    float sq = mix(0.62 * gSq, 1.22 * gSqLat, lat);
    float apexward = 1.0 - smoothstep(-0.22, 0.04, d.x);
    return vec2(LV_R0.x * (1.0 - 0.06 * gSq), LV_R0.y * (1.0 - 0.25 * sq * (1.0 + 0.3 * apexward)));
}
// 右室は自由壁（局所の y が負）が中隔へ大きく寄る
vec2 rvRadiiAt(vec2 d) {
    float free = 1.0 - smoothstep(-0.04, 0.04, d.y);
    float sq = mix(0.50 * gSq, 1.30 * gSqRv, free);
    return vec2(RV_R0.x * (1.0 - 0.05 * gSq), RV_R0.y * (1.0 - 0.24 * sq));
}
float lvBody(vec2 q) {
    vec2 d = q - LV_C;
    return sdEllipse(d, lvRadiiAt(d)) + bumps(d, 2.0) * (0.6 + 0.9 * gSqLat);
}
float rvBody(vec2 q) {
    vec2 d = rot(q - RV_C, RV_TILT);
    return sdEllipse(d, rvRadiiAt(d)) + bumps(d, 7.0) * (0.5 + 0.8 * gSqRv);
}
// 心房は心室が縮むあいだ血を溜めて膨らみ、自分の収縮で縮む
float laBody(vec2 q) {
    return sdEllipse(q - LA_C, LA_R * (1.0 + 0.06 * gSqLat - 0.08 * uAtriaL));
}
float raBody(vec2 q) {
    return sdEllipse(q - RA_C, RA_R * (1.0 + 0.06 * gSqRv - 0.09 * uAtriaR));
}
// 弁輪の下がり方。側壁ほど大きい（右室の側壁がいちばん大きい）
float baseDrop(float l) {
    float k = 0.095 + 0.045 * smoothstep(-0.05, 0.15, l) + 0.075 * smoothstep(-0.24, -0.40, l);
    float sq = mix(gSq, l > -0.13 ? gSqLat : gSqRv, smoothstep(0.0, 0.2, abs(l + 0.13)));
    return k * sq;
}

// 長軸座標のいまの点 → 拡張末期の組織の位置（心臓全体の揺れと、弁輪が心尖へ寄るぶんを戻す）。
// 心房はそのぶん縦に広がる（心室が縮むあいだに心房へ血が溜まる）。
vec2 restLocal(vec2 al) {
    // 心臓から離れた所（胸壁や肺）は動かさない
    float w = 1.0 - smoothstep(0.30, 0.46, abs(al.y + 0.09));
    float wm = 1.0 - smoothstep(0.42, 0.70, length((al - HEART_MID) * vec2(0.9, 1.25)));
    al = mix(al, rot(al - HEART_MID - gShift, -gTurn) + HEART_MID, wm);
    float a = al.x;
    float l = al.y;
    float base = MITRAL_A * (1.0 - baseDrop(l));
    float a0 = a;
    if (a > 0.0 && a <= base) {
        a0 = a * MITRAL_A / base;
    } else if (a > base) {
        a0 = a + (MITRAL_A - base) * (1.0 - smoothstep(base, base + 0.36, a));
    }
    return vec2(mix(a, a0, w), l);
}

// 壁の組織がいまどこにあるか → 拡張末期のどこだったか。腔が縮むと壁は面積を保って内へ寄る。
// 模様（エコーの粒・MRI の格子）を組織に貼り付けて一緒に動かす
vec2 wallRest(vec2 d, vec2 r, vec2 r0) {
    vec2 n = d / r0;
    float rho = length(n);
    if (rho < 1e-4) {
        return d;
    }
    vec2 dir = n / rho;
    float rc = 1.0 / max(length(dir * r0 / r), 1e-4);
    float rho0 = rho < rc ? rho / rc : sqrt(rho * rho - rc * rc + 1.0);
    float w = 1.0 - smoothstep(1.5, 2.6, rho);
    return mix(d, dir * rho0 * r0, w);
}
vec2 materialLocal(vec2 q) {
    vec2 d = q - LV_C;
    vec2 lv = wallRest(d, lvRadiiAt(d), LV_R0) - d;
    vec2 dr = rot(q - RV_C, RV_TILT);
    vec2 rv = rot(wallRest(dr, rvRadiiAt(dr), RV_R0) - dr, -RV_TILT);
    return q + lv + rv * 0.8;
}

struct Heart {
    float cav;   // 血液のある腔（乳頭筋などを除く）までの符号付き距離
    float env;   // 心臓の外形（心外膜）までの符号付き距離
    float rv;    // 右室腔
    float mitralHalf;
};

Heart heartAt(vec2 q) {
    Heart h;
    // 腔（いまの形）。心室は弁輪で切る
    h.rv = max(rvBody(q), q.x - TRICUSPID_A);
    float lv = max(lvBody(q), q.x - MITRAL_A);
    float cav = min(min(lv, h.rv), min(laBody(q), raBody(q)));
    // 乳頭筋と調節帯は腔の中の筋。側壁と一緒に中へ寄る
    float lvy = lvRadiiAt(vec2(0.04, 1.0)).y;
    float lvs = lvRadiiAt(vec2(0.08, -1.0)).y;
    float pap = min(
        sdEllipse(rot(q - vec2(0.33, lvy * 0.86), 0.22), vec2(0.050, 0.015 + 0.006 * gSqLat)),
        sdEllipse(rot(q - vec2(0.37, -lvs * 0.80), -0.2), vec2(0.044, 0.015 + 0.004 * gSq))
    );
    float band = sdCapsule(q, vec2(0.25, -0.165), vec2(0.285, -0.33 + 0.03 * gSqRv), 0.005);
    h.cav = max(cav, -min(pap, band));
    // 外形は拡張末期の腔に壁の厚みを足して決める（収縮で壁が厚くなる。外も少しだけ寄る）
    vec2 d = q - LV_C;
    float lvOut = sdEllipse(d, LV_R0 * vec2(1.0, 1.0 - 0.05 * gSqLat)) - 0.058;
    vec2 dr = rot(q - RV_C, RV_TILT);
    float rvOut = sdEllipse(dr, RV_R0 * vec2(1.0, 1.0 - 0.07 * gSqRv)) - 0.030;
    h.env = smin(
        smin(lvOut, rvOut, 0.04),
        smin(laBody(q) - 0.012, raBody(q) - 0.012, 0.03),
        0.035
    );
    vec2 lvr = lvRadiiAt(vec2(MITRAL_A - LV_C.x, 0.0));
    h.mitralHalf = lvr.y * sqrt(max(0.0, 1.0 - pow((MITRAL_A - LV_C.x) / lvr.x, 2.0))) + 0.012;
    return h;
}

// 弁尖 1 枚までの距離。付け根から先へ 5 つの節でたどる。
// 角度は「向かいの付け根へ向く向き」から心尖側へ測る（負は心房側へたわむ）。
// 開くと心尖へ倒れて先が反り、開いているあいだ先が細かく震える。閉じると先が向かいと
// 合わさって心房側へふくらむ。side=+1 は l の正側の付け根で、閉じると l の負側へ伸びる。
float leaflet(vec2 q, vec2 hinge, float side, float len, float openAmt, float phase,
              out vec2 tip) {
    float ang = mix(-0.30, 1.30, openAmt);
    float curl = mix(0.55, -0.28, openAmt);
    float shiver = 0.22 * openAmt * (1.0 - 0.6 * openAmt)
        * sin(uTime * 71.0 + phase) * (0.6 + 0.4 * sin(uTime * 23.0 + phase * 1.7));
    float d = 1e3;
    vec2 p = hinge;
    for (int i = 0; i < 5; i++) {
        float s = (float(i) + 0.5) / 5.0;
        float a = ang + (curl + shiver) * s * s;
        vec2 dir = vec2(-sin(a), -side * cos(a));
        vec2 nxt = p + dir * len * 0.2;
        // 付け根は薄く、先は腱索が付いて厚い
        float thick = mix(0.0026, 0.0052, s * s);
        d = min(d, sdCapsule(q, p, nxt, thick));
        p = nxt;
    }
    tip = p;
    return d;
}

// 僧帽弁（中隔側の前尖が長い）と三尖弁の 4 枚までの距離。chord は腱索までの距離
float valveDist(vec2 q, float mitralHalf, out float chord) {
    vec2 tip;
    float lvy = lvRadiiAt(vec2(0.04, 1.0)).y;
    float lvs = lvRadiiAt(vec2(0.08, -1.0)).y;
    vec2 papL = vec2(0.36, lvy * 0.70);
    vec2 papS = vec2(0.39, -lvs * 0.72);
    float v = leaflet(q, vec2(MITRAL_A, -mitralHalf), -1.0, 0.108, uOpen, 0.0, tip);
    chord = sdCapsule(q, tip, papS, 0.0012);
    v = min(v, leaflet(q, vec2(MITRAL_A, mitralHalf), 1.0, 0.068, uOpen * 0.9, 1.9, tip));
    chord = min(chord, sdCapsule(q, tip, papL, 0.0012));
    float triHalf = rvRadiiAt(vec2(0.1, 1.0)).y * 0.84;
    vec2 tCenter = vec2(TRICUSPID_A, RV_C.y + 0.02);
    vec2 papR = vec2(0.30, -0.33 + 0.03 * gSqRv);
    v = min(v, leaflet(q, tCenter + vec2(0.0, triHalf), 1.0, 0.078, uOpenT, 3.1, tip));
    chord = min(chord, sdCapsule(q, tip, papR, 0.0012));
    v = min(v, leaflet(q, tCenter - vec2(0.0, triHalf), -1.0, 0.094, uOpenT * 0.95, 4.4, tip));
    chord = min(chord, sdCapsule(q, tip, papR, 0.0012));
    return v;
}

// 開いた房室弁を抜けて心尖へ向かう血の速さ（心尖へ向かう向きを正）。収縮期は心基部へ戻る。
// 心エコーのカラードプラと、MRI の流れの暗さに使う
float inflow(vec2 q) {
    // 僧帽弁の口から心尖へ。先へ行くほど広がって遅くなる
    float alongM = clamp((MITRAL_A + 0.02 - q.x) / 0.36, -0.4, 1.2);
    float widthM = 0.030 + 0.075 * max(alongM, 0.0);
    float coreM = exp(-pow((q.y - 0.018) / widthM, 2.0));
    float jetM = coreM * (1.0 - smoothstep(0.7, 1.15, alongM)) * smoothstep(-0.4, 0.0, alongM);
    float mitral = jetM * uOpen * (1.0 + 0.5 * (1.0 - smoothstep(0.0, 0.3, alongM)));
    // 三尖弁の口から右室の心尖へ
    vec2 dt = rot(q - vec2(TRICUSPID_A, RV_C.y + 0.02), RV_TILT);
    float alongT = clamp(-dt.x / 0.32, -0.4, 1.2);
    float widthT = 0.028 + 0.06 * max(alongT, 0.0);
    float jetT = exp(-pow(dt.y / widthT, 2.0)) * (1.0 - smoothstep(0.7, 1.1, alongT))
        * smoothstep(-0.4, 0.0, alongT);
    float tricuspid = jetT * uOpenT * 0.8;
    // 渦: 心尖で折り返した血が壁ぞいに戻る（拡張の終わりほど）
    float wallBack = smoothstep(0.03, 0.08, abs(q.y)) * (1.0 - smoothstep(0.08, 0.12, abs(q.y)))
        * smoothstep(0.12, 0.30, q.x) * (1.0 - smoothstep(0.38, 0.48, q.x));
    float vortex = -0.35 * wallBack * uOpen * smoothstep(0.3, 0.8, uAge / max(uInterval, 0.2));
    // 収縮期: 心室の血は心基部（大動脈の出口は中隔寄り）へ押し出される
    float ej = squeezeAt(0.04, 1.3);
    float outLv = -ej * (0.12 + 0.55 * exp(-pow((q.y + 0.04) / 0.05, 2.0)))
        * smoothstep(0.08, 0.40, q.x) * (1.0 - smoothstep(0.44, 0.50, q.x));
    return mitral + tricuspid + vortex + outLv;
}
"""


def fragment_program(uniforms: str, body: str) -> str:
    """版の宣言・共有部品・スタイル固有の本体を 1 つの断片シェーダーにまとめる。"""
    return "#version 130\n" + uniforms + NOISE_GLSL + SDF_GLSL + CHAMBER_GLSL + body


DEFAULT_INTERVAL = 60.0 / 72.0
# 弁が開ききるまでの秒・拡張なかほどの半開き・心房収縮でもう一度開くぶん
_VALVE_RISE = 0.05
_DIASTASIS = 0.38
_ATRIAL_OPEN = 0.42


def _smooth(edge0: float, edge1: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - edge0) / max(edge1 - edge0, 1e-6)))
    return t * t * (3.0 - 2.0 * t)


def valve_open(cycle: CardiacCycle, interval: float = DEFAULT_INTERVAL, lead: float = 0.0) -> float:
    """房室弁の開き 0〜1。

    収縮のあいだは閉じ、拡張早期に大きく開き（E）、なかほどで半ば閉じて漂い、
    心房の収縮でもう一度開いて（A）、次の拍で閉じる。lead は早めに開く秒（三尖弁）。
    """
    age = cycle.age + lead
    systole = min(0.34, max(0.20, interval * 0.36))
    open_at = systole * 0.80
    if age <= open_at or cycle.squeeze > 0.05:
        return 0.0
    t = age - open_at
    level = _smooth(0.0, _VALVE_RISE, t) - (1.0 - _DIASTASIS) * _smooth(0.07, 0.24, t)
    kick = max(open_at + 0.12, interval - 0.19)
    rise = _smooth(kick, kick + 0.07, age)
    fall = _smooth(kick + 0.08, kick + 0.20, age)
    # 心房が縮み終わると弁は浮いて閉じかける（次の拍が遅れてもそこで待つ）
    level *= 1.0 - 0.6 * fall
    return max(0.0, min(1.0, level + _ATRIAL_OPEN * rise * (1.0 - fall)))


def motion_uniforms(cycle: CardiacCycle, interval: float, time_s: float) -> dict[str, float]:
    """断面のスタイルに共通の、動きの値。"""
    # 拍ごとに変わる数（拍の起点の時刻から作る。長時間でも精度が落ちないよう折り返す）
    seed = round((time_s - cycle.age) * 10.0) % 997
    return {
        "uAge": float(cycle.age),
        "uInterval": float(max(0.25, interval)),
        "uTime": float(time_s % 3600.0),
        "uSeed": float(seed),
        "uOpen": valve_open(cycle, interval),
        "uOpenT": valve_open(cycle, interval, lead=0.02),
        "uAtriaL": float(cycle.atria_l),
        "uAtriaR": float(cycle.atria_r),
    }


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
        stage = QOpenGLShader.ShaderTypeBit
        if not program.addShaderFromSourceCode(stage.Vertex, glsl(QUAD_VERTEX)):
            raise SliceShaderError(f"頂点シェーダー: {program.log()}")
        if not program.addShaderFromSourceCode(stage.Fragment, glsl(fragment)):
            raise SliceShaderError(f"断片シェーダー: {program.log()}")
        program.bindAttributeLocation("aPos", 0)
        if not program.link():
            raise SliceShaderError(f"リンク: {program.log()}")
        self._program = program

    def draw(
        self,
        width: int,
        height: int,
        uniforms: dict[str, UniformValue],
        samplers: dict[str, int] | None = None,
    ) -> None:
        """samplers は画の名前と、その画をつないだ番号（glActiveTexture の番号）。"""
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
        for name, unit in (samplers or {}).items():
            program.setUniformValue1i(name, unit)
        gl.glDrawArrays(GL_TRIANGLES, 0, 6)
        program.release()
        self._vao.release()
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
