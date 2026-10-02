"""心臓わしづかみの手を OpenGL で描く。

手の絵を細かい網目にして、頂点シェーダーで指を開き、心臓の胴へ巻き付ける（grip_pose と同じ式）。
網目の点は握った手の絵での位置も持ち（hand_morph）、握るほどそちらへ寄って絵も握った手に替わる。
指は輪郭を越えると奥へ回り込み、心臓越しに淡く透けて見える。手は心臓と同じカメラで描くので、
心臓の拍の揺れ・握りの潰れに合わせて動く。
"""

from __future__ import annotations

import math
from array import array

from PySide6.QtGui import QImage, QOpenGLFunctions, QVector2D, QVector3D, QVector4D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)

from stream_heartbeat.render.gl_platform import glsl
from stream_heartbeat.render.grip_pose import (
    ARM_RISE,
    ARM_RISE_MAX,
    ARM_SLOPE,
    FINGERS,
    GRIP_SHAPE_GLSL,
    HAND_IMAGE_SIZE,
    HAND_PALM,
    STIFF_FROM,
    STIFF_STEP,
    TAIL_V,
    HandPose,
    bend_index,
    claw_fingers,
    skin,
    wrap_weight,
)
from stream_heartbeat.render.hand_morph import claw_point
from stream_heartbeat.render.heart_gl import camera_matrices

GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_ONE = 0x0001
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_SRC_ALPHA = 0x0302
GL_LEQUAL = 0x0203
GL_DEPTH_BUFFER_BIT = 0x0100
GL_TEXTURE0 = 0x84C0

# 網目の細かさ（素材の横・縦の分け方）と、素材の下へ袖を伸ばす分
_COLS = 64
_ROWS = 112
_TAIL_ROWS = 6
_TAIL_EXTEND = 3000.0
# 指は手首より上にしか無いので、それより下は指へのつき方を計算しない
_SKIN_LIMIT_V = 760.0

_ATTRIBUTES = (
    ("aImg", 0, 2),
    ("aClaw", 2, 2),
    ("aTex", 4, 2),
    ("aClawTex", 6, 2),
    ("aSkin", 8, 4),
    ("aThumb", 12, 1),
    ("aInfo", 13, 4),
    ("aClawSkin", 17, 4),
    ("aClawThumb", 21, 1),
    ("aClawInfo", 22, 4),
)
_FLOATS = 26


def _vec2_list(points: list[tuple[float, float]]) -> str:
    return ", ".join(f"vec2({x:.1f}, {y:.1f})" for x, y in points)


