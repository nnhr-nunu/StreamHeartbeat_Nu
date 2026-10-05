"""レントゲン4 の肋骨を描く。Blender の心臓（model_gl）の周りに、同じ座標・同じ置き方で重ねる。

肋骨は窓より大きいので、心臓から離れるほど薄れて消える（窓の端で切れて見えない）。
材質は X 線（硬い外側が縁で厚く写る）とガラス（素通しの映り込み）。X 線は心臓と同じく
背景に重ねる 2 回描き（model_shaders の XRAY_OUT_GLSL）。ガラスは心臓より奥と手前に分けて描き、
奥の骨 → 心臓 → 手前の骨の順に重ねる。
"""

from __future__ import annotations

from PySide6.QtGui import QMatrix4x4, QOpenGLFunctions, QVector3D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)

from stream_heartbeat.render.gl_platform import glsl
from stream_heartbeat.render.heart_looks import Look
from stream_heartbeat.render.heart_shaders import _NOISE
from stream_heartbeat.render.model_mesh import RibcageMesh, load_ribcage_mesh
from stream_heartbeat.render.model_shaders import SHADING_GLSL, XRAY_OUT_GLSL

GL_SHORT = 0x1402
# 薄れ始め・消える所を決める楕円の真ん中と半径（形の座標。心臓の胴の少し上を真ん中に、縦に長め）。
# 半径の 0.55 倍から薄れ始め、半径で消える
BONE_FADE_CENTER = (0.0, -0.25, 0.0)
BONE_FADE_RADIUS = (2.3, 2.3, 2.3)
# 骨を描き分ける: 全部 / 心臓より奥だけ / 心臓より手前だけ（ガラスの重なりの順）
SIDE_ALL = 0
SIDE_BEHIND = 1
SIDE_FRONT = 2

_ATTRIBUTES = (("aPos", "pos"), ("aNormal", "normal"))

BONE_VERTEX = """
#version 130
in vec3 aPos;
in vec3 aNormal;

uniform mat4 uModel;
uniform mat3 uNormalMat;
uniform mat4 uView;
uniform mat4 uProj;
uniform vec3 uPosScale;

out vec3 vWorldPos;
out vec3 vObjPos;
out vec3 vNormal;

void main() {
    vec3 p = aPos * uPosScale;
    vec4 world = uModel * vec4(p, 1.0);
    vWorldPos = world.xyz;
    vObjPos = p;
    vNormal = normalize(uNormalMat * aNormal);
    gl_Position = uProj * uView * world;
}
"""

BONE_FRAGMENT = (
    """
#version 130
in vec3 vWorldPos;
in vec3 vObjPos;
in vec3 vNormal;

uniform vec3 uCamPos;
// 0: X 線 / 1: ガラス
uniform int uMaterial;
uniform float uOpacity;
uniform sampler2D uEnv;
uniform float uEnvYaw;
uniform vec3 uFadeCenter;
uniform vec3 uFadeRadius;
uniform int uSide;
uniform vec3 uSplitPoint;
uniform vec3 uSplitDir;

out vec4 fragColor;
"""
    + _NOISE
    + SHADING_GLSL
    + XRAY_OUT_GLSL
    + """
void main() {
    // 心臓の真ん中を通り視線に垂直な面で、奥と手前に分ける（正がカメラ側）
    float side = dot(vWorldPos - uSplitPoint, uSplitDir);
    if ((uSide == 1 && side >= 0.0) || (uSide == 2 && side < 0.0)) {
        discard;
    }
    float fade = 1.0 - smoothstep(0.55, 1.0, length((vObjPos - uFadeCenter) / uFadeRadius));
    if (fade <= 0.0) {
        discard;
    }
    vec3 n = normalize(vNormal);
    vec3 v = normalize(uCamPos - vWorldPos);
    if (!gl_FrontFacing) n = -n;
    if (uMaterial == 1) {
        // 素通しのガラス（Blender: 白・IOR 1.33・Alpha 0.51・つるつる）。心臓より色を付けない。
        // 真ん中は透かし、縁を白く光らせて形を見せる（スタジオの映り込みは暗く、そのままでは濁る）
        float f = fresnelIor(dot(n, v), 1.33);
        float rim = pow(1.0 - abs(dot(n, v)), 2.5);
        vec3 refl = envAt(reflect(-v, n));
        vec3 refr = envAt(refract(-v, n, 1.0 / 1.33));
        vec3 color = mix(refr * 1.2 + vec3(0.10, 0.12, 0.16), refl * 2.4, f);
        color += vec3(0.75, 0.88, 1.0) * rim * 0.8;
        vec3 warm = normalize(vec3(0.55, 0.5, 0.65));
        vec3 cool = normalize(vec3(-0.7, 0.25, 0.6));
        color += vec3(1.0, 0.86, 0.72) * pow(max(0.0, dot(n, normalize(warm + v))), 200.0) * 1.6;
        color += vec3(0.6, 0.75, 1.0) * pow(max(0.0, dot(n, normalize(cool + v))), 160.0) * 1.0;
        float alpha = clamp(0.08 + 0.75 * rim + 0.5 * f, 0.0, 1.0);
        fragColor = vec4(softTone(color), alpha * fade * uOpacity);
        return;
    }
    // X 線: 骨は硬い外側（皮質）を縁で長く通るので、輪郭が明るく真ん中は淡い
    float facing = abs(dot(n, v));
    float d = 0.06 + 0.24 * pow(1.0 - facing, 1.5);
    d *= xrayGrain(vWorldPos) * fade;
    fragColor = xrayOut(d, 1.0, uOpacity);
}
"""
)


