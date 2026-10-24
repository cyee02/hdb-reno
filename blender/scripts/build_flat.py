"""Build the flat's 3D shell from blender/data/floor_plan.json.

Run headless:
    Blender -b -P blender/scripts/build_flat.py
or paste into Blender (or send via the Blender MCP `execute_blender_code` tool).

Idempotent: deletes and rebuilds the "Flat" collection only. Other collections
(e.g. Furniture) are left untouched.
"""
import json
import math
import os

import bpy
import bmesh

# Fallback for when the script is run without __file__ (Blender text editor / MCP).
HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")

try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "floor_plan.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "floor_plan.json")
BLEND = os.path.join(ROOT, "blender", "hdb-reno.blend")
COLLECTION = "Flat"


def mm(v):
    return v / 1000.0


def to_xy(px, py):
    """Plan coords (mm, y down) -> Blender coords (m, y up)."""
    return mm(px), -mm(py)


# ---------- scene helpers ----------

def reset_collection(name):
    coll = bpy.data.collections.get(name)
    if coll:
        for obj in list(coll.all_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for child in list(coll.children_recursive):
            bpy.data.collections.remove(child)
    else:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def sub_collection(parent, name):
    c = bpy.data.collections.new(f"{parent.name}.{name}")
    parent.children.link(c)
    return c


def material(name, rgb, alpha=1.0, roughness=0.6):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Alpha"].default_value = alpha
    mat.diffuse_color = (*rgb, alpha)
    if alpha < 1.0:
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, val)
                except TypeError:
                    pass
    return mat


def add_box(bm, x0, y0, x1, y1, z0, z1):
    """Add an axis-aligned box to bmesh; inputs in plan mm (y down) and z mm."""
    ax0, ay0 = to_xy(min(x0, x1), max(y0, y1))
    ax1, ay1 = to_xy(max(x0, x1), min(y0, y1))
    z0, z1 = mm(z0), mm(z1)
    vs = [bm.verts.new(c) for c in (
        (ax0, ay0, z0), (ax1, ay0, z0), (ax1, ay1, z0), (ax0, ay1, z0),
        (ax0, ay0, z1), (ax1, ay0, z1), (ax1, ay1, z1), (ax0, ay1, z1))]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([vs[i] for i in f])


def mesh_object(name, bm, mat, coll):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.data.materials.append(mat)
    coll.objects.link(obj)
    return obj


# ---------- builders ----------

def wall_boxes(bm, wall, defaults):
    """Split a straight axis-aligned wall into solid pieces around its openings."""
    (x0, y0), (x1, y1) = wall["from"], wall["to"]
    t = wall["thickness"]
    h = wall.get("height", defaults["ceiling_height"])
    horizontal = abs(y1 - y0) < 1e-6
    a, b = (x0, x1) if horizontal else (y0, y1)
    a, b = min(a, b), max(a, b)
    a -= t / 2  # extend into corners so walls meet cleanly
    b += t / 2
    fixed = y0 if horizontal else x0

    def box(s, e, z0, z1):
        if e - s <= 0 or z1 - z0 <= 0:
            return
        if horizontal:
            add_box(bm, s, fixed - t / 2, e, fixed + t / 2, z0, z1)
        else:
            add_box(bm, fixed - t / 2, s, fixed + t / 2, e, z0, z1)

    cursor = a
    for op in sorted(wall.get("openings", []), key=lambda o: o["at"][0]):
        s, e = op["at"]
        box(cursor, s, 0, h)
        if op["type"] == "window":
            box(s, e, 0, op.get("sill", defaults["window_sill"]))
            box(s, e, op.get("head", defaults["window_head"]), h)
        else:
            box(s, e, op.get("head", defaults["door_height"]), h)
        cursor = e
    box(cursor, b, 0, h)
    return horizontal, fixed


