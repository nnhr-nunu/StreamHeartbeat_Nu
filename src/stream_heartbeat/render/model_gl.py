"""Blender の心臓を OpenGL で描く。HeartRenderer が「リアル1」の見た目のときに呼ぶ。

カメラ・拡大・回転・握りつぶしは heart_gl と同じ決め方。Blender の形は最初から体の向きに
なっているので、heart_gl の解剖の傾きは足さない。手の凹みと断面は無い。
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys
from collections.abc import Callable

from PySide6.QtGui import QImage, QMatrix4x4, QOpenGLFunctions, QVector3D
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.gl_platform import glsl
from stream_heartbeat.render.grip_pose import BODY_CENTER
from stream_heartbeat.render.heart_shaders import Look
from stream_heartbeat.render.model_mesh import (
    ENV_PATH,
    GRADIENT_PATH,
    ModelMesh,
    beat_weights,
    load_model_mesh,
)
from stream_heartbeat.render.model_shaders import (
    MATERIAL_GLASS,
    MATERIAL_INDEX,
    MATERIAL_REAL,
    MODEL_FRAGMENT,
    MODEL_VERTEX,
)

GL_TRIANGLES = 0x0004
GL_SHORT = 0x1402
GL_UNSIGNED_SHORT = 0x1403
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_FRONT = 0x0404
GL_BACK = 0x0405
GL_LEQUAL = 0x0203
GL_MULTISAMPLE = 0x809D
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_ONE = 0x0001
GL_DEPTH_BUFFER_BIT = 0x0100

# (名前, 詰めたブロック, 成分の数, 型, 1 頂点の長さ)。形・法線・キーは 16 bit を 4 つずつ
_ATTRIBUTES = (
    ("aPos", "pos", 3, GL_SHORT, 8),
    ("aNormal", "normal", 3, GL_SHORT, 8),
    ("aUv", "uv", 2, GL_UNSIGNED_SHORT, 4),
    ("aKey0", "delta0", 3, GL_SHORT, 8),
    ("aKey1", "delta1", 3, GL_SHORT, 8),
    ("aKey2", "delta2", 3, GL_SHORT, 8),
    ("aCavity", "cavity", 2, GL_SHORT, 4),
)
# Blender の心臓の胴（太い血管より下）の真ん中。形の座標で y が 0.3 より下の頂点の範囲から測った値
# （半分の幅・高さは 0.87・0.74。heart_shaders の MODEL_LOOK の大きさをこれで決めた）
MODEL_BODY_CENTER = (0.0, -0.44, 0.0)
# ガラスの映り込みで、スタジオの明かりが右上に来る向き（ラジアン）
ENV_YAW = 2.4


class ModelRendererError(RuntimeError):
    """シェーダー・バッファ・画像の準備に失敗した。"""


def _gl_library() -> ctypes.CDLL:
    if sys.platform == "win32":
        return ctypes.WinDLL("opengl32")
    if sys.platform == "darwin":
        return ctypes.CDLL("/System/Library/Frameworks/OpenGL.framework/OpenGL")
    return ctypes.CDLL(ctypes.util.find_library("GL") or "libGL.so.1")


_DRAW_ELEMENTS: Callable[..., None] | None = None


def _draw_function() -> Callable[..., None]:
    """OS の OpenGL の glDrawElements。

    PySide6 の glDrawElements は、番号のバッファの中の位置（先頭の 0）を渡せない（整数の 0 を
    弾き、ほかの型はメモリの場所として渡る）。OS の関数を直接呼び、空のポインタで渡す。
    """
    global _DRAW_ELEMENTS
    if _DRAW_ELEMENTS is None:
        try:
            func = _gl_library().glDrawElements
        except (OSError, AttributeError) as exc:
            raise ModelRendererError("OpenGL の描画の関数が見つかりません") from exc
        func.argtypes = (ctypes.c_uint, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p)
        func.restype = None
        _DRAW_ELEMENTS = func
    return _DRAW_ELEMENTS


def _draw_elements(count: int) -> None:
    """今つないでいる番号のバッファの先頭から、count 個の番号で三角形を描く。"""
    _draw_function()(GL_TRIANGLES, count, GL_UNSIGNED_SHORT, None)


def _texture(path: object, what: str, *, wrap_x: bool = False) -> QOpenGLTexture:
    """wrap_x は横につながった画像（ぐるりと一周する映り込み）。左右の端で継ぎ目を出さない。"""
    image = QImage(str(path))
    if image.isNull():
        raise ModelRendererError(f"{what}を読めません")
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    texture = QOpenGLTexture(image, QOpenGLTexture.MipMapGeneration.GenerateMipMaps)
    if not texture.isCreated():
        raise ModelRendererError(f"{what}を GPU へ載せられません")
    texture.setMinMagFilters(QOpenGLTexture.Filter.LinearMipMapLinear, QOpenGLTexture.Filter.Linear)
    texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
    if wrap_x:
        across = QOpenGLTexture.CoordinateDirection.DirectionS
        texture.setWrapMode(across, QOpenGLTexture.WrapMode.Repeat)
    return texture


class ModelRenderer:
    """現在のコンテキストで Blender の心臓を描く。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions, mesh: ModelMesh | None = None) -> None:
        self._gl = functions
        self._mesh = mesh if mesh is not None else load_model_mesh()
        _draw_function()
        self._program = QOpenGLShaderProgram()
        stage = QOpenGLShader.ShaderTypeBit
        if not self._program.addShaderFromSourceCode(stage.Vertex, glsl(MODEL_VERTEX)):
            raise ModelRendererError(f"頂点シェーダー: {self._program.log()}")
        if not self._program.addShaderFromSourceCode(stage.Fragment, glsl(MODEL_FRAGMENT)):
            raise ModelRendererError(f"断片シェーダー: {self._program.log()}")
        for index, (name, *_rest) in enumerate(_ATTRIBUTES):
            self._program.bindAttributeLocation(name, index)
        if not self._program.link():
            raise ModelRendererError(f"リンク: {self._program.log()}")

        mesh = self._mesh
        self._vao = QOpenGLVertexArrayObject()
        if not self._vao.create():
            raise ModelRendererError("頂点配列を作れません")
        self._vao.bind()
        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._ibo = QOpenGLBuffer(QOpenGLBuffer.Type.IndexBuffer)
        if not self._vbo.create() or not self._vbo.bind():
            raise ModelRendererError("頂点バッファを作れません")
        start = mesh.offsets["index"]
        self._vbo.allocate(mesh.payload[:start], start)
        # 16 bit の整数は GPU が -1〜1（UV は 0〜1）に直して読む（Qt は正規化して渡す）
        self._program.bind()
        for index, (_name, block, size, kind, stride) in enumerate(_ATTRIBUTES):
            self._program.enableAttributeArray(index)
            self._program.setAttributeBuffer(index, kind, mesh.offsets[block], size, stride)
        self._program.release()
        if not self._ibo.create() or not self._ibo.bind():
            raise ModelRendererError("番号のバッファを作れません")
        indices = mesh.payload[start : start + mesh.index_count * 2]
        self._ibo.allocate(indices, len(indices))
        self._vao.release()
        self._gradient = _texture(GRADIENT_PATH, "グラデの画像")
        self._env = _texture(ENV_PATH, "映り込みの画像", wrap_x=True)

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
        squash_x: float = 1.0,
        squash_y: float = 1.0,
        lift: float = 0.0,
    ) -> None:
        # heart_gl が先に読み込まれている（循環を避けてここで読む）
        from stream_heartbeat.render.heart_gl import BASE_SCALE, camera_matrices

        gl = self._gl
        program = self._program
        mesh = self._mesh
        model = QMatrix4x4()
        model.translate(look.shift_x, look.shift_y, 0.0)
        model.scale(squash_x, squash_y, 1.0)
        model.scale(BASE_SCALE * max(0.05, scale) * look.size_factor)
        # 胴の真ん中を、作った心臓の胴の真ん中（手や聴診器の置き場所の基準）へ置き、そこで回す
        model.translate(*BODY_CENTER)
        model.rotate(pitch_deg + look.pitch_offset_deg, 1.0, 0.0, 0.0)
        model.rotate(yaw_deg + look.yaw_offset_deg, 0.0, 1.0, 0.0)
        model.translate(*(-c for c in MODEL_BODY_CENTER))
        view, proj, cam = camera_matrices(width, height, lift)
        material = look.material if look.material in MATERIAL_INDEX else MATERIAL_REAL
        weights = beat_weights(mesh, cycle.age, cycle.interval)

        gl.glViewport(0, 0, width, height)
        gl.glEnable(GL_MULTISAMPLE)
        gl.glClear(GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_BLEND)
        gl.glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        gl.glDepthMask(True)
        gl.glEnable(GL_CULL_FACE)

        self._vao.bind()
        program.bind()
        self._gradient.bind(0)
        self._env.bind(1)
        program.setUniformValue1i("uGradient", 0)
        program.setUniformValue1i("uEnv", 1)
        program.setUniformValue("uModel", model)
        program.setUniformValue("uNormalMat", model.normalMatrix())
        program.setUniformValue("uView", view)
        program.setUniformValue("uProj", proj)
        program.setUniformValue("uCamPos", cam)
        program.setUniformValue("uPosScale", QVector3D(*mesh.pos_scale))
        program.setUniformValue("uKeyScale", QVector3D(*mesh.delta_scales[:3]))
        program.setUniformValue("uWeights", QVector3D(*weights[:3]))
        program.setUniformValue1i("uMaterial", MATERIAL_INDEX[material])
        program.setUniformValue1f("uOpacity", float(max(0.0, min(1.0, opacity))))
        program.setUniformValue1f("uPulse", float(cycle.squeeze))
        program.setUniformValue1f("uEnvYaw", ENV_YAW)
        if material == MATERIAL_GLASS:
            # 奥の面を先に描き、手前の面を重ねる（中の血管の凹凸が透けて見える）
            gl.glCullFace(GL_FRONT)
            _draw_elements(mesh.index_count)
        gl.glCullFace(GL_BACK)
        _draw_elements(mesh.index_count)
        self._env.release(1)
        self._gradient.release(0)
        program.release()
        self._vao.release()
        gl.glDisable(GL_CULL_FACE)
        gl.glDisable(GL_DEPTH_TEST)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