class BoneRendererError(RuntimeError):
    """肋骨のシェーダー・バッファの準備に失敗した。"""


class BoneRenderer:
    """現在のコンテキストで肋骨を描く。作成時にカレントなコンテキストが必要。

    GL の重ね方（混ぜ方・奥行き・裏面）は呼ぶ側（model_gl）が決める。
    """

    def __init__(self, functions: QOpenGLFunctions, mesh: RibcageMesh | None = None) -> None:
        self._gl = functions
        self._mesh = mesh if mesh is not None else load_ribcage_mesh()
        self._program = QOpenGLShaderProgram()
        stage = QOpenGLShader.ShaderTypeBit
        if not self._program.addShaderFromSourceCode(stage.Vertex, glsl(BONE_VERTEX)):
            raise BoneRendererError(f"頂点シェーダー: {self._program.log()}")
        if not self._program.addShaderFromSourceCode(stage.Fragment, glsl(BONE_FRAGMENT)):
            raise BoneRendererError(f"断片シェーダー: {self._program.log()}")
        for index, (name, _block) in enumerate(_ATTRIBUTES):
            self._program.bindAttributeLocation(name, index)
        if not self._program.link():
            raise BoneRendererError(f"リンク: {self._program.log()}")

        mesh = self._mesh
        self._vao = QOpenGLVertexArrayObject()
        if not self._vao.create():
            raise BoneRendererError("頂点配列を作れません")
        self._vao.bind()
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._ibo = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
        if not self._vbo.create() or not self._vbo.bind():
            raise BoneRendererError("頂点バッファを作れません")
        start = mesh.offsets["index"]
        self._vbo.allocate(mesh.payload[:start], start)
        self._program.bind()
        for index, (_name, block) in enumerate(_ATTRIBUTES):
            self._program.enableAttributeArray(index)
            self._program.setAttributeBuffer(index, GL_SHORT, mesh.offsets[block], 3, 8)
        self._program.release()
        if not self._ibo.create() or not self._ibo.bind():
            raise BoneRendererError("番号のバッファを作れません")
        indices = mesh.payload[start : start + mesh.index_count * 2]
        self._ibo.allocate(indices, len(indices))
        self._vao.release()

    def draw(
        self,
        *,
        model: QMatrix4x4,
        view: QMatrix4x4,
        proj: QMatrix4x4,
        cam: QVector3D,
        look: Look,
        glass: bool,
        opacity: float,
        time_s: float,
        env: QOpenGLTexture,
        env_yaw: float,
        cutout: float = 0.0,
        side: int = SIDE_ALL,
        split: tuple[QVector3D, QVector3D] | None = None,
        cull: tuple[int, ...] = (),
    ) -> None:
        """cutout は X 線の何回目か（1: 下を隠す / 2: 色を足す）。split は分ける面（点・向き）。

        cull は描く前に裏返す面の並び（ガラスは奥の面 → 手前の面の 2 回）。空なら 1 回だけ描く。
        """
        # model_gl は肋骨より先に読み込まれている（循環を避けてここで読む）
        from stream_heartbeat.render.model_gl import _draw_elements

        gl = self._gl
        program = self._program
        point, direction = split if split is not None else (QVector3D(), QVector3D(0.0, 0.0, 1.0))
        self._vao.bind()
        program.bind()
        env.bind(1)
        program.setUniformValue1i("uEnv", 1)
        program.setUniformValue1f("uEnvYaw", env_yaw)
        program.setUniformValue("uModel", model)
        program.setUniformValue("uNormalMat", model.normalMatrix())
        program.setUniformValue("uView", view)
        program.setUniformValue("uProj", proj)
        program.setUniformValue("uCamPos", cam)
        program.setUniformValue("uPosScale", QVector3D(*self._mesh.pos_scale))
        program.setUniformValue1i("uMaterial", 1 if glass else 0)
        program.setUniformValue1f("uOpacity", float(max(0.0, min(1.0, opacity))))
        program.setUniformValue("uFadeCenter", QVector3D(*BONE_FADE_CENTER))
        program.setUniformValue("uFadeRadius", QVector3D(*BONE_FADE_RADIUS))
        program.setUniformValue1i("uSide", side)
        program.setUniformValue("uSplitPoint", point)
        program.setUniformValue("uSplitDir", direction)
        program.setUniformValue("uTintDense", QVector3D(*look.tint_dense))
        program.setUniformValue("uTintThin", QVector3D(*look.tint_thin))
        program.setUniformValue1f("uGrain", float(look.grain))
        program.setUniformValue1f("uTime", float(time_s % 3600.0))
        program.setUniformValue1f("uCutout", float(cutout))
        if cull:
            for face in cull:
                gl.glCullFace(face)
                _draw_elements(self._mesh.index_count)
        else:
            _draw_elements(self._mesh.index_count)
        env.release(1)
        program.release()
        self._vao.release()
