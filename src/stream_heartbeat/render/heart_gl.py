"""立体心臓を OpenGL で描く。ウィンドウでもオフスクリーンでも同じ経路。"""

from __future__ import annotations

import math

from PySide6.QtGui import (
    QColor,
    QImage,
    QMatrix4x4,
    QOffscreenSurface,
    QOpenGLContext,
    QOpenGLFunctions,
    QVector3D,
)
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.heart_mesh import FLOATS_PER_VERTEX, HeartMesh, build_heart_mesh
from stream_heartbeat.render.heart_shaders import VERTEX, Look, fragment_source

GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_ONE = 0x0001
GL_BACK = 0x0405
GL_DEPTH_BUFFER_BIT = 0x0100
GL_COLOR_BUFFER_BIT = 0x4000
GL_LEQUAL = 0x0203
GL_MULTISAMPLE = 0x809D

ANATOMY_ROLL_DEG = 34.0
ANATOMY_YAW_DEG = -22.0
CAMERA_DISTANCE = 4.6
FOV_DEG = 30.0
BASE_SCALE = 1.05

_ATTRIBUTES = (
    ("aPos", 0, 3),
    ("aNormal", 3, 3),
    ("aRegion", 6, 1),
    ("aFat", 7, 1),
    ("aAxial", 8, 1),
    ("aUv", 9, 2),
)


class HeartRendererError(RuntimeError):
    """シェーダーやバッファの準備に失敗した。"""


