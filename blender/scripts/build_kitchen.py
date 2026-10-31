"""Build the kitchen + dining renovation from blender/data/kitchen.json.

Creates these collections (rebuilt each run, nothing else touched):
  Carpentry.Kitchen   - straight base + top cabinet run, C1 coffee/wine cupboard,
                        full-height glass sliding partition
  Appliances.Kitchen  - fridge (French doors open on scene["door_fridge"], food inside), hob, hood,
                        sink, wine cellar, coffee machine
  (Carpentry.Kitchen also has the full-height appliance tower with pull-out trays for the
   countertop oven, air fryer and microwave: scene["door_kitchen_tray_<k>"])
  Furniture.Kitchen   - movable island
  Furniture.Dining    - 6-seater dining table + chairs
  Accessories.Kitchen - whisky bottles, wine glasses, tea + matcha set
It also registers the kitchen camera views in scene["room_cameras"] for render_views.py,
and makes the glass partition movable: scene["door_kitchen_partition"] (0 closed - 1 open).

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_kitchen.py
or send via the Blender MCP `execute_blender_code` tool.
"""
import importlib
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "kitchen.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "kitchen.json")
sys.path.insert(0, os.path.join(ROOT, "blender", "scripts"))
import door_motion  # noqa: E402
importlib.reload(door_motion)  # pick up edits when re-run inside a live Blender

SLOTS = ["carcass", "front", "counter", "wood", "frame", "glass", "glass_dark", "steel",
         "chrome", "appliance", "led", "bottle_wine", "bottle_whisky", "ceramic", "matcha", "black",
         "fridge_glass", "fridge_inner", "food_red", "food_orange", "food_green", "milk"]
S = {name: i for i, name in enumerate(SLOTS)}


def material(name, rgb, roughness=0.5, metallic=0.0, emission=0.0, alpha=1.0):
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
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("blend_method", "BLEND"), ("surface_render_method", "BLENDED")):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, val)
                except TypeError:
                    pass
    mat.diffuse_color = (*rgb, alpha)
    return mat


def materials(fin):
    glass = bpy.data.materials.get("Glass") or material("KT_Glass", (0.6, 0.8, 0.95), 0.05, alpha=0.25)
    return [
        material("KT_Carcass", tuple(fin["carcass"]), 0.6),
        material("KT_Front", tuple(fin["front"]), 0.45),
        material("KT_Counter", tuple(fin["counter"]), 0.25),
        material("KT_Wood", tuple(fin["wood"]), 0.55),
        material("KT_Frame", tuple(fin["frame"]), 0.4),
        glass,
        material("KT_GlassDark", (0.04, 0.045, 0.05), 0.05),
        material("KT_Steel", (0.70, 0.71, 0.72), 0.3, metallic=1.0),
        material("KT_Chrome", (0.80, 0.80, 0.82), 0.15, metallic=1.0),
        material("KT_Appliance", (0.86, 0.88, 0.87), 0.3),
        material("KT_LED", (1.0, 0.95, 0.85), 0.5, emission=3.0),
        material("KT_BottleWine", (0.08, 0.16, 0.08), 0.15),
        material("KT_BottleWhisky", (0.62, 0.33, 0.08), 0.15),
        material("KT_Ceramic", (0.93, 0.91, 0.86), 0.3),
        material("KT_Matcha", (0.40, 0.55, 0.25), 0.6),
        material("KT_Black", (0.05, 0.05, 0.05), 0.5),
        material("KT_FridgeGlass", (0.16, 0.14, 0.17), 0.06, metallic=0.35),   # Mirror Mauve Gray
        material("KT_FridgeInner", (0.94, 0.96, 0.99), 0.4),
        material("KT_FoodRed", (0.80, 0.15, 0.12), 0.4),
        material("KT_FoodOrange", (0.95, 0.55, 0.10), 0.4),
        material("KT_FoodGreen", (0.30, 0.60, 0.20), 0.5),
        material("KT_Milk", (0.97, 0.97, 0.95), 0.3),
    ]


class Mesh:
    """Builds geometry in plan millimetres (y down) into Blender metres (Y up)."""

    def __init__(self):
        self.bm = bmesh.new()

    def _v(self, x, y, z):
        return self.bm.verts.new((x / 1000, -y / 1000, z / 1000))

    def _faces(self, rings, slot):
        faces = [self.bm.faces.new(list(reversed(rings[0]))), self.bm.faces.new(rings[1])]
        n = len(rings[0])
        for k in range(n):
            j = (k + 1) % n
            faces.append(self.bm.faces.new((rings[0][k], rings[0][j], rings[1][j], rings[1][k])))
        for f in faces:
            f.material_index = slot

    def box(self, x0, y0, x1, y1, z0, z1, slot):
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        if x1 - x0 < 0.01 or y1 - y0 < 0.01 or z1 - z0 < 0.01:
            return
        quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        self._faces([[self._v(x, y, z0) for x, y in quad], [self._v(x, y, z1) for x, y in quad]], slot)

    def cyl_z(self, cx, cy, r, z0, z1, slot, n=24):
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x, y, z0) for x, y in ring], [self._v(x, y, z1) for x, y in ring]], slot)

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


