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
    QVector4D,
)
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFramebufferObject,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.gl_platform import glsl
from stream_heartbeat.render.grip_pose import HandPose
from stream_heartbeat.render.heart_mesh import (
    ANATOMY_ROLL_DEG,
    FLOATS_PER_VERTEX,
    HeartMesh,
    build_heart_mesh,
)
from stream_heartbeat.render.heart_shaders import VERTEX, Look, fragment_source
from stream_heartbeat.render.poly_mesh import build_poly_mesh

GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_ONE = 0x0001
GL_ZERO = 0x0000
GL_BACK = 0x0405
GL_DEPTH_BUFFER_BIT = 0x0100
GL_COLOR_BUFFER_BIT = 0x4000
GL_LEQUAL = 0x0203
GL_MULTISAMPLE = 0x809D

ANATOMY_YAW_DEG = -22.0
CAMERA_DISTANCE = 4.6
FOV_DEG = 30.0
BASE_SCALE = 1.0
# 首へ昇る血管の先まで収まるよう、少し上を見る
CAMERA_TARGET_Y = 0.16

_ATTRIBUTES = (
    ("aPos", 0, 3),
    ("aNormal", 3, 3),
    ("aRegion", 6, 1),
    ("aFat", 7, 1),
    ("aAxial", 8, 1),
    ("aUv", 9, 2),
    ("aSection", 11, 2),
    ("aMerge", 13, 2),
    ("aAuricle", 15, 1),
    ("aCoronary", 16, 1),
)


def camera_matrices(
    width: int, height: int, lift: float = 0.0
) -> tuple[QMatrix4x4, QMatrix4x4, QVector3D]:
    """心臓を見るカメラ（見る行列・写す行列・カメラの位置）。手も同じカメラで描く。"""
    view = QMatrix4x4()
    cam = QVector3D(0.0, CAMERA_TARGET_Y, CAMERA_DISTANCE)
    view.lookAt(cam, QVector3D(0.0, CAMERA_TARGET_Y, 0.0), QVector3D(0.0, 1.0, 0.0))
    proj = QMatrix4x4()
    # 画面の上でそのまま持ち上げる（見る向きは変えない）。正規化した画面の高さは 2
    proj.translate(0.0, 2.0 * lift, 0.0)
    aspect = width / max(1, height)
    proj.perspective(FOV_DEG, aspect, 0.5, 20.0)
    return view, proj, cam


def set_dent_uniforms(program: QOpenGLShaderProgram, pose: HandPose | None) -> None:
    """心臓のシェーダーへ、掴んでいる指の所を渡す（pose が無ければ凹ませない）。"""
    if pose is None:
        program.setUniformValue1f("uHandOn", 0.0)
        return
    for name, value in pose.dent_uniforms().items():
        location = program.uniformLocation(name)
        if location < 0:
            continue
        if isinstance(value, tuple) and len(value) == 3:
            program.setUniformValue(location, QVector3D(*value))
        elif isinstance(value, tuple) and len(value) == 4:
            program.setUniformValue(location, QVector4D(*value))
        else:
            program.setUniformValue1f(location, float(value))  # type: ignore[arg-type]


class HeartRendererError(RuntimeError):
    """シェーダーやバッファの準備に失敗した。"""


class _MeshBuffer:
    """1 つの形を GPU へ載せたもの。"""

    def __init__(self, mesh: HeartMesh) -> None:
        self.mesh = mesh
        self.vao = QOpenGLVertexArrayObject()
        self.vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        if not self.vao.create():
            raise HeartRendererError("頂点配列を作れません")
        self.vao.bind()
        if not self.vbo.create() or not self.vbo.bind():
            raise HeartRendererError("頂点バッファを作れません")
        payload = mesh.data.tobytes()
        self.vbo.allocate(payload, len(payload))
        self.vao.release()


