"""Build the service yard renovation from blender/data/service_yard.json.

Creates three collections (rebuilt each run, nothing else touched):
  Carpentry.ServiceYard   - laundry counter, tall cabinet, sink unit
  Appliances.ServiceYard  - washer, dryer, robot vacuum + dock, stick vacuum, ceiling rack
  Accessories.ServiceYard - cabinet contents: hangers, baskets, bottles, bins

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_service_yard.py
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
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "service_yard.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "service_yard.json")

# Material slots shared by every object built here.
SLOTS = ["carcass", "front", "counter", "appliance", "glass_dark", "chrome",
         "steel", "robot", "dyson", "rack", "led", "pipe", "panel"]
S = {name: i for i, name in enumerate(SLOTS)}


def material(name, rgb, roughness=0.5, metallic=0.0, emission=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = (*rgb, 1.0)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = (*rgb, 1.0)
    return mat


def materials(fin):
    return [
        material("SY_Carcass", tuple(fin["carcass"]), 0.6),
        material("SY_Front", tuple(fin["front"]), 0.5),
        material("SY_Counter", tuple(fin["counter"]), 0.25),
        material("SY_Appliance", (0.93, 0.93, 0.92), 0.3),
        material("SY_GlassDark", (0.05, 0.06, 0.07), 0.05),
        material("SY_Chrome", (0.80, 0.80, 0.82), 0.15, metallic=1.0),
        material("SY_Steel", (0.70, 0.71, 0.72), 0.3, metallic=1.0),
        material("SY_Robot", (0.95, 0.95, 0.95), 0.35),
        material("SY_Dyson", (0.45, 0.40, 0.55), 0.35),
        material("SY_Rack", (0.88, 0.88, 0.88), 0.4),
        material("SY_LED", (1.0, 0.97, 0.90), 0.5, emission=2.0),
        material("SY_Pipe", (0.75, 0.80, 0.85), 0.4),
        material("SY_Panel", (0.75, 0.76, 0.77), 0.35),
    ]


class Mesh:
    """Builds geometry in plan millimetres (y down) into Blender metres (Y up)."""

    def __init__(self):
        self.bm = bmesh.new()

    def _v(self, x, y, z):
        return self.bm.verts.new((x / 1000, -y / 1000, z / 1000))

    def _faces(self, rings, slot, caps=True):
        faces = []
        if caps:
            faces.append(self.bm.faces.new(list(reversed(rings[0]))))
            faces.append(self.bm.faces.new(rings[1]))
        n = len(rings[0])
        for k in range(n):
            j = (k + 1) % n
            faces.append(self.bm.faces.new((rings[0][k], rings[0][j], rings[1][j], rings[1][k])))
        for f in faces:
            f.material_index = slot

    def box(self, x0, y0, x1, y1, z0, z1, slot):
        if x1 <= x0 or y1 <= y0 or z1 <= z0:
            return
        quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        self._faces([[self._v(x, y, z0) for x, y in quad], [self._v(x, y, z1) for x, y in quad]], slot)

    def cyl_z(self, cx, cy, r, z0, z1, slot, n=32):
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x, y, z0) for x, y in ring], [self._v(x, y, z1) for x, y in ring]], slot)

    def cyl_y(self, cx, cz, r, y0, y1, slot, n=32):
        """Cylinder whose axis runs along plan y (e.g. a door on a south-facing front)."""
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x, y0, z) for x, z in ring], [self._v(x, y1, z) for x, z in ring]], slot)

    def cyl_x(self, cy, cz, r, x0, x1, slot, n=16):
        """Cylinder whose axis runs along plan x (e.g. a hanging rail)."""
        ring = [(cy + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x0, y, z) for y, z in ring], [self._v(x1, y, z) for y, z in ring]], slot)

    def bar_yz(self, x, p0, p1, w, slot, thick=8):
        """Thin bar in the y-z plane from p0 to p1 (any angle), `thick` wide along x."""
        (y0, z0), (y1, z1) = p0, p1
        L = math.hypot(y1 - y0, z1 - z0)
        ny, nz = -(z1 - z0) / L * w / 2, (y1 - y0) / L * w / 2
        quad = [(y0 + ny, z0 + nz), (y1 + ny, z1 + nz), (y1 - ny, z1 - nz), (y0 - ny, z0 - nz)]
        self._faces([[self._v(x - thick / 2, y, z) for y, z in quad],
                     [self._v(x + thick / 2, y, z) for y, z in quad]], slot)

    def finish(self, name, coll, mats):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in mats:
            me.materials.append(m)
        obj = bpy.data.objects.new(name, me)
        coll.objects.link(obj)
        return obj


# ---------- carpentry ----------

def laundry_counter(d, mk):
    x0, y0, x1, y1 = d["rect"]
    m = mk()
    m.box(x0, y0, x1, y1, d["top"] - d["thickness"], d["top"], S["counter"])
    return m, "Laundry counter (folding top)"


def tall_cabinet(d, mk):
    """Layout follows the owner's sketch (see service_yard.json note)."""
    x0, y0, x1, y1 = d["rect"]  # front = y0 (north)
    H, t = d["height"], d["board"]
    yb = y0 + t  # carcass starts behind the doors
    m = mk()
    m.box(x0, yb, x0 + t, y1, 0, H, S["carcass"])           # west side
    m.box(x1 - t, yb, x1, y1, 0, H, S["carcass"])           # east side
    m.box(x0, yb, x1, y1, H - t, H, S["carcass"])           # top
    m.box(x0 + t, yb, x1 - t, y1, d["top_shelf"], d["top_shelf"] + t, S["carcass"])  # overstock shelf
    da0, da1 = d["dyson_column"]
    rb0, rb1 = d["robot_column"]
    m.box(da1, yb, rb0, y1, 0, d["divider_top"], S["carcass"])  # divider

    # Dyson column: base, then shelf on top for the laundry-pods basket.
    m.box(da0, yb, da1, y1, 0, t, S["carcass"])
    for z in d["dyson_column_shelves"]:
        m.box(da0, yb, da1, y1, z, z + t, S["carcass"])

    # Robot column: open bay at floor, shelves above for laundry items.
    bay = d["robot_bay_height"]
    m.box(rb0, yb, rb1, y1, bay, bay + t, S["carcass"])
    for z in d["robot_column_shelves"]:
        m.box(rb0, yb, rb1, y1, z, z + t, S["carcass"])

    # Full-width hanger rod (hangers only), mid-depth.
    rz, ry = d["hanger_rod_height"], (yb + y1) / 2
    m.cyl_x(ry, rz, 12, x0 + t, x1 - t, S["chrome"])
    for xx in (x0 + t, x1 - t - 25):
        m.box(xx, ry - 30, xx + 25, ry + 30, rz - 30, rz + 30, S["chrome"])

    if d.get("show_doors", True):
        m.box(x0 + 2, y0, da1 + 7, yb, t + 2, H - 2, S["front"])
        m.box(rb0 - 7, y0, x1 - 2, yb, bay + 2, H - 2, S["front"])
        m.box(da1 - 25, y0 - 20, da1 - 13, y0, 1000, 1200, S["chrome"])
        m.box(rb0 + 10, y0 - 20, rb0 + 22, y0, 1000, 1200, S["chrome"])
    return m, "Tall cabinet (robot bay + Dyson niche + storage)"


