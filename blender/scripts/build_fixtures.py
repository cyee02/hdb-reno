"""Build bathroom fixtures (toilet bowls, sinks) from the "fixtures" list in
blender/data/floor_plan.json into the Blender collection "Fixtures".

Run after build_flat.py:
    Blender -b blender/hdb-reno.blend -P blender/scripts/build_flat.py -P blender/scripts/build_fixtures.py
or send via the Blender MCP `execute_blender_code` tool.

Idempotent: only the "Fixtures" collection is deleted and rebuilt.
Each fixture is placed by `at` = plan point (mm) at the middle of its back,
against the wall, and `facing` = which way it faces into the room.
"""
import json
import math
import os

import bpy
import bmesh

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "floor_plan.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "floor_plan.json")
COLLECTION = "Fixtures"

# Plan direction -> rotation about Z (local +X is the fixture's front).
FACING = {"east": 0.0, "north": math.pi / 2, "west": math.pi, "south": -math.pi / 2}


def material(name, rgb, roughness=0.3, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    mat.diffuse_color = (*rgb, 1.0)
    return mat


class Builder:
    """Collects parts in local millimetres, each tagged with a material slot."""

    def __init__(self):
        self.bm = bmesh.new()

    def _tag(self, faces, slot):
        for f in faces:
            f.material_index = slot

    def box(self, x0, y0, z0, x1, y1, z1, slot=0):
        v = [self.bm.verts.new((x / 1000, y / 1000, z / 1000)) for z in (z0, z1)
             for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        idx = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
        self._tag([self.bm.faces.new([v[i] for i in f]) for f in idx], slot)

    def ellipse(self, cx, cy, rx, ry, z0, z1, slot=0, taper=1.0, n=32):
        """Elliptic prism; `taper` scales the bottom ring (bowl/pedestal shapes)."""
        bot, top = [], []
        for k in range(n):
            a = 2 * math.pi * k / n
            c, s = math.cos(a), math.sin(a)
            bot.append(self.bm.verts.new(((cx + rx * taper * c) / 1000, (cy + ry * taper * s) / 1000, z0 / 1000)))
            top.append(self.bm.verts.new(((cx + rx * c) / 1000, (cy + ry * s) / 1000, z1 / 1000)))
        faces = [self.bm.faces.new(list(reversed(bot))), self.bm.faces.new(top)]
        for k in range(n):
            j = (k + 1) % n
            faces.append(self.bm.faces.new((bot[k], bot[j], top[j], top[k])))
        self._tag(faces, slot)

    def to_object(self, name, mats, coll):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in mats:
            me.materials.append(m)
        obj = bpy.data.objects.new(name, me)
        coll.objects.link(obj)
        return obj


# Slots: 0 ceramic, 1 water/dark basin, 2 chrome, 3 vanity, 4 mirror

def toilet(b):
    """Close-coupled floor-mounted WC, ~400 W x 700 D x 800 H."""
    b.box(0, -190, 380, 190, 190, 790)            # cistern
    b.box(-5, -200, 790, 200, 200, 820)           # cistern lid
    b.box(165, -15, 760, 185, 15, 775, slot=2)    # flush button
    b.ellipse(400, 0, 150, 120, 0, 300, taper=0.75)  # pedestal
    b.ellipse(430, 0, 260, 185, 300, 400, taper=0.85)  # bowl
    b.ellipse(430, 0, 265, 190, 400, 425)          # seat
    b.ellipse(450, 0, 170, 115, 425, 428, slot=1)  # seat opening


def sink(b):
    """Wall-hung vanity with a counter-top basin, tap and mirror, ~600 W x 470 D."""
    b.box(0, -300, 200, 450, 300, 820, slot=3)     # vanity cabinet
    b.box(0, -310, 820, 470, 310, 850)             # counter
    b.ellipse(270, 0, 170, 230, 850, 970, taper=0.7)  # basin
    b.ellipse(270, 0, 145, 205, 970, 973, slot=1)  # basin inside
    b.box(40, -18, 850, 76, 18, 1090, slot=2)      # tap body
    b.box(40, -15, 1055, 170, 15, 1085, slot=2)    # spout
    b.box(0, -300, 1150, 15, 300, 1900, slot=4)    # mirror


BUILDERS = {"toilet": toilet, "sink": sink}


def reset_collection(name):
    coll = bpy.data.collections.get(name)
    if coll:
        for obj in list(coll.all_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def main():
    with open(DATA) as f:
        plan = json.load(f)
    coll = reset_collection(COLLECTION)
    mats = [
        material("Fixture_Ceramic", (0.95, 0.95, 0.94), roughness=0.15),
        material("Fixture_Basin", (0.62, 0.66, 0.70), roughness=0.1),
        material("Fixture_Chrome", (0.80, 0.80, 0.82), roughness=0.15, metallic=1.0),
        material("Fixture_Vanity", (0.55, 0.42, 0.30), roughness=0.5),
        material("Fixture_Mirror", (0.85, 0.90, 0.92), roughness=0.02, metallic=1.0),
    ]
    counts = {}
    for fx in plan.get("fixtures", []):
        kind = fx["type"]
        b = Builder()
        BUILDERS[kind](b)
        counts[fx["room"]] = counts.get(fx["room"], 0) + 1
        name = f"{kind.title()}_{fx['room']}"
        obj = b.to_object(name, mats, coll)
        x, y = fx["at"]
        obj.location = (x / 1000, -y / 1000, 0.01)  # sits on the floor finish
        obj.rotation_euler = (0, 0, FACING[fx["facing"]])
        obj["room"] = fx["room"]
        print(f"  {name} at {fx['at']} facing {fx['facing']}")
    print(f"Built '{COLLECTION}' with {len(coll.objects)} objects")


main()