class HeartRenderer:
    """現在のコンテキストで心臓メッシュを描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions, mesh: HeartMesh | None = None) -> None:
        self._gl = functions
        self._mesh = mesh if mesh is not None else build_heart_mesh()
        self._programs: dict[str, QOpenGLShaderProgram] = {}
        self._vao = QOpenGLVertexArrayObject()
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._upload()
        for key in ("flesh", "mech", "scan"):
            self._programs[key] = self._compile(fragment_source(key))

    def _upload(self) -> None:
        if not self._vao.create():
            raise HeartRendererError("頂点配列を作れません")
        self._vao.bind()
        if not self._vbo.create() or not self._vbo.bind():
            raise HeartRendererError("頂点バッファを作れません")
        payload = self._mesh.data.tobytes()
        self._vbo.allocate(payload, len(payload))
        self._vao.release()

    def _compile(self, fragment: str) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram()
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTEX):
            raise HeartRendererError(f"頂点シェーダー: {program.log()}")
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment):
            raise HeartRendererError(f"断片シェーダー: {program.log()}")
        for name, _offset, _size in _ATTRIBUTES:
            program.bindAttributeLocation(name, _ATTRIBUTES.index((name, _offset, _size)))
        if not program.link():
            raise HeartRendererError(f"リンク: {program.log()}")
        return program

    def _bind_attributes(self, program: QOpenGLShaderProgram) -> None:
        stride = FLOATS_PER_VERTEX * 4
        self._vbo.bind()
        for index, (_name, offset, size) in enumerate(_ATTRIBUTES):
            program.enableAttributeArray(index)
            program.setAttributeBuffer(index, GL_FLOAT, offset * 4, size, stride)

    def draw(
        self,
        *,
        width: int,
        height: int,
        cycle: CardiacCycle,
        look: Look,
        yaw_deg: float,
        pitch_deg: float,
        scale: float,
        opacity: float,
        time_s: float,
    ) -> None:
        gl = self._gl
        program = self._programs[look.program]
        model = QMatrix4x4()
        model.scale(BASE_SCALE * max(0.05, scale) * look.size_factor)
        model.rotate(pitch_deg, 1.0, 0.0, 0.0)
        model.rotate(yaw_deg, 0.0, 1.0, 0.0)
        model.rotate(ANATOMY_YAW_DEG, 0.0, 1.0, 0.0)
        model.rotate(ANATOMY_ROLL_DEG, 0.0, 0.0, 1.0)
        view = QMatrix4x4()
        cam = QVector3D(0.0, 0.05, CAMERA_DISTANCE)
        view.lookAt(cam, QVector3D(0.0, 0.05, 0.0), QVector3D(0.0, 1.0, 0.0))
        proj = QMatrix4x4()
        aspect = width / max(1, height)
        proj.perspective(FOV_DEG, aspect, 0.5, 20.0)

        gl.glViewport(0, 0, width, height)
        gl.glEnable(GL_MULTISAMPLE)
        gl.glClear(GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_BLEND)
        if look.additive:
            gl.glDisable(GL_DEPTH_TEST)
            gl.glDisable(GL_CULL_FACE)
            gl.glBlendFunc(GL_ONE, GL_ONE)
        else:
            gl.glEnable(GL_DEPTH_TEST)
            gl.glDepthFunc(GL_LEQUAL)
            gl.glDepthMask(True)
            gl.glEnable(GL_CULL_FACE)
            gl.glCullFace(GL_BACK)
            gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        self._vao.bind()
        program.bind()
        self._bind_attributes(program)
        program.setUniformValue("uModel", model)
        program.setUniformValue("uView", view)
        program.setUniformValue("uProj", proj)
        program.setUniformValue("uCamPos", cam)
        program.setUniformValue1f("uSqueeze", float(cycle.squeeze))
        program.setUniformValue1f("uEject", float(cycle.eject))
        program.setUniformValue1f("uFill", float(cycle.fill))
        program.setUniformValue1f("uTime", float(time_s))
        program.setUniformValue1f("uOpacity", float(max(0.0, min(1.0, opacity))))
        program.setUniformValue1f("uFatAmount", float(look.fat_amount))
        program.setUniformValue1f("uGloss", float(look.gloss))
        program.setUniformValue1f("uSaturation", float(look.saturation))
        if look.program == "scan":
            program.setUniformValue("uTintDense", QVector3D(*look.tint_dense))
            program.setUniformValue("uTintThin", QVector3D(*look.tint_thin))
            program.setUniformValue1f("uGrain", float(look.grain))
            program.setUniformValue1f("uDensity", float(look.density))
        gl.glDrawArrays(GL_TRIANGLES, 0, self._mesh.vertex_count)
        program.release()
        self._vao.release()
        gl.glDisable(GL_CULL_FACE)
        gl.glDisable(GL_DEPTH_TEST)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


class OffscreenHeart:
    """窓なしで心臓を画像にする。確認用。"""

    def __init__(self) -> None:
        self._context = QOpenGLContext()
        if not self._context.create():
            raise HeartRendererError("OpenGL コンテキストを作れません")
        self._surface = QOffscreenSurface()
        self._surface.create()
        if not self._context.makeCurrent(self._surface):
            raise HeartRendererError("オフスクリーン面を使えません")
        self._renderer = HeartRenderer(self._context.functions())

    def render(
        self,
        *,
        width: int,
        height: int,
        cycle: CardiacCycle,
        look: Look,
        yaw_deg: float = 0.0,
        pitch_deg: float = 0.0,
        scale: float = 0.7,
        opacity: float = 1.0,
        time_s: float = 0.0,
        background: QColor | None = None,
    ) -> QImage:
        self._context.makeCurrent(self._surface)
        fbo = QOpenGLFramebufferObject(
            width, height, QOpenGLFramebufferObject.Attachment.CombinedDepthStencil
        )
        fbo.bind()
        gl = self._context.functions()
        bg = background if background is not None else QColor(0, 255, 0)
        gl.glViewport(0, 0, width, height)
        gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._renderer.draw(
            width=width,
            height=height,
            cycle=cycle,
            look=look,
            yaw_deg=yaw_deg,
            pitch_deg=pitch_deg,
            scale=scale,
            opacity=opacity,
            time_s=time_s,
        )
        image = fbo.toImage()
        fbo.release()
        return image


def deg_to_rad(deg: float) -> float:
    return deg * math.pi / 180.0