class Frame:
    """Local frame for a unit whose front faces `front`: `a` runs along the front,
    `d` is the distance out from the front face (negative = into the carcass)."""

    def __init__(self, m, front, face):
        self.m, self.front, self.face = m, front, face

    def pt(self, a, d):
        if self.front == "north":
            return a, self.face - d
        if self.front == "south":
            return a, self.face + d
        if self.front == "east":
            return self.face + d, a
        return self.face - d, a  # west

    def box(self, a0, a1, d0, d1, z0, z1, slot):
        x0, y0 = self.pt(a0, d0)
        x1, y1 = self.pt(a1, d1)
        self.m.box(x0, y0, x1, y1, z0, z1, slot)

    def cyl(self, a, d, r, z0, z1, slot, n=24):
        x, y = self.pt(a, d)
        self.m.cyl_z(x, y, r, z0, z1, slot, n)


def unit_frame(m, rect, front):
    """Frame + (along range, back distance) for a plan rect whose front faces `front`."""
    x0, y0, x1, y1 = rect
    face = {"north": y0, "south": y1, "east": x1, "west": x0}[front]
    along = (x0, x1) if front in ("north", "south") else (y0, y1)
    depth = (y1 - y0) if front in ("north", "south") else (x1 - x0)
    return Frame(m, front, face), along, depth


def doors(f, a0, a1, z0, z1, n, slot=S["front"], gap=3, t=18, handle=None):
    """n equal fronts across a0-a1 (gap between), sitting on the front face."""
    w = (a1 - a0) / n
    for k in range(n):
        f.box(a0 + k * w + gap / 2, a0 + (k + 1) * w - gap / 2, 0, t, z0 + gap / 2, z1 - gap / 2, slot)
        if handle:
            # Slim black bar on the free edge (pairs open from the middle).
            hx = a0 + (k + 1) * w - 40 if k % 2 == 0 else a0 + k * w + 28
            f.box(hx, hx + 12, t, t + 15, handle[0], handle[1], S["black"])


def drawers(f, a0, a1, z0, z1, n, gap=3):
    h = (z1 - z0) / n
    for k in range(n):
        f.box(a0 + gap / 2, a1 - gap / 2, 0, 18, z0 + k * h + gap / 2, z0 + (k + 1) * h - gap / 2, S["front"])
        f.box((a0 + a1) / 2 - 80, (a0 + a1) / 2 + 80, 18, 30, z0 + (k + 1) * h - 45, z0 + (k + 1) * h - 33, S["black"])


# ---------- carpentry ----------

def base_run(run, bc, d, mk):
    m = mk()
    f, (a0, a1), depth = unit_frame(m, run["rect"], run["front"])
    top, wt, kick = bc["top"], bc["worktop"], bc["kick"]
    ct = top - wt
    f.box(a0, a1, -depth, -18, kick, ct, S["carcass"])             # carcass
    f.box(a0, a1, -depth, -70, 0, kick, S["carcass"])              # recessed kick
    # Worktop (with a cut-out for the sink basin on the south run).
    sink = d["sink"]["basin"] if run["front"] == "north" else None
    if sink:
        bx0, by0, bx1, by1 = sink
        y_front, y_back = run["rect"][1] - 20, run["rect"][3]
        for x_0, y_0, x_1, y_1 in ((a0, y_front, bx0, y_back), (bx1, y_front, a1, y_back),
                                   (bx0, y_front, bx1, by0), (bx0, by1, bx1, y_back)):
            m.box(x_0, y_0, x_1, y_1, ct, top, S["counter"])
    else:
        # An east-facing run stops at a north-facing run's worktop edge so a corner doesn't overlap.
        f.box(a0, a1 - (20 if run["front"] == "east" else 0), -depth, 20, ct, top, S["counter"])
    oven = d["oven"]["x"] if "oven" in d else None             # built-in oven is optional
    dish = d["dishwasher"]["x"]
    for k, fr in enumerate(run["fronts"]):
        s, e = fr
        if e - s < 100:
            f.box(s, e, 0, 18, kick, ct - 2, S["front"])          # filler
        elif run["front"] == "north" and [s, e] == oven:
            oz0, oz1 = d["oven"]["z"]
            f.box(s + 2, e - 2, 0, 18, kick + 2, oz0 - 2, S["front"])
            f.box(s + 30, e - 30, 0, 22, oz0, oz1, S["black"])  # oven
            f.box(s + 80, e - 80, 22, 24, oz0 + 60, oz1 - 140, S["glass_dark"])
            f.box(s + 80, e - 80, 22, 50, oz1 - 80, oz1 - 65, S["chrome"])
            f.box(s + 2, e - 2, 0, 18, oz1 + 2, ct - 2, S["front"])
        elif run["front"] == "north" and [s, e] == dish:
            f.box(s + 2, e - 2, 0, 18, kick + 2, ct - 2, S["front"])  # integrated dishwasher
            f.box(s + 60, e - 60, 18, 30, ct - 60, ct - 48, S["black"])
        elif run["front"] == "north" and s <= sink[0] and e >= sink[2]:
            doors(f, s, e, kick, ct, 2, handle=(ct - 200, ct - 40))
        else:
            drawers(f, s, e, kick, ct, 3)
    return m, f"{run['name']} base cabinets"