def ipad_platform(d, mk):
    """Raised ledge / shelf on the folding counter (solid, or open underneath)."""
    x0, y0, x1, y1 = d["rect"]
    top = d["top"]
    base = 920  # sits on the folding counter
    m = mk()
    if d.get("solid"):
        m.box(x0, y0, x1, y1, base, top, S["front"])
        m.box(x0, y1 - 12, x1, y1, top, top + 15, S["front"])  # front lip so the iPad can't slide
        return m, "iPad platform"
    t = d["board"]
    m.box(x0, y0, x1, y1, top - t, top, S["front"])            # shelf / plank
    if d.get("floating"):
        return m, "iPad platform"                              # concealed wall brackets
    m.box(x0, y0, x0 + 18, y1, base, top - t, S["front"])      # side supports
    m.box(x1 - 18, y0, x1, y1, base, top - t, S["front"])
    m.box(x0, y1 - 12, x1, y1, top, top + 15, S["front"])      # front lip so the iPad can't slide
    return m, "iPad platform"


def utility_sink(d, mk):
    x0, y0, x1, y1 = d["rect"]  # front = y0 (north)
    top = d["top"]
    bx0, by0, bx1, by1 = d["basin"]
    bottom = top - d["basin_depth"]
    t = 18
    m = mk()
    m.box(x0, y0 + 75, x1, y1, 0, 100, S["carcass"])                    # recessed kick
    m.box(x0, y0 + t, x1, y1, 100, bottom - 10, S["carcass"])           # body below basin
    for a in ((x0, y0 + t, bx0, y1), (bx1, y0 + t, x1, y1),             # body around basin
              (bx0, y0 + t, bx1, by0), (bx0, by1, bx1, y1)):
        m.box(*a, bottom - 10, top - 30, S["carcass"])
    m.box(x0 + 2, y0, x1 - 2, y0 + t, 102, top - 32, S["front"])        # door
    m.box(x1 - 50, y0 - 20, x1 - 38, y0, top - 260, top - 60, S["chrome"])  # handle
    for a in ((x0, y0, bx0, y1), (bx1, y0, x1, y1), (bx0, y0, bx1, by0), (bx0, by1, bx1, y1)):
        m.box(*a, top - 30, top, S["counter"])                          # counter with cut-out
    w = 3                                                               # basin walls
    m.box(bx0, by0, bx1, by1, bottom, bottom + w, S["steel"])
    m.box(bx0, by0, bx0 + w, by1, bottom, top - 1, S["steel"])
    m.box(bx1 - w, by0, bx1, by1, bottom, top - 1, S["steel"])
    m.box(bx0, by0, bx1, by0 + w, bottom, top - 1, S["steel"])
    m.box(bx0, by1 - w, bx1, by1, bottom, top - 1, S["steel"])
    m.cyl_z((bx0 + bx1) / 2, (by0 + by1) / 2, 25, bottom + w, bottom + w + 2, S["chrome"])  # waste
    cx = (bx0 + bx1) / 2                                                # gooseneck tap
    m.cyl_z(cx, y1 - 45, 16, top, top + 300, S["chrome"])
    m.box(cx - 13, (by0 + by1) / 2 + 40, cx + 13, y1 - 45, top + 275, top + 300, S["chrome"])
    return m, "Utility sink (hand-wash laundry)"