_VERTEX = (
    """
#version 130
in vec2 aImg;
// 握った手の絵での位置と、その絵の上の点
in vec2 aClaw;
in vec2 aTex;
in vec2 aClawTex;
// 人差し指・中指・薬指・小指・親指へのつき方
in vec4 aSkin;
in float aThumb;
// x: 指の付け根→先 y: 関節の近さ z: 表面に沿う割合 w: いちばん強くつく指（無ければ -1）
in vec4 aInfo;
// 同じものを握った手の絵の上で測った値
in vec4 aClawSkin;
in float aClawThumb;
in vec4 aClawInfo;
uniform mat4 uView;
uniform mat4 uProj;
uniform vec3 uHandC;
uniform vec3 uHandS;
uniform float uSize;
uniform vec2 uAnchor;
uniform vec2 uTurn;
uniform float uPx;
uniform vec4 uFan;
uniform float uFanThumb;
uniform float uLift;
uniform float uSink;
uniform float uPalmZ;
// 握った手の形への寄せ具合・握った手の絵の混ぜ具合と、巻き付けを弱める割合
uniform float uMorph;
uniform float uBlend;
uniform float uFlatten;
// 握った手の絵での指の付け根（hand_morph で解くので、起動を遅くしないよう作るときに渡す）
uniform vec2 uClawKnuckle[5];
// 指の軸（紙の上の付け根・向き）。親指・人差し指・中指・薬指・小指
uniform vec4 uAxis[5];
// 指先の方が丸みから浮き始める所（付け根からの紙の長さ）と、表面に沿う割合
uniform float uStiffFrom[5];
uniform float uStiffCurl;
out vec2 vTex;
out vec2 vClawTex;
out float vFacing;
out float vAlong;
out float vKnuckle;
"""
    + GRIP_SHAPE_GLSL
    + f"""
const vec2 PALM = vec2({HAND_PALM[0]:.1f}, {HAND_PALM[1]:.1f});
const vec2 KNUCKLE[5] = vec2[5]({_vec2_list([k for k, _t, _h in FINGERS])});
const float ARM_RISE = {ARM_RISE:.4f};
const float ARM_RISE_MAX = {ARM_RISE_MAX:.4f};
const float STIFF_STEP = {STIFF_STEP:.4f};
"""
    + """
// 素材の画素は下が正なので、正の角度で画面の右回りに回る
vec2 turnAbout(vec2 p, vec2 pivot, float a) {
    vec2 d = p - pivot;
    float c = cos(a);
    float s = sin(a);
    return pivot + vec2(c * d.x - s * d.y, s * d.x + c * d.y);
}

// 網目の点 base を、指へのつき方（skin・thumb、info は aInfo と同じ並び）に従って置く。
// world は世界の位置、戻り値は向き（正面 1・輪郭 0・裏 -1）
float place(vec2 base, vec4 skin, float thumb, vec4 info, out vec3 world) {
    float fingers = skin.x + skin.y + skin.z + skin.w + thumb;
    vec2 img = base * (1.0 - fingers)
        + turnAbout(base, mix(KNUCKLE[0], uClawKnuckle[0], uMorph), uFanThumb) * thumb
        + turnAbout(base, mix(KNUCKLE[1], uClawKnuckle[1], uMorph), uFan.x) * skin.x
        + turnAbout(base, mix(KNUCKLE[2], uClawKnuckle[2], uMorph), uFan.y) * skin.y
        + turnAbout(base, mix(KNUCKLE[3], uClawKnuckle[3], uMorph), uFan.z) * skin.z
        + turnAbout(base, mix(KNUCKLE[4], uClawKnuckle[4], uMorph), uFan.w) * skin.w;
    vec2 local = vec2(img.x - PALM.x, PALM.y - img.y) * uPx;
    vec2 f = uAnchor + vec2(uTurn.x * local.x - uTurn.y * local.y,
                            uTurn.y * local.x + uTurn.x * local.y);
    // 指は厚みのぶん表面から浮き、握ると指先ほど心臓へ沈む
    float lift = uLift - uSink * fingers * (0.3 + 0.7 * info.x);
    vec4 onBody = gripWrap(f, lift);
    float facing = onBody.w;
    // 指は筒なので、輪郭の所で真横から見ても細くならない。指の幅を画面の面へ起こす
    if (info.w > -0.5) {
        int id = int(info.w + 0.5);
        vec4 axis = uAxis[id];
        float s = dot(f - axis.xy, axis.zw);
        vec2 fc = axis.xy + axis.zw * s;
        vec4 center = gripWrap(fc, lift);
        vec3 d = onBody.xyz - center.xyz;
        float rl = length(center.xy);
        vec2 outward = rl > 1e-5 ? center.xy / rl : vec2(0.0);
        vec2 upright = d.xy - d.z * outward;
        float ul = length(upright);
        vec2 across = ul > 1e-6 ? upright * (length(d) / ul) : vec2(0.0);
        vec3 tube = vec3(center.xy + across, center.z);
        // 付け根の近く（手の甲や親指の股につながる所）では起こさない。隣の指と起こす軸が違うので、
        // 起こしたままだと境目で網目が折り返してぎざぎざの筋が出る。握った手の絵は指の丸みまで
        // 描いてあり、指どうしが接していて境目で起こす軸が入れ替わるので、絵が替わるほど起こさない
        float own = id == 0 ? thumb : dot(skin, vec4(id == 1, id == 2, id == 3, id == 4));
        float c = own * smoothstep(0.15, 0.45, info.x) * (1.0 - uBlend);
        onBody.xyz = mix(onBody.xyz, tube, c);
        facing = mix(facing, center.w, c);
        // 指の途中から先は丸みに貼り付かず、接線の方へ浮く（grip_pose.finger_point と同じ式）
        float start = uStiffFrom[id];
        if (id > 0 && s > start) {
            vec2 fa = axis.xy + axis.zw * start;
            vec4 a = gripWrap(fa, lift);
            vec4 b = gripWrap(fa + axis.zw * STIFF_STEP, lift);
            vec3 line = a.xyz + (b.xyz - a.xyz) * ((s - start) / STIFF_STEP);
            float lifted = (1.0 - uStiffCurl) * own;
            onBody.xyz += (line - center.xyz) * lifted;
            facing = mix(facing, a.w, lifted);
        }
    }
    // 手首から下は平らなまま、下へ行くほど見ている人の側へ寄る
    float rise = min(ARM_RISE * max(uAnchor.y - f.y, 0.0), ARM_RISE_MAX);
    vec3 flatPart = vec3(f, uPalmZ + rise) * uSize;
    float k = info.z * (1.0 - uFlatten);
    world = uHandC + mix(flatPart, onBody.xyz * uHandS, k);
    return mix(1.0, facing, k);
}

void main() {
    vec2 base = mix(aImg, aClaw, uMorph);
    vec3 world;
    float facing = place(base, aSkin, aThumb, aInfo, world);
    // 握った手の絵へ替わるほど、握った手の絵の上で測ったつき方で置く。開いた手から握った手への
    // 写しは指の縁で折れ返って網目が重なる所があり、開いた手のつき方のままだと重なった網目が
    // 別々の指と動いてずれ、ぎざぎざに見える（握った手の絵の同じ所なら同じに動く）
    if (uBlend > 0.0) {
        vec3 clawWorld;
        float clawFacing = place(base, aClawSkin, aClawThumb, aClawInfo, clawWorld);
        world = uBlend < 1.0 ? mix(world, clawWorld, uBlend) : clawWorld;
        facing = uBlend < 1.0 ? mix(facing, clawFacing, uBlend) : clawFacing;
    }
    vTex = aTex;
    vClawTex = aClawTex;
    vFacing = facing;
    vAlong = mix(aInfo.x, aClawInfo.x, uBlend);
    vKnuckle = mix(aInfo.y, aClawInfo.y, uBlend);
    gl_Position = uProj * uView * vec4(world, 1.0);
}
"""
)