def top_run(run, tc, ceiling, mk):
    m = mk()
    f, (a0, a1), depth = unit_frame(m, run["rect"], run["front"])
    zb = tc["bottom"]
    f.box(a0, a1, -depth, -18, zb, ceiling, S["carcass"])
    n = max(1, round((a1 - a0) / tc["door_width"]))
    doors(f, a0, a1, zb, ceiling, n)
    f.box(a0 + 20, a1 - 20, -60, -40, zb - 4, zb, S["led"])      # under-cabinet LED strip
    return m, f"{run['name']} top cabinets (to ceiling)"


def partition(p, ceiling, mk):
    """Top-hung, full-height slim black-frame glass panels, one track each.

    stack "east": every panel slides east and parks in the slot between the fridge and C1.
    stack "both": bi-parting, half the panels park at each end (needs tracks >= panels / 2).

    Returns the ceiling track plus one (mesh, slide_mm) per panel. Panels are built CLOSED;
    `slide_mm` is how far the panel travels along plan x when fully open.
    """
    x0, x1 = p["x"]
    n, lap, fw = p["panels"], p["overlap"], p["frame"]
    w = ((x1 - x0) + (n - 1) * lap) / n
    east = p.get("stack", "east") == "east"
    gap, yc = p["track_gap"], p["y"]
    track_y = [yc + (t - (p["tracks"] - 1) / 2) * gap for t in range(p["tracks"])]
    if east:
        tracks = list(range(n))                # one track per panel: all stack in the slot
    else:
        # West half on tracks 0,1,2..; east half reversed, so neighbours never share a track.
        h = n // 2
        tracks = list(range(h)) + [(h - 1 - k) % p["tracks"] for k in range(n - h)]
    z0, z1 = 10, ceiling - 45
    panels = []
    for k in range(n):
        a = x0 + k * (w - lap)                                     # closed position
        parked = x1 - w if east or k >= n // 2 else x0             # fully open position
        y = track_y[tracks[k]]
        ya, yb = y - 14, y + 14
        m = mk()
        m.box(a, ya, a + fw, yb, z0, z1, 0)                        # stiles
        m.box(a + w - fw, ya, a + w, yb, z0, z1, 0)
        m.box(a, ya, a + w, yb, z0, z0 + fw + 20, 0)               # rails
        m.box(a, ya, a + w, yb, z1 - fw, z1, 0)
        m.box(a + fw, y - 4, a + w - fw, y + 4, z0 + fw + 20, z1 - fw, 1)  # glass
        panels.append((m, parked - a))
    track = mk()
    track.box(x0, track_y[0] - 25, x1, track_y[-1] + 25, ceiling - 45, ceiling, 0)
    return track, panels


def c1_columns(c, a0, a1):
    """Equal columns across C1 (about 500 mm each)."""
    n = max(2, round((a1 - a0) / c.get("column_width", 500)))
    w = (a1 - a0) / n
    return [(a0 + k * w, a0 + (k + 1) * w) for k in range(n)]


def c1_cupboard(c, mk):
    """Coffee / tea / matcha + wine station on the dining side of the glass (faces west)."""
    m = mk()
    f, (a0, a1), depth = unit_frame(m, c["rect"], c["front"])
    ct, top = c["counter_top"] - 30, c["counter_top"]
    f.box(a0, a1, -depth, -18, 0, ct, S["carcass"])
    f.box(a0, a1, -depth, 20, ct, top, S["counter"])
    dz0, dz1 = c["drawer"]
    drawers(f, a0, a1, dz0, dz1, 1)
    ws, we = c["wine_cellar"]                                      # cellar along-range
    for s, e in ((a0, ws), (we, a1)):                              # cabinet doors beside it
        if e - s > 100:
            doors(f, s, e, 0, dz0 - 10, max(1, round((e - s) / 450)), handle=(dz0 - 200, dz0 - 50))
    f.box(a0, a1, -depth, -depth + 10, top, c["upper_bottom"], S["wood"])  # wood splashback
    # Upper cabinet: columns x 3 rows, to the ceiling.
    ud = c["upper_depth"]
    ub, ut = c["upper_bottom"], c["upper_rows"][-1]["z"][1]
    off = -(depth - ud)                                            # upper front sits back
    g = Frame(m, f.front, f.face)
    g.pt = lambda a, d, _f=f: _f.pt(a, d + off)
    g.box(a0, a1, -ud, -18, ub, ub + 18, S["carcass"])
    g.box(a0, a1, -ud, -18, ut - 18, ut, S["carcass"])
    g.box(a0, a0 + 18, -ud, -18, ub, ut, S["carcass"])
    g.box(a1 - 18, a1, -ud, -18, ub, ut, S["carcass"])
    cols = c1_columns(c, a0, a1)
    for s, _ in cols[1:]:
        g.box(s - 9, s + 9, -ud, -18, ub, ut, S["carcass"])        # dividers
    g.box(a0, a1, -ud, -ud + 10, ub, ut, S["carcass"])            # back
    for row in c["upper_rows"]:
        z0, z1 = row["z"]
        g.box(a0 + 18, a1 - 18, -ud, -18, z0, z0 + 18, S["carcass"])  # shelf
        for s, e in cols:
            g.box(s + 30, e - 30, -ud + 20, -ud + 25, z1 - 25, z1 - 20, S["led"])
        for s, e in cols:
            if row["glass"]:
                g.box(s + 2, e - 2, 0, 18, z0 + 2, z0 + 22, S["frame"])
                g.box(s + 2, e - 2, 0, 18, z1 - 22, z1 - 2, S["frame"])
                g.box(s + 2, s + 22, 0, 18, z0 + 2, z1 - 2, S["frame"])
                g.box(e - 22, e - 2, 0, 18, z0 + 2, z1 - 2, S["frame"])
            else:
                g.box(s + 2, e - 2, 0, 18, z0 + 2, z1 - 2, S["front"])
        if not row["glass"]:
            for s, e in cols:                                      # handle at the bottom of each door
                g.box((s + e) / 2 - 80, (s + e) / 2 + 80, 18, 33, z0 + 30, z0 + 42, S["black"])
    g.box(a0 + 20, a1 - 20, -60, -40, ub - 4, ub, S["led"])
    return m, "C1 coffee + wine cupboard"


