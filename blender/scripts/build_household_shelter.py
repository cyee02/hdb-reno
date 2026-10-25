"""Build the household shelter renovation from blender/data/household_shelter.json.

Creates two collections (rebuilt each run, nothing else touched):
  Carpentry.HouseholdShelter   - free-standing L-shaped rack, whiteboard on the door
  Accessories.HouseholdShelter - kids' bike, luggage, storage boxes (for scale)

Nothing is fixed to the shelter walls, door or ceiling (SCDF rule).

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_household_shelter.py
or send via the Blender MCP `execute_blender_code` tool.
"""
import json
import math
import os

import bpy
import bmesh

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "household_shelter.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "household_shelter.json")


def material(name, rgb, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    mat.diffuse_color = (*rgb, 1.0)
    return mat


class Mesh:
    """Builds geometry in plan millimetres (y down) into Blender metres (Y up)."""

    def __init__(self):
        self.bm = bmesh.new()

    def _v(self, x, y, z):
        return self.bm.verts.new((x / 1000, -y / 1000, z / 1000))

    def _faces(self, rings):
        faces = [self.bm.faces.new(list(reversed(rings[0]))), self.bm.faces.new(rings[1])]
        n = len(rings[0])
        for k in range(n):
            j = (k + 1) % n
            faces.append(self.bm.faces.new((rings[0][k], rings[0][j], rings[1][j], rings[1][k])))

    def box(self, x0, y0, x1, y1, z0, z1):
        if x1 <= x0 or y1 <= y0 or z1 <= z0:
            return
        quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        self._faces([[self._v(x, y, z0) for x, y in quad], [self._v(x, y, z1) for x, y in quad]])

    def cyl_x(self, cy, cz, r, x0, x1, n=24):
        """Cylinder whose axis runs along plan x (wheels, handlebars)."""
        ring = [(cy + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x0, y, z) for y, z in ring], [self._v(x1, y, z) for y, z in ring]])

    def bar_yz(self, x, p0, p1, w, thick=25):
        """Bar in the y-z plane from p0 to p1, `w` thick in-plane, `thick` wide along x."""
        (y0, z0), (y1, z1) = p0, p1
        L = math.hypot(y1 - y0, z1 - z0)
        ny, nz = -(z1 - z0) / L * w / 2, (y1 - y0) / L * w / 2
        quad = [(y0 + ny, z0 + nz), (y1 + ny, z1 + nz), (y1 - ny, z1 - nz), (y0 - ny, z0 - nz)]
        self._faces([[self._v(x - thick / 2, y, z) for y, z in quad],
                     [self._v(x + thick / 2, y, z) for y, z in quad]])

    def finish(self, name, coll, mat):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        me.materials.append(mat)
        obj = bpy.data.objects.new(name, me)
        coll.objects.link(obj)
        return obj


# ---------- carpentry ----------

def rack_unit(unit, r, posts_m, shelves_m):
    """One free-standing bay: 4 posts, shelves from waist height up, low ties on wall sides only."""
    g, p, st = r["gap_to_wall"], r["post"], r["shelf_thickness"]
    x0, y0, x1, y1 = unit["rect"]
    x0, y0, x1, y1 = x0 + g, y0 + g, x1 - g, y1 - g
    top = r["shelves"][-1]
    for px in (x0, x1 - p):
        for py in (y0, y1 - p):
            posts_m.box(px, py, px + p, py + p, 0, top)
    for z in r["shelves"]:
        shelves_m.box(x0, y0, x1, y1, z - st, z)
    # Low ties keep the open bottom square; skipped on the open (front) side.
    tz, th = r["low_tie"], 25
    sides = {"west": (x0, y0, x0 + p, y1), "east": (x1 - p, y0, x1, y1),
             "north": (x0, y0, x1, y0 + p), "south": (x0, y1 - p, x1, y1)}
    for side, (a, b, c, d) in sides.items():
        if side != unit["open_side"]:
            posts_m.box(a, b, c, d, tz - th, tz)


def whiteboard(d, coll, mat):
    """Thin white sheet on the shelter door's outer face.

    build_flat.py draws the door open 90 degrees into the foyer; its outer face then
    faces north (towards the living room) = the leaf's min-y side in plan.
    """
    leaf = bpy.data.objects.get(d["door_leaf"])
    if not leaf:
        print(f"[shelter] {d['door_leaf']} not found - run build_flat.py first")
        return
    xs = [(leaf.matrix_world @ v.co).x * 1000 for v in leaf.data.vertices]
    ys = [-(leaf.matrix_world @ v.co).y * 1000 for v in leaf.data.vertices]
    x0, x1, y0 = min(xs), max(xs), min(ys)
    m = Mesh()
    m.box(x0 + d["inset"], y0 - d["thickness"], x1 - d["inset"], y0, d["bottom"], d["top"])
    m.finish("SH_Whiteboard", coll, mat)