def build_walls(plan, coll, mats):
    d = plan["defaults"]
    walls_c = sub_collection(coll, "Walls")
    open_c = sub_collection(coll, "Openings")
    for wall in plan["walls"]:
        bm = bmesh.new()
        horizontal, fixed = wall_boxes(bm, wall, d)
        mat = mats["wall_ext"] if wall.get("side") == "out" else mats["wall"]
        mesh_object(f"Wall_{wall['id']}", bm, mat, walls_c)

        for i, op in enumerate(wall.get("openings", [])):
            s, e = op["at"]
            if op["type"] == "window":
                bm = bmesh.new()
                z0 = op.get("sill", d["window_sill"])
                z1 = op.get("head", d["window_head"])
                g = 10
                if horizontal:
                    add_box(bm, s, fixed - g, e, fixed + g, z0, z1)
                else:
                    add_box(bm, fixed - g, s, fixed + g, e, z0, z1)
                mesh_object(f"Glass_{wall['id']}_{i}", bm, mats["glass"], open_c)
            else:
                # Door leaf drawn open at 90 degrees from its hinge side.
                w = e - s
                hinge = s if op.get("hinge", "start") == "start" else e
                sw = op.get("swing", 1)
                leaf_t = 40
                z1 = op.get("head", d["door_height"])
                bm = bmesh.new()
                off = wall["thickness"] / 2
                if horizontal:
                    hx = hinge + (leaf_t if hinge == s else -leaf_t) / 2
                    y_a = fixed + sw * off
                    add_box(bm, hx - leaf_t / 2, y_a, hx + leaf_t / 2, y_a + sw * w, 0, z1)
                else:
                    hy = hinge + (leaf_t if hinge == s else -leaf_t) / 2
                    x_a = fixed + sw * off
                    add_box(bm, x_a, hy - leaf_t / 2, x_a + sw * w, hy + leaf_t / 2, 0, z1)
                mat = mats["door_main"] if op.get("main") else mats["door"]
                mesh_object(f"Door_{wall['id']}_{i}", bm, mat, open_c)

    for ledge in plan.get("ledges", []):
        bm = bmesh.new()
        wall_boxes(bm, {**ledge, "openings": []}, d)
        mesh_object(f"Ledge_{ledge['id']}", bm, mats["wall_ext"], walls_c)


def build_floors(plan, coll, mats):
    floors_c = sub_collection(coll, "Floors")
    labels_c = sub_collection(coll, "Labels")
    xs, ys = [], []
    for room in plan["rooms"]:
        bm = bmesh.new()
        area = 0.0
        for x0, y0, x1, y1 in room["rects"]:
            add_box(bm, x0, y0, x1, y1, 0, 10)
            area += (x1 - x0) * (y1 - y0) / 1e6
            xs += [x0, x1]
            ys += [y0, y1]
        mat = material(f"Floor_{room['name']}", tuple(room["color"]), roughness=0.8)
        obj = mesh_object(f"Floor_{room['name']}", bm, mat, floors_c)
        obj["area_m2"] = round(area, 2)
        print(f"  {room['name']:<20} {area:6.2f} m2")

        lx, ly = to_xy(*room["label_at"])
        curve = bpy.data.curves.new(f"Label_{room['name']}", "FONT")
        curve.body = f"{room.get('label', room['name']).upper()}\n{area:.1f} m²"
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.size = 0.28
        txt = bpy.data.objects.new(f"Label_{room['name']}", curve)
        txt.location = (lx, ly, 0.02)
        txt.data.materials.append(mats["label"])
        labels_c.objects.link(txt)

    # Base slab under everything.
    bm = bmesh.new()
    add_box(bm, min(xs) - 600, min(ys) - 600, max(xs) + 600, max(ys) + 600, -200, 0)
    mesh_object("Slab", bm, mats["slab"], coll)


def main():
    with open(DATA) as f:
        plan = json.load(f)

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "METERS"

    # Remove default startup objects (cube, light, camera) on a fresh file.
    for name in ("Cube", "Light", "Camera"):
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)

    coll = reset_collection(COLLECTION)
    mats = {
        "wall": material("Wall_Internal", (0.96, 0.96, 0.94)),
        "wall_ext": material("Wall_External", (0.85, 0.85, 0.83)),
        "glass": material("Glass", (0.6, 0.8, 0.95), alpha=0.25, roughness=0.05),
        "door": material("Door", (0.55, 0.38, 0.22), roughness=0.5),
        "door_main": material("Door_Main", (0.30, 0.20, 0.12), roughness=0.4),
        "label": material("Label", (0.08, 0.08, 0.08)),
        "slab": material("Slab", (0.35, 0.35, 0.36)),
    }
    print("Room areas:")
    build_floors(plan, coll, mats)
    build_walls(plan, coll, mats)

    if bpy.app.background:
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
        print(f"Saved {BLEND}")
    print(f"Built '{COLLECTION}' with {len(coll.all_objects)} objects")


main()