def c1_glass(c, mk):
    """Glass in C1's upper glass-door rows (separate object so it can be see-through)."""
    m = mk()
    f, (a0, a1), depth = unit_frame(m, c["rect"], c["front"])
    off = -(depth - c["upper_depth"])
    for row in c["upper_rows"]:
        if row["glass"]:
            z0, z1 = row["z"]
            for s, e in c1_columns(c, a0, a1):
                f.box(s + 22, e - 22, off + 7, off + 11, z0 + 22, z1 - 22, 0)
    return m


# ---------- appliances ----------

def fridge(fr, mats, coll):
    """French-door fridge (modelled on the Hitachi R-GWC670TS) facing north: glass body, wood strip,
    2 small + 2 large drawers, an open fresh-food cavity with glass shelves, a vacuum drawer and
    food, and two doors with door bins that swing open on scene["door_fridge"] (0 closed - 1 open)."""
    x0, y0, x1, y1 = fr["rect"]                    # y0 = front face of the closed doors
    H, split, strip, dt = fr["height"], fr["split"], fr["strip"], fr["door_thickness"]
    yb = y0 + dt                                   # front face of the body
    w = 45                                         # wall thickness of the cavity
    body = Mesh()
    g = S["fridge_glass"]
    # lower body + drawer fronts
    body.box(x0, yb, x1, y1, 20, split - strip, g)
    mid = (x0 + x1) / 2
    for k, (z0, z1) in enumerate(fr["drawers"]):
        if k == len(fr["drawers"]) - 1:            # two small drawers side by side
            body.box(x0 + 2, y0, mid - 2, yb, z0, z1, g)
            body.box(mid + 2, y0, x1 - 2, yb, z0, z1, g)
        else:
            body.box(x0 + 2, y0, x1 - 2, yb, z0, z1, g)
        body.box(x0 + 2, y0 - 1, x1 - 2, y0, z1 - 3, z1, S["black"])         # shadow gap
    body.box(x0, y0, x1, y1, split - strip, split, S["wood"])               # walnut strip
    body.box(x0, yb, x1, y1, 0, 20, S["black"])                              # plinth
    # fresh-food cavity: outer shell + white liner
    for bx in ((x0, yb, x0 + w, y1), (x1 - w, yb, x1, y1), (x0, y1 - w, x1, y1)):
        body.box(*bx, split, H, g)
    body.box(x0, yb, x1, y1, H - w, H, g)                                     # top
    body.box(x0 + w, yb, x1 - w, y1 - w, split, split + 35, S["fridge_inner"])  # floor
    for bx in ((x0 + w, yb, x0 + w + 4, y1 - w), (x1 - w - 4, yb, x1 - w, y1 - w),
               (x0 + w, y1 - w - 4, x1 - w, y1 - w)):
        body.box(*bx, split + 35, H - w, S["fridge_inner"])
    body.box(x0 + w, yb, x1 - w, y1 - w, H - w - 4, H - w, S["fridge_inner"])
    body.box(mid - 200, y1 - w - 300, mid + 200, y1 - w - 260, H - w - 12, H - w - 4, S["led"])
    sy0, sy1 = yb + 110, y1 - w - 5                # shelves clear the door bins
    shelves = [split + 210, split + 420, split + 630]
    for z in shelves:
        body.box(x0 + w + 4, sy0, x1 - w - 4, sy1, z - 6, z, S["glass"])
    # vacuum / chilled drawer on the floor
    body.box(x0 + w + 10, sy0, x1 - w - 10, sy1, split + 35, split + 45, S["glass"])
    body.box(x0 + w + 10, sy0 - 4, x1 - w - 10, sy0, split + 35, split + 170, S["glass_dark"])
    food = Mesh()
    food.box(x0 + 120, sy0 + 60, x0 + 330, sy0 + 260, split + 45, split + 95, S["food_red"])   # meat
    food.box(x0 + 380, sy0 + 60, x0 + 560, sy0 + 260, split + 45, split + 90, S["food_orange"])  # salmon
    # shelf 1: glass containers + eggs + greens
    z = shelves[0]
    for k in range(3):
        food.box(x0 + 80 + k * 230, sy0 + 80, x0 + 270 + k * 230, sy0 + 280, z, z + 90, S["glass"])
        food.box(x0 + 95 + k * 230, sy0 + 95, x0 + 255 + k * 230, sy0 + 265, z, z + 60,
                 (S["food_green"], S["food_red"], S["food_orange"])[k])
    # shelf 2: pot + cake tarts
    z = shelves[1]
    food.cyl_z(x0 + 560, sy0 + 230, 130, z, z + 140, S["ceramic"])
    for k in range(3):
        food.cyl_z(x0 + 140 + k * 110, sy0 + 120, 40, z, z + 50, S["food_red"], n=12)
    # shelf 3: jars + boxes
    z = shelves[2]
    for k in range(5):
        food.cyl_z(x0 + 120 + k * 140, sy0 + 150, 45, z, z + 120 + (k % 2) * 40,
                   (S["glass"], S["food_green"], S["ceramic"], S["food_orange"], S["glass"])[k], n=16)
    body.finish("KT_Fridge body (Hitachi R-GWC670TS)", coll, mats)
    food.finish("KT_Fridge food", coll, mats)

    door_motion.register_group("fridge", "Fridge French doors", fr.get("open", 0))
    T = math.radians(fr.get("max_angle", 100))
    for side, (a, b, hinge, sign) in {"left": (x0, mid - 2, x0, 1), "right": (mid + 2, x1, x1, -1)}.items():
        m = Mesh()
        m.box(a, y0, b, yb, split + 2, H, g)                                 # glass door
        m.box(a + 20, yb, b - 20, yb + 8, split + 30, H - 30, S["fridge_inner"])  # inner liner
        for k, zb in enumerate((split + 120, split + 370, split + 620)):     # door bins + bottles
            m.box(a + 40, yb + 8, b - 40, yb + 100, zb, zb + 10, S["glass"])
            m.box(a + 40, yb + 92, b - 40, yb + 100, zb, zb + 90, S["glass"])
            n = 4
            for j in range(n):
                cx = a + 80 + j * (b - a - 160) / (n - 1)
                h = 220 if k == 2 else 180 if k == 1 else 120
                slot = (S["milk"], S["bottle_whisky"], S["food_green"], S["bottle_wine"])[(j + k) % 4]
                m.cyl_z(cx, yb + 55, 32, zb + 10, zb + 10 + h, slot, n=12)
        obj = m.finish(f"KT_Fridge door {side}", coll, mats)
        px, py = hinge / 1000, -y0 / 1000
        obj.data.transform(Matrix.Translation((-px, -py, 0)))
        obj.location = (px, py, 0)
        door_motion.drive_rotation(obj, "fridge", sign * T)