# ---------- accessories ----------

def bike(item, m):
    cx, cy = item["at"]
    r, L, bar = item["wheel"] / 2, item["length"], item["bar_height"]
    rear, front = cy + L / 2 - r, cy - L / 2 + r   # front wheel towards the door end (north)
    for wy in (rear, front):
        m.cyl_x(wy, r, r, cx - 20, cx + 20)
    seat = (rear - 120, 620)
    head = (front + 90, bar - 60)
    bb = ((rear + front) / 2 + 40, r)
    for a, b in ((bb, seat), (bb, head), (seat, head), ((rear, r), bb), ((rear, r), seat),
                 ((front, r), head), (head, (front + 60, bar))):
        m.bar_yz(cx, a, b, 30)
    m.cyl_x(front + 60, bar, 15, cx - 230, cx + 230)        # handlebar
    m.box(cx - 80, seat[0] - 120, cx + 80, seat[0] + 60, seat[1], seat[1] + 50)


def luggage(item, m):
    x0, y0, x1, y1 = item["rect"]
    h = item["height"]
    m.box(x0, y0, x1, y1, 60, h)
    for wx in (x0 + 40, x1 - 60):                            # wheels
        for wy in (y0 + 40, y1 - 60):
            m.box(wx, wy, wx + 20, wy + 20, 0, 60)
    mx = (x0 + x1) / 2
    m.box(mx - 120, y1 - 40, mx - 100, y1 - 20, h, h + 120)  # telescopic handle
    m.box(mx + 100, y1 - 40, mx + 120, y1 - 20, h, h + 120)
    m.box(mx - 120, y1 - 40, mx + 120, y1 - 20, h + 120, h + 145)


def storage_boxes(r, b, m):
    """A row of boxes on each shelf except the top cap."""
    g, st = r["gap_to_wall"], r["shelf_thickness"]
    for unit in r["units"]:
        x0, y0, x1, y1 = unit["rect"]
        along_y = unit["open_side"] in ("east", "west")
        depth = (x1 - x0 if along_y else y1 - y0) - 2 * g - 60
        span0, span1 = (y0, y1) if along_y else (x0, x1)
        n = max(1, int((span1 - span0 - 60) // 420))
        w = (span1 - span0 - 60 - (n - 1) * 30) / n
        for z in r["shelves"][:-1]:
            for k in range(n):
                s = span0 + 30 + k * (w + 30)
                if along_y:
                    m.box(x0 + g + 30, s, x0 + g + 30 + depth, s + w, z, z + b["height"])
                else:
                    m.box(s, y1 - g - 30 - depth, s + w, y1 - g - 30, z, z + b["height"])


# ---------- collections ----------

def child_collection(parent_name, child_name):
    parent = bpy.data.collections.get(parent_name)
    if not parent:
        parent = bpy.data.collections.new(parent_name)
        bpy.context.scene.collection.children.link(parent)
    child = bpy.data.collections.get(child_name)
    if child:
        for obj in list(child.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        child = bpy.data.collections.new(child_name)
        parent.children.link(child)
    return child


def main():
    with open(DATA) as f:
        data = json.load(f)
    r = data["rack"]

    carp = child_collection("Carpentry", "Carpentry.HouseholdShelter")
    posts_m, shelves_m = Mesh(), Mesh()
    for unit in r["units"]:
        rack_unit(unit, r, posts_m, shelves_m)
    posts_m.finish("SH_Rack_Frame", carp, material("SH_RackFrame", (0.92, 0.92, 0.91), 0.4, 0.3))
    shelves_m.finish("SH_Rack_Shelves", carp, material("SH_RackShelf", (0.95, 0.95, 0.94), 0.45))
    whiteboard(data["whiteboard"], carp, material("SH_Whiteboard", (0.97, 0.97, 0.97), 0.08))

    acc = child_collection("Accessories", "Accessories.HouseholdShelter")
    for item in data["under_rack"]:
        m = Mesh()
        if item["kind"] == "bike":
            bike(item, m)
            mat = material("SH_Bike", (0.15, 0.55, 0.75), 0.4)
        else:
            luggage(item, m)
            mat = material(f"SH_{item['name']}", tuple(item["color"]), 0.35)
        m.finish(f"SH_{item['name']}", acc, mat)
    m = Mesh()
    storage_boxes(r, data["boxes"], m)
    m.finish("SH_StorageBoxes", acc, material("SH_Box", tuple(data["boxes"]["color"]), 0.6))
    print("[shelter] built rack, whiteboard and accessories")


main()