# ---------- appliances ----------

def front_loader(d, mk):
    x0, y0, x1, y1 = d["rect"]  # front = y1 (south)
    h = d["height"]
    cx = (x0 + x1) / 2
    m = mk()
    m.box(x0, y0, x1, y1, 0, h, S["appliance"])
    m.box(x0 + 10, y1, x1 - 10, y1 + 4, h - 110, h - 10, S["panel"])     # control panel
    m.box(cx - 60, y1 + 4, cx + 60, y1 + 6, h - 75, h - 45, S["glass_dark"])  # display
    m.cyl_y(x0 + 110, h - 60, 28, y1 + 4, y1 + 26, S["chrome"])         # dial
    m.box(x0 + 20, y1, x0 + 180, y1 + 3, h - 100, h - 85, S["glass_dark"])  # drawer line
    m.cyl_y(cx, 420, 235, y1, y1 + 30, S["panel"])                      # door ring
    m.cyl_y(cx, 420, 175, y1 + 30, y1 + 36, S["glass_dark"])            # door glass
    m.box(cx + 175, y1 + 30, cx + 205, y1 + 40, 380, 460, S["chrome"])  # door handle
    return m, d["name"]


def robot_vacuum(d, mk):
    x0, y0, x1, y1 = d["dock_rect"]  # dock faces north (y0)
    h = d["dock_height"]
    rx, ry = d["robot_center"]
    r = d["robot_diameter"] / 2
    m = mk()
    m.box(x0, y0, x1, y1, 0, h, S["robot"])                             # dock body
    m.box(x0 + 30, y0 - 3, x1 - 30, y0, h - 160, h - 40, S["glass_dark"])  # dock lid / window
    m.box(x0, ry - r + 10, x1, y0, 0, 12, S["panel"])                   # ramp / wash tray
    m.cyl_z(rx, ry, r, 15, 110, S["robot"])                             # robot
    m.cyl_z(rx, ry - r * 0.35, 42, 110, 132, S["glass_dark"])           # lidar turret
    # Water hookup kit: inlet valve on the wall + drain to a floor trap.
    m.cyl_z(x1 - 40, y1 - 15, 10, 0, 320, S["pipe"])
    m.box(x1 - 60, y1 - 30, x1 - 20, y1 - 2, 300, 340, S["chrome"])
    m.cyl_z(x0 + 50, y1 - 30, 50, 0, 4, S["steel"])
    return m, "Robot vacuum + plumbed dock"