def appliance_box(m, f, kind, a0, a1, front_d, depth, z0, h):
    """Countertop appliance standing on a tray; its front at `front_d` (frame distance), facing out."""
    back = front_d - depth
    if kind == "air_fryer":
        f.box(a0, a1, back, front_d, z0, z0 + h, S["black"])
        f.box(a0 + 20, a1 - 20, front_d, front_d + 25, z0 + 30, z0 + h * 0.6, S["black"])   # basket
        f.box((a0 + a1) / 2 - 50, (a0 + a1) / 2 + 50, front_d + 25, front_d + 45, z0 + h * 0.6 - 60,
              z0 + h * 0.6 - 30, S["chrome"])                                                 # handle
        f.box(a0 + 40, a1 - 40, front_d, front_d + 3, z0 + h * 0.7, z0 + h - 30, S["glass_dark"])
        return
    f.box(a0, a1, back, front_d, z0 + 10, z0 + h, S["steel"])
    for a in (a0 + 30, a1 - 50):
        f.box(a, a + 20, back + 30, front_d - 30, z0, z0 + 10, S["black"])                   # feet
    panel = 110 if kind == "oven" else 120
    f.box(a0 + 20, a1 - panel - 10, front_d, front_d + 6, z0 + 40, z0 + h - 30, S["glass_dark"])  # door
    f.box(a1 - panel, a1 - 15, front_d, front_d + 4, z0 + 40, z0 + h - 30, S["black"])           # controls
    if kind == "oven":
        f.box(a0 + 30, a1 - panel - 20, front_d + 6, front_d + 25, z0 + h - 60, z0 + h - 48, S["chrome"])
    else:
        f.box(a1 - panel - 30, a1 - panel - 18, front_d + 6, front_d + 25, z0 + 70, z0 + h - 70, S["chrome"])