# 握ったときに関節が白む量と、指先が赤らむ量（強すぎると肌の色が変わりすぎて見える）
KNUCKLE_PALE = 0.18
TIP_FLUSH = 0.25

_FRAGMENT = f"""
#version 130
const float KNUCKLE_PALE = {KNUCKLE_PALE:.3f};
const float TIP_FLUSH = {TIP_FLUSH:.3f};
in vec2 vTex;
in vec2 vClawTex;
in float vFacing;
in float vAlong;
in float vKnuckle;
uniform sampler2D uTex;
uniform sampler2D uClawTex;
// 握った手の絵の混ぜ具合
uniform float uBlend;
uniform float uOpacity;
uniform float uGrip;
uniform float uBehind;
out vec4 fragColor;
void main() {{
    // 素材は不透明さを掛けた色で持つ（縮めた画の縁が暗くにじまない）
    vec4 c = mix(texture(uTex, vTex), texture(uClawTex, vClawTex), uBlend);
    // 2 枚の絵を混ぜている途中は、片方の絵にしか無い所（伸ばした指先など）が半透明の幽霊に
    // ならないよう、不透明さをはっきり分ける。混ぜ始めと終わりは元の縁のなめらかさのまま
    float swap = 4.0 * uBlend * (1.0 - uBlend);
    float alpha = mix(c.a, smoothstep(0.3, 0.7, c.a), swap);
    c = c.a > 1e-4 ? vec4(c.rgb / c.a, 1.0) * alpha : vec4(0.0);
    if (c.a < 0.004) {{
        discard;
    }}
    // 表面に沿って奥へ向かうほど暗い
    vec3 rgb = c.rgb * mix(0.45, 1.0, smoothstep(-0.25, 0.85, vFacing));
    // 握ると関節が白み、指先に血がたまって赤らむ
    rgb = mix(rgb, vec3(1.0, 0.95, 0.92) * c.a, KNUCKLE_PALE * uGrip * vKnuckle);
    rgb *= mix(vec3(1.0), vec3(1.0, 0.74, 0.70), TIP_FLUSH * uGrip * vAlong * vAlong);
    // 心臓の向こうへ回った所は、心臓越しに淡く青白く透けて見える。握った手の絵は指の曲がりが
    // 描いてあるので、縁の際の指先までは透かさない
    float behind = 1.0 - smoothstep(-0.12, 0.03, vFacing + 0.15 * uBlend);
    float lum = dot(rgb, vec3(0.30, 0.55, 0.15));
    rgb = mix(rgb, vec3(0.60, 0.70, 0.84) * lum, 0.65 * behind);
    float keep = mix(1.0, uBehind, behind) * uOpacity;
    fragColor = vec4(rgb, c.a) * keep;
}}
"""