class HeartRenderer:
    """現在のコンテキストで心臓メッシュを描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions, mesh: HeartMesh | None = None) -> None:
        self._gl = functions
        self._mesh = mesh if mesh is not None else build_heart_mesh()
        self._programs: dict[str, QOpenGLShaderProgram] = {}
        self._heart = _MeshBuffer(self._mesh)
        # ポリゴンの形は選ばれたときに作る（軽いので待たせない）
        self._poly: _MeshBuffer | None = None
        for key in ("flesh", "mech", "scan", "poly"):
            self._programs[key] = self._compile(fragment_source(key))

    def _buffer(self, look: Look) -> _MeshBuffer:
        if look.program != "poly":
            return self._heart
        if self._poly is None:
            self._poly = _MeshBuffer(build_poly_mesh())
        return self._poly

    def _compile(self, fragment: str) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram()
        stage = QOpenGLShader.ShaderTypeBit
        if not program.addShaderFromSourceCode(stage.Vertex, glsl(VERTEX)):
            raise HeartRendererError(f"頂点シェーダー: {program.log()}")
        if not program.addShaderFromSourceCode(stage.Fragment, glsl(fragment)):
            raise HeartRendererError(f"断片シェーダー: {program.log()}")
        for name, _offset, _size in _ATTRIBUTES:
            program.bindAttributeLocation(name, _ATTRIBUTES.index((name, _offset, _size)))
        if not program.link():
            raise HeartRendererError(f"リンク: {program.log()}")
        return program

    def _bind_attributes(self, program: QOpenGLShaderProgram, buffer: _MeshBuffer) -> None:
        stride = FLOATS_PER_VERTEX * 4
        buffer.vbo.bind()
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
        squash_x: float = 1.0,
        squash_y: float = 1.0,
        lift: float = 0.0,
        hand: HandPose | None = None,
    ) -> None:
        """lift は画面の上へずらす量（窓の高さに対する割合）。

        hand は心臓を掴んでいる手の形（指の所が凹む）。
        """
        gl = self._gl
        program = self._programs[look.program]
        model = QMatrix4x4()
        model.translate(look.shift_x, look.shift_y, 0.0)
        # 手で握られて潰れる（画面の横に縮み、縦に伸びる）。心臓の真ん中を中心に潰す
        model.scale(squash_x, squash_y, 1.0)
        model.scale(BASE_SCALE * max(0.05, scale) * look.size_factor)
        model.rotate(pitch_deg + look.pitch_offset_deg, 1.0, 0.0, 0.0)
        model.rotate(yaw_deg + look.yaw_offset_deg, 0.0, 1.0, 0.0)
        model.rotate(ANATOMY_YAW_DEG, 0.0, 1.0, 0.0)
        model.rotate(ANATOMY_ROLL_DEG, 0.0, 0.0, 1.0)
        view, proj, cam = camera_matrices(width, height, lift)

        gl.glViewport(0, 0, width, height)
        gl.glEnable(GL_MULTISAMPLE)
        gl.glClear(GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_BLEND)
        if look.additive:
            gl.glDisable(GL_DEPTH_TEST)
            gl.glDisable(GL_CULL_FACE)
            gl.glBlendFunc(GL_ONE, GL_ONE)
        elif look.cutout:
            gl.glDisable(GL_DEPTH_TEST)
            gl.glDisable(GL_CULL_FACE)
        else:
            gl.glEnable(GL_DEPTH_TEST)
            gl.glDepthFunc(GL_LEQUAL)
            gl.glDepthMask(True)
            # 断面は切って開いた管の内側も見せるので裏面も描く
            if look.section:
                gl.glDisable(GL_CULL_FACE)
            else:
                gl.glEnable(GL_CULL_FACE)
                gl.glCullFace(GL_BACK)
            # 透明な窓でも縁が明るく浮かないよう、アルファは別の式で重ねる
            gl.glBlendFuncSeparate(
                GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA
            )

        buffer = self._buffer(look)
        buffer.vao.bind()
        program.bind()
        self._bind_attributes(program, buffer)
        program.setUniformValue("uModel", model)
        program.setUniformValue("uView", view)
        program.setUniformValue("uProj", proj)
        program.setUniformValue("uCamPos", cam)
        program.setUniformValue1f("uSqueeze", float(cycle.squeeze))
        program.setUniformValue1f("uEject", float(cycle.eject))
        program.setUniformValue1f("uFill", float(cycle.fill))
        # 長時間の配信でも細かい揺らぎが粗くならないよう、小さな値に折り返して渡す
        program.setUniformValue1f("uTime", float(time_s % 3600.0))
        program.setUniformValue1f("uAge", float(cycle.age))
        program.setUniformValue1f("uOpacity", float(max(0.0, min(1.0, opacity))))
        program.setUniformValue1f("uFatAmount", float(look.fat_amount))
        program.setUniformValue1f("uGloss", float(look.gloss))
        program.setUniformValue1f("uSaturation", float(look.saturation))
        program.setUniformValue1f("uCoronary", float(look.coronary))
        program.setUniformValue1f("uLively", float(look.lively))
        program.setUniformValue1f("uAtriaR", float(cycle.atria_r))
        program.setUniformValue1f("uAtriaL", float(cycle.atria_l))
        program.setUniformValue1f("uAurR", float(cycle.auricle_r))
        program.setUniformValue1f("uAurL", float(cycle.auricle_l))
        set_dent_uniforms(program, hand)
        if look.program == "flesh":
            program.setUniformValue1f("uSection", 1.0 if look.section else 0.0)
        if look.program == "scan":
            program.setUniformValue("uTintDense", QVector3D(*look.tint_dense))
            program.setUniformValue("uTintThin", QVector3D(*look.tint_thin))
            program.setUniformValue1f("uGrain", float(look.grain))
            program.setUniformValue1f("uDensity", float(look.density))
            program.setUniformValue1f("uCutout", 0.0)
        mesh = buffer.mesh
        count = mesh.section_end if look.section else mesh.body_vertex_count
        if look.program == "poly":
            # 粗い三角形の形を 1 回で描く（先を透かす血管は無い）
            program.setUniformValue1i("uPass", 0)
            gl.glDrawArrays(GL_TRIANGLES, 0, mesh.vertex_count)
        elif look.cutout:
            # 1 回目: 下の背景を濃さのぶんだけ隠す（透明の窓では不透明さを積む）。
            # 2 回目: 色を足す（不透明さは変えない）
            gl.glBlendFuncSeparate(GL_ZERO, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
            program.setUniformValue1f("uCutout", 1.0)
            gl.glDrawArrays(GL_TRIANGLES, 0, count)
            gl.glBlendFuncSeparate(GL_ONE, GL_ONE, GL_ZERO, GL_ONE)
            program.setUniformValue1f("uCutout", 2.0)
            gl.glDrawArrays(GL_TRIANGLES, 0, count)
        elif look.additive:
            gl.glDrawArrays(GL_TRIANGLES, 0, count)
        else:
            # 不透明な所を先に描き、透けて消えていく血管の先は奥行きを書かずに重ねる
            program.setUniformValue1i("uPass", 0)
            gl.glDrawArrays(GL_TRIANGLES, 0, count)
            if look.lively > 0.0 and mesh.auricle_start >= 0:
                gl.glDrawArrays(
                    GL_TRIANGLES, mesh.auricle_start, mesh.vertex_count - mesh.auricle_start
                )
            gl.glDepthMask(False)
            # 透ける先では管の内側を見せない（断面でも切るのは根元だけ）
            gl.glEnable(GL_CULL_FACE)
            gl.glCullFace(GL_BACK)
            program.setUniformValue1i("uPass", 1)
            tubes = self._mesh.tube_start
            gl.glDrawArrays(GL_TRIANGLES, tubes, self._mesh.body_vertex_count - tubes)
            gl.glDepthMask(True)
        program.release()
        buffer.vao.release()
        gl.glDisable(GL_CULL_FACE)
        gl.glDisable(GL_DEPTH_TEST)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


class OffscreenHeart:
    """窓なしで心臓を画像にする。確認用。"""

    def __init__(self, mesh: HeartMesh | None = None) -> None:
        self._context = QOpenGLContext()
        if not self._context.create():
            raise HeartRendererError("OpenGL コンテキストを作れません")
        self._surface = QOffscreenSurface()
        self._surface.create()
        if not self._context.makeCurrent(self._surface):
            raise HeartRendererError("オフスクリーン面を使えません")
        self._renderer = HeartRenderer(self._context.functions(), mesh)

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
        gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), bg.alphaF())
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