def appliance_tower(t, mats, coll):
    """Full-height tall unit with open niches; each niche has a pull-out tray carrying removable
    countertop appliances (oven, air fryer, microwave). Trays slide out on scene["door_kitchen_tray_<k>"]."""
    m = Mesh()
    f, (a0, a1), depth = unit_frame(m, t["rect"], t["front"])
    H, kick, b = 2600, t["kick"], 18
    f.box(a0, a0 + b, -depth, 0, kick, H, S["carcass"])                    # side panels
    f.box(a1 - b, a1, -depth, 0, kick, H, S["carcass"])
    f.box(a0, a1, -depth, -depth + b, kick, H, S["carcass"])               # back
    f.box(a0, a1, -depth, -60, 0, kick, S["carcass"])                      # kick
    d0, d1 = t["drawers"]
    f.box(a0 + b, a1 - b, -depth + b, -18, kick, d1, S["carcass"])         # drawer box
    drawers(f, a0, a1, kick, d1, t["drawer_count"])
    z_top0, z_top1 = t["top_doors"]
    f.box(a0 + b, a1 - b, -depth + b, -18, z_top0, H, S["carcass"])        # upper cabinet
    doors(f, a0, a1, z_top0, H, 2, handle=(z_top0 + 40, z_top0 + 240))
    edges = [d1] + [z for n in t["niches"] for z in n["z"]] + [z_top0]
    for z in sorted(set(edges)):                                           # niche floors / ceilings
        f.box(a0 + b, a1 - b, -depth + b, 0, z - 18, z, S["carcass"])
        f.box(a0 + b, a1 - b, -2, 0, z - 18, z, S["wood"])                 # wood edge
    for zz0, zz1 in zip([n["z"][1] for n in t["niches"]], [n["z"][0] for n in t["niches"]][1:] + [z_top0]):
        if zz1 - zz0 > 20:                                                 # filler band between niches
            f.box(a0 + b, a1 - b, -18, 0, zz0, zz1 - 18, S["front"])
    for k, n in enumerate(t["niches"]):
        z0, z1 = n["z"]
        f.box(a0 + b + 20, a0 + b + 120, -depth + b, -depth + b + 2, z1 - 150, z1 - 80, S["black"])  # socket
        tray = Mesh()
        tf = Frame(tray, f.front, f.face)
        tf.box(a0 + b + 5, a1 - b - 5, -depth + b + 20, -10, z0, z0 + 18, S["wood"])     # pull-out tray
        tf.box(a0 + b + 5, a1 - b - 5, -12, -10 + 2, z0, z0 + 40, S["wood"])             # front lip
        for it in n["items"]:
            ia0, ia1 = it["a"]
            appliance_box(tray, tf, it["kind"], ia0, ia1, -40, it["depth"], z0 + 18, it["height"])
        obj = tray.finish(f"KT_Appliance tray {k + 1} ({n['label']})", coll, mats)
        gid = f"kitchen_tray_{k + 1}"
        door_motion.register_group(gid, f"Kitchen {n['label']} (pull out)", n.get("open", 0))
        sx = {"west": -1, "east": 1}.get(f.front, 0) * n["pull"] / 1000
        sy = {"north": 1, "south": -1}.get(f.front, 0) * n["pull"] / 1000
        door_motion.drive(obj, gid, (sx, sy, 0))
    m.finish("KT_Appliance tower (full height)", coll, mats)


def hob_hood_sink(d, mk):
    m = mk()
    x0, y0, x1, y1 = d["hob"]["rect"]
    top = d["base_cabinets"]["top"]
    m.box(x0, y0, x1, y1, top, top + 6, S["glass_dark"])
    for cx, cy, r in ((x0 + 200, y0 + 150, 110), (x1 - 200, y0 + 150, 90),
                      (x0 + 200, y1 - 150, 90), (x1 - 200, y1 - 150, 110)):
        m.cyl_z(cx, cy, r, top + 6, top + 7, S["steel"], n=32)
    hx0, hy0, hx1, hy1 = d["hood"]["rect"]
    zb = d["top_cabinets"]["bottom"]
    m.box(hx0 + 5, hy0 - 40, hx1 - 5, hy1, zb - d["hood"]["height"], zb, S["steel"])
    bx0, by0, bx1, by1 = d["sink"]["basin"]
    bottom = top - d["sink"]["depth"]
    w = 3
    m.box(bx0, by0, bx1, by1, bottom, bottom + w, S["steel"])
    m.box(bx0, by0, bx0 + w, by1, bottom, top - 1, S["steel"])
    m.box(bx1 - w, by0, bx1, by1, bottom, top - 1, S["steel"])
    m.box(bx0, by0, bx1, by0 + w, bottom, top - 1, S["steel"])
    m.box(bx0, by1 - w, bx1, by1, bottom, top - 1, S["steel"])
    cx = (bx0 + bx1) / 2
    m.cyl_z(cx, by1 + 45, 16, top, top + 320, S["chrome"])        # gooseneck tap
    m.box(cx - 13, by0 + 150, cx + 13, by1 + 45, top + 295, top + 320, S["chrome"])
    return m, "Hob + hood + sink (suggested positions)"