def stick_vacuum(d, mk):
    x, y = d["at"]
    m = mk()
    m.box(x - 120, y - 80, x + 120, y + 120, 18, 30, S["panel"])        # floor dock
    m.box(x - 120, y - 160, x + 120, y - 40, 30, 95, S["dyson"])        # cleaner head
    m.box(x - 22, y - 10, x + 22, y + 34, 95, 1000, S["chrome"])        # wand
    m.cyl_z(x, y + 40, 65, 1000, 1220, S["dyson"])                      # bin + motor
    m.box(x - 15, y + 100, x + 15, y + 150, 1080, 1260, S["dyson"])     # handle
    return m, "Stick vacuum (Dyson)"


def ceiling_rack(d, mk, ceiling):
    x0, y0, x1, y1 = d["body_rect"]
    zb = ceiling - d["body_height"]
    m = mk()
    m.box(x0, y0, x1, y1, zb, ceiling, S["rack"])                       # body
    m.box(x0 + 25, y0 + 60, x1 - 25, y1 - 60, zb - 4, zb, S["led"])     # LED / heater panel
    py0, py1 = d["poles_y"]
    pz1 = zb - 15
    for px in d["poles_x"]:
        m.box(px - 12, py0, px + 12, py1, pz1 - 25, pz1, S["chrome"])    # drying poles
    for yy in (y0 + 20, y1 - 40):
        m.box(d["poles_x"][0] - 12, yy, d["poles_x"][1] + 12, yy + 20, pz1 - 25, zb, S["rack"])
    return m, f"Ceiling laundry rack ({d.get('name', 'rack')})"


# ---------- accessories (contents of the cabinets) ----------

def hangers(d, rod_z, ry, mk):
    m = mk()
    x0, x1 = d["x"]
    n = d["count"]
    for i in range(n):
        x = x0 + i * (x1 - x0) / max(1, n - 1)
        top, shoulder, bottom = rod_z + 10, rod_z - 60, rod_z - 230
        m.bar_yz(x, (ry, top), (ry, shoulder), 8, 0)
        m.bar_yz(x, (ry, shoulder), (ry - 200, bottom), 10, 0)
        m.bar_yz(x, (ry, shoulder), (ry + 200, bottom), 10, 0)
        m.bar_yz(x, (ry - 200, bottom), (ry + 200, bottom), 8, 0)
    return m


def basket(d, mk):
    x0, y0, x1, y1 = d["rect"]
    z0, z1, w = d["z"], d["z"] + d["height"], 8
    m = mk()
    m.box(x0, y0, x1, y1, z0, z0 + w, 0)
    m.box(x0, y0, x0 + w, y1, z0, z1, 0)
    m.box(x1 - w, y0, x1, y1, z0, z1, 0)
    m.box(x0, y0, x1, y0 + w, z0, z1, 0)
    m.box(x0, y1 - w, x1, y1, z0, z1, 0)
    return m


