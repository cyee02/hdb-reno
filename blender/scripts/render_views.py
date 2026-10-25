"""Set up cameras + lighting and render standard views to blender/renders/.

Run after build_flat.py:
    Blender -b -P blender/scripts/build_flat.py -P blender/scripts/render_views.py
Set env RENDER_TAG (default v001) to version the output filenames.
"""
import math
import os

import bpy
from mathutils import Vector

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
except NameError:
    ROOT = HDB_RENO_ROOT
OUT = os.path.join(ROOT, "blender", "renders")
TAG = os.environ.get("RENDER_TAG", "v001")

CENTER = Vector((7.45, -4.45, 0.0))  # middle of the flat in Blender coords (m)


def get_coll(name):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def reset(coll):
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def look_at(obj, target):
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def camera(coll, name, loc, ortho_scale=None, lens=28):
    cam = bpy.data.cameras.new(name)
    if ortho_scale:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho_scale
    else:
        cam.lens = lens
    cam.clip_end = 200
    obj = bpy.data.objects.new(name, cam)
    obj.location = loc
    coll.objects.link(obj)
    return obj


def setup_engine(scene):
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    print(f"Render engine: {scene.render.engine}")
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1200
    scene.render.film_transparent = False
    if hasattr(scene, "eevee"):
        for attr, val in (("taa_render_samples", 32), ("use_shadows", True), ("use_raytracing", False)):
            if hasattr(scene.eevee, attr):
                setattr(scene.eevee, attr, val)
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Filmic"

    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
    bg.inputs["Strength"].default_value = 0.45


def main():
    scene = bpy.context.scene
    setup_engine(scene)
    coll = get_coll("Cameras")
    reset(coll)

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(35), math.radians(10), math.radians(-30))
    coll.objects.link(sun)

    views = {
        "topdown": camera(coll, "Cam_TopDown", CENTER + Vector((0, 0, 30)), ortho_scale=17.5),
        "persp_south": camera(coll, "Cam_PerspSouth", CENTER + Vector((-1.0, -10.0, 15.0)), lens=24),
        "persp_north": camera(coll, "Cam_PerspNorth", CENTER + Vector((1.0, 10.0, 15.0)), lens=24),
    }
    # Service yard close-ups from the ceiling corners: storage wall, then laundry side.
    views["yard_storage"] = camera(coll, "Cam_YardStorage", Vector((9.85, -6.52, 2.35)), lens=14)
    views["yard_laundry"] = camera(coll, "Cam_YardLaundry", Vector((9.8, -8.05, 2.4)), lens=13)
    views["topdown"].rotation_euler = (0, 0, 0)
    look_at(views["persp_south"], CENTER)
    look_at(views["persp_north"], CENTER)
    look_at(views["yard_storage"], Vector((9.05, -8.55, 0.75)))
    look_at(views["yard_laundry"], Vector((8.95, -6.75, 0.5)))

    os.makedirs(OUT, exist_ok=True)
    for key, cam in views.items():
        scene.camera = cam
        scene.render.filepath = os.path.join(OUT, f"{TAG}_{key}.png")
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {scene.render.filepath}")

    scene.camera = views["persp_south"]
    if bpy.app.background and bpy.data.filepath:
        bpy.ops.wm.save_mainfile()


main()