def wine_cellar(c, mk):
    m = mk()
    f, _, depth = unit_frame(m, c["rect"], c["front"])
    a0, a1 = c["wine_cellar"]
    zt = c["wine_cellar_top"]
    f.box(a0 + 3, a1 - 3, -depth + 20, -18, 20, zt, S["black"])   # cabinet body
    f.box(a0 + 3, a1 - 3, -18, 0, 20, 50, S["black"])             # door frame
    f.box(a0 + 3, a1 - 3, -18, 0, zt - 30, zt, S["black"])
    f.box(a0 + 3, a0 + 33, -18, 0, 20, zt, S["black"])
    f.box(a1 - 33, a1 - 3, -18, 0, 20, zt, S["black"])
    f.box(a0 + 33, a1 - 33, -10, -6, 50, zt - 30, S["glass_dark"])
    f.box(a0 + 40, a1 - 40, -20, -17, zt - 50, zt - 45, S["led"])
    # Bottle bottoms seen through the glass, 4 racks.
    for r in range(4):
        z = 110 + r * 150
        k = 0
        while a0 + 75 + k * 85 < a1 - 60:
            f.box(a0 + 45 + k * 85, a0 + 105 + k * 85, -60, -30, z - 30, z + 30, S["bottle_wine"])
            k += 1
    return m, "Wine cellar (under-counter)"


def coffee_machine(at, mk, top):
    x0, y0, x1, y1 = at
    m = mk()
    m.box(x0, y0, x1, y1, top, top + 30, S["black"])              # base / drip tray
    m.box(x0 + 120, y0, x1, y1, top + 30, top + 400, S["steel"])  # body (back part)
    m.box(x0, y0, x0 + 120, y1, top + 300, top + 400, S["steel"])  # head
    m.cyl_z(x0 + 60, (y0 + y1) / 2, 30, top + 250, top + 300, S["black"])  # group head
    m.cyl_z(x0 + 60, (y0 + y1) / 2, 32, top + 30, top + 110, S["ceramic"])  # cup
    m.cyl_z(x1 - 70, (y0 + y1) / 2, 55, top + 400, top + 560, S["glass_dark"])  # bean hopper
    return m, "Coffee machine"


# ---------- furniture ----------

def island(d, mk):
    x0, y0, x1, y1 = d["rect"]
    top, c = d["top"], d["castor"]
    m = mk()
    m.box(x0 + 20, y0 + 20, x1 - 20, y1 - 20, c, top - 30, S["carcass"])
    m.box(x0, y0, x1, y1, top - 30, top, S["wood"])
    f = Frame(m, "south", y1 - 20)
    n = 3
    w = (x1 - x0 - 40) / n
    for k in range(n):
        drawers(f, x0 + 20 + k * w, x0 + 20 + (k + 1) * w, c + 10, top - 30, 2)
    for cx, cy in ((x0 + 70, y0 + 70), (x1 - 70, y0 + 70), (x0 + 70, y1 - 70), (x1 - 70, y1 - 70)):
        m.cyl_z(cx, cy, 30, 10, c, S["black"])                     # lockable castors
        m.box(cx - 25, cy - 25, cx + 25, cy + 25, c - 10, c, S["chrome"])
    return m, "Island (movable, on castors)"


def table(d, mk):
    x0, y0, x1, y1 = d["rect"]
    h = d["height"]
    m = mk()
    m.box(x0, y0, x1, y1, h - 30, h, S["wood"])
    for lx, ly in ((x0 + 60, y0 + 60), (x1 - 120, y0 + 60), (x0 + 60, y1 - 120), (x1 - 120, y1 - 120)):
        m.box(lx, ly, lx + 60, ly + 60, 0, h - 30, S["wood"])
    m.box(x0 + 90, y0 + 70, x1 - 90, y0 + 90, h - 110, h - 30, S["wood"])   # aprons
    m.box(x0 + 90, y1 - 90, x1 - 90, y1 - 70, h - 110, h - 30, S["wood"])
    return m, f"Dining table {x1 - x0:.0f} x {y1 - y0:.0f} (6-seater)"


def chair(cx, y, faces, s, mk):
    m = mk()
    x0, x1 = cx - s / 2, cx + s / 2
    y0, y1 = y, y + s
    m.box(x0, y0, x1, y1, 430, 460, S["wood"])
    for lx, ly in ((x0 + 15, y0 + 15), (x1 - 45, y0 + 15), (x0 + 15, y1 - 45), (x1 - 45, y1 - 45)):
        m.box(lx, ly, lx + 30, ly + 30, 0, 430, S["black"])
    by = y0 if faces == "south" else y1 - 25                       # backrest away from the table
    m.box(x0 + 15, by, x0 + 40, by + 25, 460, 850, S["black"])
    m.box(x1 - 40, by, x1 - 15, by + 25, 460, 850, S["black"])
    m.box(x0 + 15, by, x1 - 15, by + 25, 700, 850, S["wood"])
    return m


# ---------- accessories ----------