def bottle(d, mk):
    x0, y0, x1, y1 = d["rect"]
    z0, h = d["z"], d["height"]
    m = mk()
    m.box(x0, y0, x1, y1, z0, z0 + h * 0.85, 0)
    m.cyl_z((x0 + x1) / 2, (y0 + y1) / 2, 28, z0 + h * 0.85, z0 + h, 0)
    return m


def tablet(d, mk):
    x0, x1 = d["x"]
    m = mk()
    m.bar_yz((x0 + x1) / 2, tuple(d["base"]), tuple(d["lean_to"]), 8, 0, thick=x1 - x0)
    return m


def cactus(d, mk):
    x, y = d["at"]
    z = d["z"]
    m = mk()
    m.cyl_z(x, y, 34, z, z + 65, 1)                 # pot
    m.cyl_z(x, y, 20, z + 65, z + 165, 0)           # body
    m.cyl_z(x - 26, y, 9, z + 105, z + 140, 0)      # arm
    return m


def build_accessories(d, coll):
    cab = d["tall_cabinet"]
    ry = (cab["rect"][1] + cab["board"] + cab["rect"][3]) / 2
    for item in d.get("accessories", []):
        if item["type"] == "hangers":
            m, mat = hangers(item, cab["hanger_rod_height"], ry, Mesh), material("SY_Acc_Hanger", (0.95, 0.95, 0.95), 0.4)
        else:
            m = {"bottle": bottle, "tablet": tablet, "cactus": cactus}.get(item["type"], basket)(item, Mesh)
            mat = material(f"SY_Acc_{item['name']}", tuple(item["color"]), 0.6)
        if item["type"] == "cactus":
            mats_ = [mat, material("SY_Acc_Terracotta", (0.70, 0.38, 0.24), 0.8)]
            m.finish(f"SY_{item['name']}", coll, mats_)
            continue
        tag = " (suggested)" if item.get("suggested") else ""
        m.finish(f"SY_{item['name']}{tag}", coll, [mat])


# ---------- collections ----------

def child_collection(parent_name, child_name):
    parent = bpy.data.collections.get(parent_name)
    if not parent:
        parent = bpy.data.collections.new(parent_name)
        bpy.context.scene.collection.children.link(parent)
    child = bpy.data.collections.get(child_name)
    if child:
        for obj in list(child.all_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        child = bpy.data.collections.new(child_name)
        parent.children.link(child)
    return child


def main():
    with open(DATA) as f:
        d = json.load(f)
    mats = materials(d["finishes"])
    carp = child_collection("Carpentry", "Carpentry.ServiceYard")
    appl = child_collection("Appliances", "Appliances.ServiceYard")
    ceiling = d["interior"]["ceiling"]

    jobs = [
        (carp, laundry_counter(d["laundry_counter"], Mesh)),
        (carp, tall_cabinet(d["tall_cabinet"], Mesh)),
        (carp, utility_sink(d["utility_sink"], Mesh)),
        (carp, ipad_platform(d["ipad_platform"], Mesh)),
        (appl, robot_vacuum(d["robot_vacuum"], Mesh)),
        (appl, stick_vacuum(d["stick_vacuum"], Mesh)),
        (appl, ceiling_rack(d["ceiling_rack"], Mesh, ceiling)),
    ]
    jobs += [(appl, front_loader(fl, Mesh)) for fl in d["front_loaders"]]
    for coll, (mesh, name) in jobs:
        mesh.finish(f"SY_{name}", coll, mats)
        print(f"  built {name}")
    acc = child_collection("Accessories", "Accessories.ServiceYard")
    build_accessories(d, acc)
    print(f"  built {len(acc.objects)} accessories")
    print(f"Service yard: {len(carp.objects)} carpentry, {len(appl.objects)} appliance objects")


main()