# 心臓の裏へ回った指の見え方（透けるレントゲンの心臓越しの淡さ）。透けない心臓では隠す
BEHIND_ALPHA = 0.30


class HandRendererError(RuntimeError):
    """手の絵・シェーダー・バッファの準備に失敗した。"""


def build_hand_mesh() -> array:
    """網目の三角形の頂点（_ATTRIBUTES の並び）。"""
    width, height = HAND_IMAGE_SIZE
    claw_lines = claw_fingers()
    grid: list[tuple[float, ...]] = []
    rows: list[float] = [height * j / _ROWS for j in range(_ROWS + 1)]
    rows += [height + _TAIL_EXTEND * j / _TAIL_ROWS for j in range(1, _TAIL_ROWS + 1)]
    for v in rows:
        for i in range(_COLS + 1):
            u = width * i / _COLS
            # 素材の下端より下は、袖の向きに沿って下端の行を伸ばす
            shear = ARM_SLOPE * max(0.0, v - TAIL_V)
            weights, along, knuckle, main = (
                skin(u, v) if v < _SKIN_LIMIT_V else ((0.0,) * 5, 0.0, 0.0, -1)
            )
            cu, cv = claw_point(u, v)
            claw_weights, claw_along, claw_knuckle, claw_main = (
                skin(cu, cv, claw_lines) if cv < _SKIN_LIMIT_V else ((0.0,) * 5, 0.0, 0.0, -1)
            )
            # 開いた手の人差し指は関節で少し曲げておく（握った手の絵へ寄るほど薄れる）
            bu, bv = bend_index(u, v, weights[1])
            grid.append(
                (
                    bu + shear,
                    bv,
                    cu + shear,
                    cv,
                    u / width,
                    min(v, TAIL_V) / height,
                    cu / width,
                    min(cv, TAIL_V) / height,
                    weights[1],
                    weights[2],
                    weights[3],
                    weights[4],
                    weights[0],
                    along,
                    knuckle,
                    wrap_weight(v),
                    float(main),
                    claw_weights[1],
                    claw_weights[2],
                    claw_weights[3],
                    claw_weights[4],
                    claw_weights[0],
                    claw_along,
                    claw_knuckle,
                    wrap_weight(cv),
                    float(claw_main),
                )
            )
    vertices = array("f")
    stride = _COLS + 1
    for j in range(len(rows) - 1):
        for i in range(_COLS):
            a = j * stride + i
            c = a + stride
            for k in (a, c, a + 1, a + 1, c, c + 1):
                vertices.extend(grid[k])
    return vertices


def _premultiplied_texture(image: QImage) -> QOpenGLTexture:
    """不透明さを掛けた色で GPU へ載せる（縮めて描いても縁に暗いにじみが出ない）。"""
    premul = image.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    # 掛け済みの画素をそのまま載せたいので、掛けていない形式として読み直す（変換させない）
    raw = QImage(
        bytes(premul.constBits()),
        premul.width(),
        premul.height(),
        premul.bytesPerLine(),
        QImage.Format.Format_RGBA8888,
    ).copy()
    texture = QOpenGLTexture(raw, QOpenGLTexture.MipMapGeneration.GenerateMipMaps)
    if not texture.isCreated():
        raise HandRendererError("手の絵を GPU へ載せられません")
    texture.setMinMagFilters(QOpenGLTexture.Filter.LinearMipMapLinear, QOpenGLTexture.Filter.Linear)
    texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
    return texture


