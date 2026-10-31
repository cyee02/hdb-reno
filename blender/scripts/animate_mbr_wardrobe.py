"""Keyframe the main-bedroom wardrobe demo: bi-folds fold + slide to their parking end,
the pull-out baskets slide out one after another, hold, slide back, doors close.

Uses the same scene["door_<id>"] values as the HDB Reno tab, so "Clear Animation" in that
tab removes it. Run after build_main_bedroom.py (design with "bracket_wardrobe"):
    Blender -b blender/hdb-reno.blend -P blender/scripts/animate_mbr_wardrobe.py
Set env RENDER_ANIM=1 to also render it to blender/renders/<RENDER_TAG>_mbr_wardrobe_anim.mp4
from the scene camera "Cam_mbr_wardrobe" (or the "mbr_wardrobe" view in scene["room_cameras"]).
"""
import json
import os

import bpy
from mathutils import Vector

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
FPS = 24
DOORS_OPEN = (1, 36)       # frames: doors fold away
BASKET_START, BASKET_STEP, BASKET_MOVE = 44, 10, 18
HOLD_UNTIL = 132
DOORS_CLOSE = (180, 216)


def door_fcurves(scene):
    ad = scene.animation_data
    if not ad or not ad.action or not getattr(ad, "action_slot", None):
        return []
    out = []
    for layer in ad.action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(ad.action_slot)
            if bag:
                out += [(bag, fc) for fc in bag.fcurves if fc.data_path.startswith('["door_')]
    return out


def key(scene, gid, frame, value):
    scene[f"door_{gid}"] = float(value)
    scene.keyframe_insert(data_path=f'["door_{gid}"]', frame=frame)


def main():
    scene = bpy.context.scene
    groups = json.loads(scene.get("hdb_doors", "{}"))
    meta = json.loads(scene.get("hdb_door_meta", "{}"))
    pairs = sorted(g for g in groups if g.startswith("wardrobe_"))
    baskets = sorted(g for g in groups if g.startswith("basket_"))
    if not pairs and not baskets:
        raise SystemExit("No wardrobe doors / baskets - run build_main_bedroom.py first")
    for bag, fc in door_fcurves(scene):
        bag.fcurves.remove(fc)
    for gid in groups:                     # every other door stays put (closed) during the demo
        if gid not in pairs and gid not in baskets:
            scene[f"door_{gid}"] = 0.0

    n = len(baskets)
    back_in = HOLD_UNTIL
    for k, gid in enumerate(pairs):        # doors open, pairs staggered slightly
        to = float(meta.get(gid, {}).get("open_to", 1))
        key(scene, gid, DOORS_OPEN[0], 0)
        key(scene, gid, DOORS_OPEN[1] - 6 + 2 * k, to)
        key(scene, gid, DOORS_CLOSE[0] + 2 * k, to)
        key(scene, gid, DOORS_CLOSE[1], 0)
    for k, gid in enumerate(baskets):      # top basket first out, last back
        j = n - 1 - k
        t0 = BASKET_START + j * BASKET_STEP
        key(scene, gid, 1, 0)
        key(scene, gid, t0, 0)
        key(scene, gid, t0 + BASKET_MOVE, 1)
        r0 = back_in + k * BASKET_STEP
        key(scene, gid, r0, 1)
        key(scene, gid, r0 + BASKET_MOVE, 0)
    scene.frame_start, scene.frame_end = 1, DOORS_CLOSE[1] + 12
    scene.render.fps = FPS
    scene.frame_set(1)
    print(f"[wardrobe anim] keyframed {len(pairs)} bi-fold pairs + {n} baskets, frames 1-{scene.frame_end}")

    if os.environ.get("RENDER_ANIM"):
        render(scene)


def render(scene):
    cam = bpy.data.objects.get("Cam_mbr_wardrobe")
    if not cam:
        c = json.loads(scene.get("room_cameras", "{}"))["mbr_wardrobe"]
        cam = bpy.data.objects.new("Cam_mbr_wardrobe", bpy.data.cameras.new("Cam_mbr_wardrobe"))
        scene.collection.objects.link(cam)
        cam.location = Vector(c["loc"])
        cam.data.lens = c.get("lens", 14)
        cam.rotation_euler = (Vector(c["target"]) - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 1280, 800
    scene.render.resolution_percentage = 100
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 16
    fmt = scene.render.image_settings
    if hasattr(fmt, "media_type"):          # Blender 5.x: pick "video" before the FFMPEG format
        fmt.media_type = "VIDEO"
    fmt.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    tag = os.environ.get("RENDER_TAG", "v001")
    root = HDB_RENO_ROOT
    scene.render.filepath = os.path.join(root, "blender", "renders", f"{tag}_mbr_wardrobe_anim.mp4")
    bpy.ops.render.render(animation=True)
    print(f"[wardrobe anim] rendered {scene.render.filepath}")


main()
