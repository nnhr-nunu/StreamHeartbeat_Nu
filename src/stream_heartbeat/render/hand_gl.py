"""心臓わしづかみの手を OpenGL で描く。

手の絵を細かい網目にして、頂点シェーダーで指を開き、心臓の胴へ巻き付ける（grip_pose と同じ式）。
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
    TAIL_V,
    HandPose,
    skin,
    wrap_weight,
)
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
    ("aTex", 2, 2),
    ("aSkin", 4, 4),
    ("aThumb", 8, 1),
    ("aInfo", 9, 4),
)
_FLOATS = 13


def _vec2_list(points: list[tuple[float, float]]) -> str:
    return ", ".join(f"vec2({x:.1f}, {y:.1f})" for x, y in points)


_VERTEX = (
    """
#version 130
in vec2 aImg;
in vec2 aTex;
// 人差し指・中指・薬指・小指・親指へのつき方
in vec4 aSkin;
in float aThumb;
// x: 指の付け根→先 y: 関節の近さ z: 表面に沿う割合 w: いちばん強くつく指（無ければ -1）
in vec4 aInfo;
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
// 指の軸（紙の上の付け根・向き）。親指・人差し指・中指・薬指・小指
uniform vec4 uAxis[5];
out vec2 vTex;
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
"""
    + """
// 素材の画素は下が正なので、正の角度で画面の右回りに回る
vec2 turnAbout(vec2 p, vec2 pivot, float a) {
    vec2 d = p - pivot;
    float c = cos(a);
    float s = sin(a);
    return pivot + vec2(c * d.x - s * d.y, s * d.x + c * d.y);
}

void main() {
    float fingers = aSkin.x + aSkin.y + aSkin.z + aSkin.w + aThumb;
    vec2 img = aImg * (1.0 - fingers)
        + turnAbout(aImg, KNUCKLE[0], uFanThumb) * aThumb
        + turnAbout(aImg, KNUCKLE[1], uFan.x) * aSkin.x
        + turnAbout(aImg, KNUCKLE[2], uFan.y) * aSkin.y
        + turnAbout(aImg, KNUCKLE[3], uFan.z) * aSkin.z
        + turnAbout(aImg, KNUCKLE[4], uFan.w) * aSkin.w;
    vec2 local = vec2(img.x - PALM.x, PALM.y - img.y) * uPx;
    vec2 f = uAnchor + vec2(uTurn.x * local.x - uTurn.y * local.y,
                            uTurn.y * local.x + uTurn.x * local.y);
    // 指は厚みのぶん表面から浮き、握ると指先ほど心臓へ沈む
    float lift = uLift - uSink * fingers * (0.3 + 0.7 * aInfo.x);
    vec4 onBody = gripWrap(f, lift);
    float facing = onBody.w;
    // 指は筒なので、輪郭の所で真横から見ても細くならない。指の幅を画面の面へ起こす
    if (aInfo.w > -0.5) {
        int id = int(aInfo.w + 0.5);
        vec4 axis = uAxis[id];
        vec2 fc = axis.xy + axis.zw * dot(f - axis.xy, axis.zw);
        vec4 center = gripWrap(fc, lift);
        vec3 d = onBody.xyz - center.xyz;
        float rl = length(center.xy);
        vec2 outward = rl > 1e-5 ? center.xy / rl : vec2(0.0);
        vec2 upright = d.xy - d.z * outward;
        float ul = length(upright);
        vec2 across = ul > 1e-6 ? upright * (length(d) / ul) : vec2(0.0);
        vec3 tube = vec3(center.xy + across, center.z);
        float c = id == 0 ? aThumb : dot(aSkin, vec4(id == 1, id == 2, id == 3, id == 4));
        onBody.xyz = mix(onBody.xyz, tube, c);
        facing = mix(facing, center.w, c);
    }
    // 手首から下は平らなまま、下へ行くほど見ている人の側へ寄る
    float rise = min(ARM_RISE * max(uAnchor.y - f.y, 0.0), ARM_RISE_MAX);
    vec3 flatPart = vec3(f, uPalmZ + rise) * uSize;
    float k = aInfo.z;
    vec3 world = uHandC + mix(flatPart, onBody.xyz * uHandS, k);
    vTex = aTex;
    vFacing = mix(1.0, facing, k);
    vAlong = aInfo.x;
    vKnuckle = aInfo.y;
    gl_Position = uProj * uView * vec4(world, 1.0);
}
"""
)

_FRAGMENT = """
#version 130
in vec2 vTex;
in float vFacing;
in float vAlong;
in float vKnuckle;
uniform sampler2D uTex;
uniform float uOpacity;
uniform float uGrip;
uniform float uBehind;
out vec4 fragColor;
void main() {
    // 素材は不透明さを掛けた色で持つ（縮めた画の縁が暗くにじまない）
    vec4 c = texture(uTex, vTex);
    if (c.a < 0.004) {
        discard;
    }
    // 表面に沿って奥へ向かうほど暗い
    vec3 rgb = c.rgb * mix(0.45, 1.0, smoothstep(-0.25, 0.85, vFacing));
    // 握ると関節が白み、指先に血がたまって赤らむ
    rgb = mix(rgb, vec3(1.0, 0.95, 0.92) * c.a, 0.38 * uGrip * vKnuckle);
    rgb *= mix(vec3(1.0), vec3(1.0, 0.74, 0.70), 0.5 * uGrip * vAlong * vAlong);
    // 心臓の向こうへ回った所は、心臓越しに淡く青白く透けて見える
    float behind = 1.0 - smoothstep(-0.12, 0.03, vFacing);
    float lum = dot(rgb, vec3(0.30, 0.55, 0.15));
    rgb = mix(rgb, vec3(0.60, 0.70, 0.84) * lum, 0.65 * behind);
    float keep = mix(1.0, uBehind, behind) * uOpacity;
    fragColor = vec4(rgb, c.a) * keep;
}
"""

# 心臓の裏へ回った指の見え方（心臓越しの淡さ）
BEHIND_ALPHA = 0.30


class HandRendererError(RuntimeError):
    """手の絵・シェーダー・バッファの準備に失敗した。"""


def build_hand_mesh() -> array:
    """網目の三角形の頂点（_ATTRIBUTES の並び）。"""
    width, height = HAND_IMAGE_SIZE
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
            grid.append(
                (
                    u + shear,
                    v,
                    u / width,
                    min(v, TAIL_V) / height,
                    weights[1],
                    weights[2],
                    weights[3],
                    weights[4],
                    weights[0],
                    along,
                    knuckle,
                    wrap_weight(v),
                    float(main),
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

    def __init__(self, functions: QOpenGLFunctions, image: QImage) -> None:
        if image.isNull():
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
        self._texture = _premultiplied_texture(image)
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
    ) -> None:
        """lift は heart_gl と同じ（画面の上へ寄せる量）。"""
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
        gl.glActiveTexture(GL_TEXTURE0)
        self._texture.bind()
        program.setUniformValue1i("uTex", 0)
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
        for i, axis in enumerate(pose.finger_axes()):
            program.setUniformValue(program.uniformLocation(f"uAxis[{i}]"), QVector4D(*axis))
        program.setUniformValue1f("uOpacity", float(max(0.0, min(1.0, opacity))))
        program.setUniformValue1f("uGrip", float(pose.grip))
        program.setUniformValue1f("uBehind", BEHIND_ALPHA)
        gl.glDrawArrays(GL_TRIANGLES, 0, self._count)
        self._texture.release()
        program.release()
        self._vao.release()
        gl.glDisable(GL_DEPTH_TEST)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