class HandRenderer:
    """現在のコンテキストで手を描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions, image: QImage, claw_image: QImage) -> None:
        if image.isNull() or claw_image.isNull():
            raise HandRendererError("手の絵がありません")
        self._gl = functions
        self._program = QOpenGLShaderProgram()
        stage = QOpenGLShader.ShaderTypeBit
        if not self._program.addShaderFromSourceCode(stage.Vertex, glsl(_VERTEX)):
            raise HandRendererError(f"頂点シェーダー: {self._program.log()}")
        if not self._program.addShaderFromSourceCode(stage.Fragment, glsl(_FRAGMENT)):
            raise HandRendererError(f"断片シェーダー: {self._program.log()}")
        for index, (name, _offset, _size) in enumerate(_ATTRIBUTES):
            self._program.bindAttributeLocation(name, index)
        if not self._program.link():
            raise HandRendererError(f"リンク: {self._program.log()}")
        self._program.bind()
        for i, ((kx, ky), _tip) in enumerate(claw_fingers()):
            self._program.setUniformValue(
                self._program.uniformLocation(f"uClawKnuckle[{i}]"), QVector2D(kx, ky)
            )
        self._program.release()
        self._texture = _premultiplied_texture(image)
        self._claw_texture = _premultiplied_texture(claw_image)
        vertices = build_hand_mesh()
        self._count = len(vertices) // _FLOATS
        self._vao = QOpenGLVertexArrayObject()
        if not self._vao.create():
            raise HandRendererError("頂点配列を作れません")
        self._vao.bind()
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        if not self._vbo.create() or not self._vbo.bind():
            raise HandRendererError("頂点バッファを作れません")
        payload = vertices.tobytes()
        self._vbo.allocate(payload, len(payload))
        stride = _FLOATS * 4
        for index, (_name, offset, size) in enumerate(_ATTRIBUTES):
            self._program.enableAttributeArray(index)
            self._program.setAttributeBuffer(index, GL_FLOAT, offset * 4, size, stride)
        self._vao.release()

    def draw(
        self,
        *,
        width: int,
        height: int,
        pose: HandPose,
        lift: float,
        opacity: float,
        see_through: bool = True,
    ) -> None:
        """lift は heart_gl と同じ（画面の上へ寄せる量）。

        see_through は心臓が透けるか（レントゲン）。透けない心臓では、裏へ回った所を描かない。
        """
        gl = self._gl
        view, proj, _cam = camera_matrices(width, height, lift)
        program = self._program
        gl.glViewport(0, 0, width, height)
        # 手の中の前後（表の指と、心臓の裏へ回った指先）を奥行きで描き分ける
        gl.glClear(GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        gl.glDepthMask(True)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        self._vao.bind()
        program.bind()
        gl.glActiveTexture(GL_TEXTURE0 + 1)
        self._claw_texture.bind()
        gl.glActiveTexture(GL_TEXTURE0)
        self._texture.bind()
        program.setUniformValue1i("uTex", 0)
        program.setUniformValue1i("uClawTex", 1)
        program.setUniformValue("uView", view)
        program.setUniformValue("uProj", proj)
        program.setUniformValue("uHandC", QVector3D(*pose.center))
        program.setUniformValue("uHandS", QVector3D(*pose.body))
        program.setUniformValue1f("uSize", float(pose.size))
        program.setUniformValue("uAnchor", QVector2D(*pose.anchor))
        program.setUniformValue("uTurn", QVector2D(math.cos(pose.turn), math.sin(pose.turn)))
        program.setUniformValue1f("uPx", float(pose.px))
        thumb, *rest = pose.fan
        program.setUniformValue("uFan", QVector4D(*rest))
        program.setUniformValue1f("uFanThumb", float(thumb))
        program.setUniformValue1f("uLift", float(pose.lift))
        program.setUniformValue1f("uSink", float(pose.sink))
        program.setUniformValue1f("uPalmZ", float(pose.palm_z))
        program.setUniformValue1f("uMorph", float(pose.morph))
        program.setUniformValue1f("uBlend", float(pose.blend))
        program.setUniformValue1f("uFlatten", float(pose.flatten))
        for i, axis in enumerate(pose.finger_axes()):
            program.setUniformValue(program.uniformLocation(f"uAxis[{i}]"), QVector4D(*axis))
        for i, (bx, by, ex, ey, _half) in enumerate(pose.segments()):
            start = STIFF_FROM * math.hypot(ex - bx, ey - by)
            program.setUniformValue1f(program.uniformLocation(f"uStiffFrom[{i}]"), start)
        program.setUniformValue1f("uStiffCurl", float(pose.stiff_curl()))
        program.setUniformValue1f("uOpacity", float(max(0.0, min(1.0, opacity))))
        program.setUniformValue1f("uGrip", float(pose.grip))
        program.setUniformValue1f("uBehind", BEHIND_ALPHA if see_through else 0.0)
        gl.glDrawArrays(GL_TRIANGLES, 0, self._count)
        gl.glActiveTexture(GL_TEXTURE0 + 1)
        self._claw_texture.release()
        gl.glActiveTexture(GL_TEXTURE0)
        self._texture.release()
        program.release()
        self._vao.release()
        gl.glDisable(GL_DEPTH_TEST)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
