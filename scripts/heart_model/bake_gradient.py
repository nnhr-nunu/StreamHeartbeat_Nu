"""Blender の心臓（material/data/blend/心臓_v04.blend）から、アプリで使う画像を 2 つ書き出す。

- gradient_bake.png: グラデの波模様の色。模様は UV だけで決まるので、心臓の UV の範囲と同じ板に
  同じ材質を貼って真上から撮る（このファイルでは Blender の「焼き付け」が通らないため）。
  画の上が UV の v の大きい側
- glass_env.png: ガラスの映り込みに使う、ワールドの環境画像を 512×256 に縮めたもの

出力先は material/build/（git 管理外）。.blend は保存しない。リポジトリの直下で実行:
  & "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b
    material\\data\\blend\\心臓_v04.blend --python scripts\\heart_model\\bake_gradient.py
"""
import os

import bpy

OUT = os.path.normpath(os.path.join(os.path.dirname(bpy.data.filepath), "..", "..", "build"))
os.makedirs(OUT, exist_ok=True)
scene = bpy.context.scene

for o in bpy.data.objects:
    o.hide_render = True

# 心臓の UV は 0〜1 の外まで広がっている。その範囲ぴったりの板を作り、UV を位置と同じにする。
# 真上から撮った画が、convert_glb.py の詰めた UV（範囲を 0〜1 に直したもの）でそのまま引ける
uvs = bpy.data.objects["グラデ"].data.uv_layers.active.data
u_min = min(d.uv[0] for d in uvs)
u_max = max(d.uv[0] for d in uvs)
v_min = min(d.uv[1] for d in uvs)
v_max = max(d.uv[1] for d in uvs)
print("uv range", u_min, u_max, v_min, v_max)
bpy.ops.mesh.primitive_plane_add(size=1.0)
plane = bpy.context.active_object
plane.hide_render = False
corners = {(-0.5, -0.5): (u_min, v_min), (0.5, -0.5): (u_max, v_min),
           (-0.5, 0.5): (u_min, v_max), (0.5, 0.5): (u_max, v_max)}
for vert in plane.data.vertices:
    vert.co.x, vert.co.y = corners[(round(vert.co.x, 1), round(vert.co.y, 1))]
for loop in plane.data.loops:
    co = plane.data.vertices[loop.vertex_index].co
    plane.data.uv_layers.active.data[loop.index].uv = (co.x, co.y)

mat = bpy.data.materials["グラデ.001"].copy()
nt = mat.node_tree
emit = nt.nodes.new("ShaderNodeEmission")
nt.links.new(nt.nodes["カラーランプ"].outputs["Color"], emit.inputs["Color"])
nt.links.new(emit.outputs["Emission"], nt.nodes["マテリアル出力"].inputs["Surface"])
plane.data.materials.clear()
plane.data.materials.append(mat)

cam = bpy.data.objects.new("bake_cam", bpy.data.cameras.new("bake_cam"))
cam.data.type = "ORTHO"
u_span, v_span = u_max - u_min, v_max - v_min
cam.data.ortho_scale = max(u_span, v_span)
cam.location = ((u_min + u_max) / 2, (v_min + v_max) / 2, 2.0)
scene.collection.objects.link(cam)
scene.camera = cam

env = next((n.image for n in scene.world.node_tree.nodes if n.type == "TEX_ENVIRONMENT"), None)

scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.cycles.device = "CPU"
scene.render.resolution_x = round(1024 * u_span / max(u_span, v_span)) * 2
scene.render.resolution_y = round(1024 * v_span / max(u_span, v_span)) * 2
scene.render.resolution_percentage = 100
scene.world = None
# ランプの色をそのまま残す（Blender の AgX の色味はアプリのシェーダー側で合わせる）
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(OUT, "gradient_bake.png")
bpy.ops.render.render(write_still=True)
print("baked", scene.render.filepath)

if env is not None:
    small = env.copy()
    small.scale(512, 256)
    scene.view_settings.view_transform = "AgX"
    small.save_render(os.path.join(OUT, "glass_env.png"), scene=scene)
    print("env", env.filepath, tuple(env.size))
