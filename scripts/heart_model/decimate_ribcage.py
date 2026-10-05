"""肋骨（material/x/骨_X線.glb）の面を減らし、心臓と同じ座標のまま material/build/ に書く。

元は 9 万頂点あり、16 bit の番号に入らない。配信の窓の大きさでは半分以下でも見た目は変わらない。
置き場所・向き・大きさ（GLB の節の変換）は頂点へ焼き込む（アプリは心臓の座標でそのまま描く）。

Blender で裏で実行:
  blender.exe -b --python scripts\\heart_model\\decimate_ribcage.py
続けて venv の Python で convert_glb.py を実行すると assets/heart_model/ribcage.bin ができる。
"""

from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "material" / "x" / "骨_X線.glb"
OUT = ROOT / "material" / "build" / "ribcage.glb"
# 面を残す割合（頂点が 65536 未満になるように）
RATIO = 0.42

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(SOURCE))
meshes = [ob for ob in bpy.data.objects if ob.type == "MESH"]
for ob in meshes:
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for ob in meshes:
    mod = ob.modifiers.new("decimate", "DECIMATE")
    mod.ratio = RATIO
    mod.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.shade_smooth()
    print("頂点", len(ob.data.vertices), "面", len(ob.data.polygons))
OUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=str(OUT),
    export_format="GLB",
    use_selection=True,
    export_texcoords=False,
    export_materials="NONE",
    export_animations=False,
)