def c1_contents(c, mk, mats, coll):
    f_m = mk()
    f, (a0, a1), depth = unit_frame(f_m, c["rect"], c["front"])
    off = -(depth - c["upper_depth"])
    rows = {r["name"]: r for r in c["upper_rows"]}
    # Whisky: 3 bottles per column on the lowest shelf.
    z = rows["Whisky"]["z"][0] + 18
    cols = c1_columns(c, a0, a1)
    for s, e in cols:
        for k in range(3):
            a = s + 80 + k * (e - s - 160) / 2
            f.cyl(a, off - 170, 38, z, z + 220, S["bottle_whisky"])
            f.cyl(a, off - 170, 14, z + 220, z + 290, S["black"])
    f_m.finish("KT_Whisky bottles", coll, mats)
    # Wine glasses: 2 rows x 4 per column, stem + bowl, in glass material.
    g = mk()
    gf = Frame(g, f.front, f.face)
    z = rows["Wine glasses"]["z"][0] + 18
    for s, e in cols:
        for k in range(4):
            for dd in (off - 90, off - 240):
                a = s + 60 + k * (e - s - 120) / 3
                gf.cyl(a, dd, 35, z, z + 5, 0, n=16)
                gf.cyl(a, dd, 4, z + 5, z + 110, 0, n=8)
                gf.cyl(a, dd, 40, z + 110, z + 220, 0, n=16)
    g.finish("KT_Wine glasses", coll, [mats[S["ceramic"]]])
    # Tea set + matcha set on the counter, beside the coffee machine.
    t = mk()
    tf = Frame(t, f.front, f.face)
    top = c["counter_top"]
    tf.box(a1 - 380, a1 - 40, -420, -120, top, top + 15, S["wood"])        # tray
    tf.cyl(a1 - 300, -270, 70, top + 15, top + 140, S["ceramic"])           # teapot
    tf.cyl(a1 - 200, -200, 32, top + 15, top + 75, S["ceramic"])            # cups
    tf.cyl(a1 - 120, -200, 32, top + 15, top + 75, S["ceramic"])
    tf.cyl(a1 - 160, -340, 60, top + 15, top + 85, S["matcha"])             # matcha bowl
    tf.cyl(a1 - 80, -340, 22, top + 15, top + 110, S["wood"])               # chasen (whisk)
    t.finish("KT_Tea + matcha set", coll, mats)


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
    with open(DATA) as fh:
        d = json.load(fh)
    mats = materials(d["finishes"])
    ceiling = d["ceiling"]
    carp = child_collection("Carpentry", "Carpentry.Kitchen")
    appl = child_collection("Appliances", "Appliances.Kitchen")
    furn_k = child_collection("Furniture", "Furniture.Kitchen")
    furn_d = child_collection("Furniture", "Furniture.Dining")
    acc = child_collection("Accessories", "Accessories.Kitchen")

    jobs = [(carp, base_run(r, d["base_cabinets"], d, Mesh)) for r in d["base_cabinets"]["runs"]]
    jobs += [(carp, top_run(r, d["top_cabinets"], ceiling, Mesh)) for r in d["top_cabinets"]["runs"]]
    jobs += [
        (carp, c1_cupboard(d["c1"], Mesh)),
        (appl, hob_hood_sink(d, Mesh)),
        (appl, wine_cellar(d["c1"], Mesh)),
        (furn_k, island(d["island"], Mesh)),
        (furn_d, table(d["dining"]["table"], Mesh)),
    ]
    c = d["c1"]
    cm0, cm1 = c["coffee_machine"]                                 # along-range (plan y)
    jobs.append((appl, coffee_machine([c["rect"][0] + 40, cm0, c["rect"][2] - 20, cm1], Mesh, c["counter_top"])))
    for coll, (mesh, name) in jobs:
        mesh.finish(f"KT_{name}", coll, mats)
        print(f"  built {name}")

    door_motion.forget_groups("fridge")
    fridge(d["fridge"], mats, appl)
    door_motion.forget_groups("kitchen_tray_")
    if "appliance_tower" in d:
        appliance_tower(d["appliance_tower"], mats, carp)
    c1_glass(c, Mesh).finish("KT_C1 glass doors", carp, [mats[S["glass"]]])
    track, panels = partition(d["partition"], ceiling, Mesh)
    track.finish("KT_Glass partition track", carp, [mats[S["frame"]]])
    door_motion.register_group("kitchen_partition", "Kitchen glass partition", d["partition"]["open"])
    for k, (mesh, slide) in enumerate(panels):
        obj = mesh.finish(f"KT_Glass panel {k + 1}", carp, [mats[S["frame"]], mats[S["glass"]]])
        door_motion.drive(obj, "kitchen_partition", (slide / 1000, 0, 0))

    dn = d["dining"]
    for row in dn["chair_rows"]:
        for x in dn["chair_x"]:
            chair(x, row["y"], row["faces"], dn["chair_seat"], Mesh).finish(f"KT_Dining chair {row['faces']} {x}", furn_d, mats)
    c1_contents(c, Mesh, mats, acc)

    scene = bpy.context.scene
    cams = {k: v for k, v in json.loads(scene.get("room_cameras", "{}")).items() if not k.startswith("kit_")}
    cams.update(d.get("cameras", {}))
    scene["room_cameras"] = json.dumps(cams)
    print(f"Kitchen: {len(carp.objects)} carpentry, {len(appl.objects)} appliance, "
          f"{len(furn_k.objects) + len(furn_d.objects)} furniture, {len(acc.objects)} accessory objects")


main()
