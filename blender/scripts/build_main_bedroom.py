"""Build the main bedroom renovation from blender/data/main_bedroom_design<N>.json.

There are alternative layouts; pick one with env MB_DESIGN (default 2):
  1 - bed along the window (headboard east), long table, L-wardrobe in the SE corner, TV on the west wall
  2 - west wall: vanity | pole hanging system (with wire baskets) behind bi-fold doors | cupboard 2;
      lobby mirror; bed headboard on the window wall, TV feature wall + L-shaped study table behind it
      with a wall-mounted monitor; hook rail on the south wall

Creates four collections (rebuilt each run, nothing else touched):
  Carpentry.MainBedroom   - wardrobe / cupboards, hanging system, tables, TV console or feature wall
  Furniture.MainBedroom   - queen bed, chairs
  Appliances.MainBedroom  - wall-mounted TV
  Accessories.MainBedroom - clothes, cosmetics (for scale)
It also registers the design's camera views in scene["room_cameras"] for render_views.py.

Run after build_flat.py:
    MB_DESIGN=2 Blender -b <file>.blend -P blender/scripts/build_main_bedroom.py
or send via the Blender MCP `execute_blender_code` tool (set os.environ["MB_DESIGN"] first).
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

DESIGN = os.environ.get("MB_DESIGN", "2")
DATA = os.path.join(ROOT, "blender", "data", f"main_bedroom_design{DESIGN}.json")

SLOTS = ["carcass", "front", "wood", "fabric", "linen", "mirror", "led", "black",
         "chrome", "duvet", "clothes_a", "clothes_b", "bottle_a", "bottle_b", "wall", "towel", "box", "basket", "monitor", "screen"]
S = {name: i for i, name in enumerate(SLOTS)}


def material(name, rgb, roughness=0.5, metallic=0.0, emission=0.0, alpha=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, val)
                except TypeError:
                    pass
    if emission:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = (*rgb, 1.0)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = (*rgb, alpha)
    return mat


def materials(fin):
    return [
        material("MB_Carcass", tuple(fin["carcass"]), 0.55),
        material("MB_Front", tuple(fin["front"]), 0.45),
        material("MB_Wood", tuple(fin["wood"]), 0.5),
        material("MB_Fabric", tuple(fin["fabric"]), 0.9),
        material("MB_Linen", tuple(fin["linen"]), 0.85),
        material("MB_Mirror", (0.9, 0.92, 0.94), 0.02, metallic=1.0),
        material("MB_LED", (1.0, 0.95, 0.85), 0.5, emission=3.0),
        material("MB_Black", (0.02, 0.02, 0.025), 0.15),
        material("MB_Chrome", (0.8, 0.8, 0.82), 0.15, metallic=1.0),
        material("MB_Duvet", (0.80, 0.76, 0.68), 0.9),
        material("MB_ClothesA", (0.25, 0.32, 0.45), 0.9),
        material("MB_ClothesB", (0.75, 0.55, 0.55), 0.9),
        material("MB_BottleA", (0.95, 0.85, 0.80), 0.2),
        material("MB_BottleB", (0.35, 0.55, 0.50), 0.2),
        material("MB_PartitionWall", (0.90, 0.90, 0.88), 0.8),
        material("MB_Towel", (0.85, 0.88, 0.90), 0.95),
        material("MB_StorageBox", (0.82, 0.76, 0.66), 0.7),
        material("MB_WireBasket", (0.95, 0.95, 0.95), 0.35, metallic=0.6),
        material("MB_MonitorBody", (0.03, 0.03, 0.035), 0.55),
        material("MB_Screen", (0.005, 0.006, 0.008), 0.05),
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
        if x1 <= x0 or y1 <= y0 or z1 <= z0:
            return
        quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        self._faces([[self._v(x, y, z0) for x, y in quad], [self._v(x, y, z1) for x, y in quad]], slot)

    def prism(self, p0, p1, t, z0, z1, slot):
        """Vertical panel of thickness t from plan point p0 to p1 (any angle)."""
        (x0, y0), (x1, y1) = p0, p1
        L = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / L * t / 2, (x1 - x0) / L * t / 2
        quad = ((x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny))
        self._faces([[self._v(x, y, z0) for x, y in quad], [self._v(x, y, z1) for x, y in quad]], slot)

    def cyl_z(self, cx, cy, r, z0, z1, slot, n=16):
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x, y, z0) for x, y in ring], [self._v(x, y, z1) for x, y in ring]], slot)

    def cyl_y(self, cx, cz, r, y0, y1, slot, n=12):
        """Cylinder along plan y (hanging rails in the wardrobe)."""
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x, y0, z) for x, z in ring], [self._v(x, y1, z) for x, z in ring]], slot)

    def cyl_x(self, cy, cz, r, x0, x1, slot, n=12):
        """Cylinder along plan x (hanging rails in the wardrobe)."""
        ring = [(cy + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x0, y, z) for y, z in ring], [self._v(x1, y, z) for y, z in ring]], slot)

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

class Leg:
    """One straight run of wardrobe in local coords: u along the run, d from the back wall (0) to the front."""

    def __init__(self, leg, depth):
        self.axis, self.back, self.depth = leg["axis"], leg["back"], leg.get("depth", depth)
        # +1 when the front faces +x (east) / +y (south), -1 for west / north.
        self.dir = 1 if leg["front"] in ("east", "south") else -1

    def _c(self, d):
        return self.back + self.dir * d

    def box(self, m, u0, u1, d0, d1, z0, z1, slot):
        a, b = sorted((self._c(d0), self._c(d1)))
        if self.axis == "y":   # run along the y axis, depth along x
            m.box(a, u0, b, u1, z0, z1, slot)
        else:                  # run along the x axis, depth along y
            m.box(u0, a, u1, b, z0, z1, slot)

    def rod(self, m, u0, u1, d, z, r, slot):
        if self.axis == "y":
            m.cyl_y(self._c(d), z, r, u0, u1, slot)
        else:
            m.cyl_x(self._c(d), z, r, u0, u1, slot)

    def bottle(self, m, u, d, r, z0, z1, slot):
        if self.axis == "y":
            m.cyl_z(self._c(d), u, r, z0, z1, slot)
        else:
            m.cyl_z(u, self._c(d), r, z0, z1, slot)


def drawers(L, m, u0, u1, z_top, n, t):
    """Stack of n drawer fronts from the floor to z_top, flush with the carcass front."""
    D, plinth = L.depth, 80
    L.box(m, u0, u1, t, D - t, 0, plinth, S["carcass"])
    h = (z_top - plinth) / n
    mid = (u0 + u1) / 2
    for k in range(n):
        z0 = plinth + k * h
        L.box(m, u0 + 2, u1 - 2, D - t, D, z0 + 2, z0 + h - 2, S["front"])
        L.box(m, mid - 80, mid + 80, D, D + 20, z0 + h - 40, z0 + h - 25, S["chrome"])


def wardrobe_leg(leg, d, m, a):
    L = Leg(leg, d["depth"])
    H, t, top_c, D = d["height"], d["board"], d["top_cabinet"], L.depth
    u0, u1 = leg["span"]
    L.box(m, u0, u1, 0, t, 0, H, S["carcass"])                    # back
    L.box(m, u0, u1, 0, D, H - t, H, S["carcass"])                # top
    L.box(m, u0, u1, 0, D, top_c - t, top_c, S["carcass"])        # top-cabinet shelf
    L.box(m, u0, u1, 0, D, 0, t, S["carcass"])                    # bottom
    edges = [u0]
    for sec in leg["sections"]:
        edges.append(edges[-1] + sec["width"])
    for e in edges:                                               # section side panels
        L.box(m, max(u0, e - t / 2), min(u1, e + t / 2), 0, D, 0, H, S["carcass"])
    for i, sec in enumerate(leg["sections"]):
        b0, b1 = edges[i] + t / 2, edges[i + 1] - t / 2
        n_top = max(1, round((b1 - b0) / 600))                    # top cabinet dividers
        for k in range(1, n_top):
            uu = b0 + k * (b1 - b0) / n_top
            L.box(m, uu - t / 2, uu + t / 2, 0, D, top_c, H - t, S["carcass"])
        kind = sec["kind"]
        if kind == "cosmetics":
            c = d["cosmetics"]
            drawers(L, m, b0, b1, c["drawers_top"], 3, t)
            L.box(m, b0, b1, t, t + c["counter_depth"], c["drawers_top"], c["counter"], S["wood"])
            L.box(m, b0 + 20, b1 - 20, t, t + 5, c["mirror"][0], c["mirror"][1], S["mirror"])
            L.box(m, b0, b1, t, t + 250, c["shelf"] - t, c["shelf"], S["wood"])
            L.box(m, b0 + 20, b1 - 20, t + 200, t + 215, c["shelf"] - t - 8, c["shelf"] - t, S["led"])
            for k, (du, r, h) in enumerate([(70, 30, 180), (140, 25, 140), (210, 35, 120), (330, 28, 160), (400, 22, 110)]):
                L.bottle(a, b0 + du, t + 90 + (k % 2) * 70, r, c["counter"], c["counter"] + h,
                         S["bottle_b" if k % 2 else "bottle_a"])
            for k in range(4):
                L.bottle(a, b0 + 70 + k * 100, t + 80, 25, c["shelf"], c["shelf"] + 130,
                         S["bottle_b" if k % 2 else "bottle_a"])
            continue
        if kind == "utility":
            u = d["utility"]
            for z in u["towel_shelves"] + [u["upper_shelf"]]:
                L.box(m, b0, b1, t, D, z - t, z, S["carcass"])
            lows = [t] + u["towel_shelves"][:-1]
            for z0 in lows:                                       # folded towel stacks
                for j in range(2):
                    uu = b0 + 30 + j * (b1 - b0 - 60) / 2
                    L.box(a, uu, uu + (b1 - b0 - 90) / 2, 60, D - 60, z0, z0 + 200, S["towel"])
            for z0 in (u["upper_shelf"], top_c):                  # storage boxes on top
                L.box(a, b0 + 20, b1 - 20, 40, D - 40, z0, z0 + 300 if z0 == u["upper_shelf"] else 450, S["box"])
            continue
        if kind == "shelves":
            z = d.get("shelf_spacing", 350)
            k = 1
            while z * k < top_c - 100:
                L.box(m, b0, b1, t, D - 20, z * k - t, z * k, S["carcass"])
                for j in range(int((b1 - b0) // 110)):            # small jars / bottles on each shelf
                    L.bottle(a, b0 + 60 + j * 110, D / 2, 30, z * k, z * k + 100 + (j % 3) * 30,
                             S["bottle_b" if (j + k) % 2 else "bottle_a"])
                k += 1
            continue
        if kind == "long_hang":
            rod_z, drop = d["long_hang_rod"], 1150
        else:
            drawers(L, m, b0, b1, d["drawers_top"], 3, t)
            L.box(m, b0, b1, t, D, d["drawers_top"], d["drawers_top"] + t, S["carcass"])
            rod_z, drop = d["short_hang_rod"], 800
        L.rod(m, b0, b1, D / 2, rod_z, 12, S["chrome"])
        slot = S["clothes_a"] if sec["owner"] == "His" else S["clothes_b"]
        n = int((b1 - b0 - 40) // 45)
        for k in range(n):                                        # garments, for scale
            gu = b0 + 30 + k * 45
            L.box(a, gu, gu + 12, D / 2 - 230, D / 2 + 230, rod_z - drop + (k % 3) * 60, rod_z - 30, slot)
    if d.get("show_doors"):
        L.box(m, u0, u1, D, D + t, 0, H, S["front"])


def desk(d, carp, furn):
    """Table with a drawer pedestal; the user sits on the south side (Design 1)."""
    x0, y0, x1, y1 = d["rect"]
    top, t = d["top"], d["thickness"]
    m = carp()
    m.box(x0, y0, x1, y1, top - t, top, S["wood"])
    p0, p1 = d["drawer"]
    ph = (top - t - 60) / 3
    m.box(p0, y0, p1, y1, 0, top - t, S["carcass"])
    for k in range(3):
        z0 = 60 + k * ph
        m.box(p0 + 3, y1, p1 - 3, y1 + 18, z0 + 3, z0 + ph - 3, S["front"])
    leg = x1 - 40 if p0 - x0 < 100 else x0                                     # leg panel at the free end
    m.box(leg, y0, leg + 40, y1, 0, top - t, S["carcass"])
    if "lamp" in d:
        lx, ly = d["lamp"]
        m.cyl_z(lx, ly, 70, top, top + 20, S["chrome"])
        m.cyl_z(lx, ly, 10, top + 20, top + 300, S["chrome"])
        m.cyl_z(lx, ly, 110, top + 250, top + 420, S["linen"])
    f = furn()
    chair(f, d["chair"], back="south")
    return m, f


def chair(f, c, back="south"):
    cx, cy = c["at"]
    s = c["size"] / 2
    f.box(cx - s, cy - s, cx + s, cy + s, 430, 470, S["fabric"])
    f.box(cx - s, cy + s - 40, cx + s, cy + s, 470, 850, S["fabric"])
    for px in (cx - s + 20, cx + s - 40):
        for py in (cy - s + 20, cy + s - 40):
            f.box(px, py, px + 20, py + 20, 0, 430, S["chrome"])


def bed(d, furn):
    """Queen bed; headboard on the north (window) or east wall."""
    x0, y0, x1, y1 = d["rect"]
    hb = d["headboard"]
    fz, mz, ht = d["frame_height"], d["mattress"], hb["thickness"]
    f = furn()
    top = fz + mz
    if hb["side"] == "east":
        xh = x1 - ht
        f.box(xh, y0, x1, y1, 0, hb["height"], S["fabric"])                       # headboard
        f.box(x0 + 30, y0 + 30, xh - 30, y1 - 30, 0, 100, S["black"])             # recessed plinth
        f.box(x0, y0, xh, y1, 100, fz, S["fabric"])                               # frame
        f.box(x0 + 10, y0 + 10, xh - 5, y1 - 10, fz, top, S["linen"])             # mattress
        f.box(x0 + 5, y0 + 5, xh - 600, y1 - 5, top - 120, top + 40, S["duvet"])  # duvet (folded back)
        w = (y1 - y0 - 60) / 2
        for k in range(2):                                                        # pillows
            py = y0 + 20 + k * (w + 20)
            f.box(xh - 480, py, xh - 40, py + w, top, top + 120, S["linen"])
    else:  # north
        yh = y0 + ht
        f.box(x0, y0, x1, yh, 0, hb["height"], S["fabric"])
        f.box(x0 + 30, yh + 30, x1 - 30, y1 - 30, 0, 100, S["black"])
        f.box(x0, yh, x1, y1, 100, fz, S["fabric"])
        f.box(x0 + 10, yh + 5, x1 - 10, y1 - 10, fz, top, S["linen"])
        f.box(x0 + 5, yh + 600, x1 - 5, y1 - 5, top - 120, top + 40, S["duvet"])
        w = (x1 - x0 - 60) / 2
        for k in range(2):
            px = x0 + 20 + k * (w + 20)
            f.box(px, yh + 40, px + w, yh + 480, top, top + 120, S["linen"])
    return f


def feature_wall(d, carp):
    """Full-height partition with vertical timber slats on the bed (north) side."""
    x0, y0, x1, y1 = d["rect"]
    H, sl = d["height"], d["slats"]
    m = carp()
    m.box(x0, y0, x1, y1, 0, H, S["carcass"])
    x = x0 + sl["gap"] / 2
    while x + sl["width"] <= x1:
        m.box(x, y0 - sl["depth"], x + sl["width"], y0, 0, H, S["wood"])
        x += sl["width"] + sl["gap"]
    m.box(x0 - 20, y0 - sl["depth"], x0, y1, 0, H, S["wood"])                     # end cap
    return m


def tv(d, carp, appl):
    """Wall-mounted TV: on the west wall facing east (+ floating console), or on a north-facing wall."""
    w, h, cz = d["width"], d["height"], d["center_z"]
    a = appl()
    faces = d.get("faces", "east")
    if faces == "north":
        cx, wy = d["center_x"], d["wall_y"]
        a.box(cx - w / 2, wy - 30, cx + w / 2, wy, cz - h / 2, cz + h / 2, S["black"])
    else:
        wx, cy = d["wall_x"], d["center_y"]
        a.box(wx, cy - w / 2, wx + 30, cy + w / 2, cz - h / 2, cz + h / 2, S["black"])
    m = None
    if "console" in d:
        x0, y0, x1, y1 = d["console"]["rect"]
        z0, z1 = d["console"]["z"]
        m = carp()
        m.box(x0, y0, x1, y1, z0, z1, S["carcass"])
        m.box(x1, y0, x1 + 3, y1, z0, z0 + 40, S["wood"])                         # wood lip at the front
    return m, a


def partitions(parts, m):
    """Plain partition walls, rect + height (optionally from z[0], e.g. a header)."""
    for p in parts:
        x0, y0, x1, y1 = p["rect"]
        m.box(x0, y0, x1, y1, p.get("z", [0, 0])[0], p.get("height", 2600), S["wall"])


def vanity(d, m, a, furn):
    """Vanity table against a wall: optional drawer pedestal, knee space, optional mirror + LED above."""
    L = Leg(d, d["depth"])
    u0, u1 = d["span"]
    top, t = d["top"], 25
    L.box(m, u0, u1, 0, L.depth, top - t, top, S["wood"])                         # top
    if "drawer" in d:                       # drawer pedestal + leg panel; otherwise a floating top
        du0, du1 = d["drawer"]              # fixed to the walls on three sides
        L.box(m, du0, du1, 0, L.depth, 0, top - t, S["carcass"])
        ph = (top - t - 60) / 3
        for k in range(3):
            z0 = 60 + k * ph
            L.box(m, du0 + 3, du1 - 3, L.depth, L.depth + 18, z0 + 3, z0 + ph - 3, S["front"])
        free = u1 - 40 if du0 - u0 < 100 else u0
        L.box(m, free, free + 40, 0, L.depth, 0, top - t, S["carcass"])
    if "mirror" in d:
        z0, z1 = d["mirror"]
        L.box(m, u0 + 30, u1 - 30, 0, 5, z0, z1, S["mirror"])
        L.box(m, u0 + 30, u1 - 30, 0, 60, z1, z1 + 15, S["led"])                  # light bar over the mirror
    for k, (du, r, h) in enumerate([(80, 30, 170), (150, 24, 130), (230, 34, 110), (420, 26, 150), (500, 22, 100)]):
        L.bottle(a, u0 + du, 90 + (k % 2) * 60, r, top, top + h, S["bottle_b" if k % 2 else "bottle_a"])
    if "stool" in d:
        cx, cy = d["stool"]["at"]
        furn.cyl_z(cx, cy, d["stool"]["size"] / 2, 0, 450, S["fabric"], n=24)


def pole_closet(d, m, a):
    """Open hanging system on the west wall (no carpentry): wall standards + brackets, poles, wire shelf,
    optional stack of wire baskets under part of the upper pole."""
    back, (y0, y1), D = d["back"], d["span"], d["depth"]
    sh, up, lo = d["shelf"], d["upper_pole"], d["lower_pole"]
    n = max(2, round((y1 - y0) / d["standard_spacing"]) + 1)
    ys = [y0 + 40 + k * (y1 - y0 - 80) / (n - 1) for k in range(n)]
    for y in ys:
        m.box(back, y - 12, back + 15, y + 12, 400, 2300, S["chrome"])                  # wall standard
        m.box(back, y - 6, back + sh["depth"], y + 6, sh["z"] - 50, sh["z"] - 30, S["chrome"])  # shelf bracket
        m.box(back + up["d"] - 8, y - 6, back + up["d"] + 8, y + 6, up["z"], sh["z"] - 50, S["chrome"])
    # wire shelf: thin frame + bars
    m.box(back, y0, back + sh["depth"], y1, sh["z"] - 30, sh["z"] - 25, S["chrome"])
    m.cyl_y(back + up["d"], up["z"], 14, y0, y1, S["chrome"])                          # upper pole
    ly0, ly1 = lo["span"]
    m.cyl_y(back + lo["d"], lo["z"], 14, ly0, ly1, S["chrome"])                        # lower pole
    for y in (ly0 + 40, ly1 - 40):
        m.box(back, y - 6, back + lo["d"] + 8, y + 6, lo["z"] - 10, lo["z"] + 10, S["chrome"])  # lower brackets
    bk = d.get("baskets")
    if bk:
        wire_baskets(bk, back, m, a)
    # garments for scale: short hang over the lower pole / baskets, long hang elsewhere
    k = 0
    y = y0 + 30
    while y < y1 - 30:
        double = ly0 <= y <= ly1
        over_baskets = bk and bk["span"][0] <= y <= bk["span"][1]
        slot = S["clothes_a"] if (y // 400) % 2 else S["clothes_b"]
        drop = 800 if (double or over_baskets) else 1150
        a.box(back + up["d"] - 230, y, back + up["d"] + 230, y + 12, up["z"] - drop + (k % 3) * 60, up["z"] - 30, slot)
        if double:
            a.box(back + lo["d"] - 230, y, back + lo["d"] + 230, y + 12, lo["z"] - 600 + (k % 2) * 40, lo["z"] - 30,
                  S["black"])
        y += 45
        k += 1
    # storage boxes on the wire shelf
    yy = y0 + 40
    while yy + 380 < y1:
        a.box(back + 40, yy, back + sh["depth"] - 40, yy + 360, sh["z"], sh["z"] + 260, S["box"])
        yy += 420


def wire_baskets(d, back, m, a):
    """Stack of pull-out wire baskets on a floor-standing frame (part of the bracket system)."""
    (y0, y1), D, h = d["span"], d["depth"], d["height"]
    for y in (y0 + 10, y1 - 30):                                                     # side frames
        m.box(back + 20, y, back + 40, y + 20, 0, d["levels"][-1] + h + 20, S["chrome"])
        m.box(back + D - 40, y, back + D - 20, y + 20, 0, d["levels"][-1] + h + 20, S["chrome"])
    for z in d["levels"]:
        bx0, bx1, by0, by1 = back + 30, back + D - 30, y0 + 35, y1 - 35
        if d.get("pulled_out") == z:                                                 # one basket pulled out
            bx0, bx1 = bx0 + 250, bx1 + 250
        m.box(bx0, by0, bx1, by1, z, z + 6, S["basket"])                             # wire base
        for x0_, x1_ in ((bx0, bx0 + 5), (bx1 - 5, bx1)):
            m.box(x0_, by0, x1_, by1, z, z + h, S["basket"])
        for y0_, y1_ in ((by0, by0 + 5), (by1 - 5, by1)):
            m.box(bx0, y0_, bx1, y1_, z, z + h, S["basket"])
        m.box(bx1, (by0 + by1) / 2 - 60, bx1 + 15, (by0 + by1) / 2 + 60, z + h - 40, z + h - 20, S["chrome"])
        a.box(bx0 + 20, by0 + 20, bx1 - 20, by1 - 20, z + 6, z + h - 40,               # folded clothes inside
              S["clothes_a"] if d["levels"].index(z) % 2 else S["linen"])


def bifold_doors(d, m):
    """Bi-fold wardrobe doors across a north-south opening at x, opening east into the room.

    `open` lists each pair's state: 0 = closed flat, 1 = fully folded against its hinge jamb.
    """
    x, (y0, y1), H = d["x"], d["span"], d["height"]
    n = len(d["open"])
    pair = (y1 - y0) / n
    leaf, t = pair / 2 - 3, 20
    m.box(x - 25, y0, x + 25, y1, H - 40, H, S["chrome"])                           # top track
    for k, f in enumerate(d["open"]):
        ys = y0 + k * pair + 2
        ang = math.radians(5 + 80 * f) if f > 0 else 0.0
        apex = (x + leaf * math.sin(ang), ys + leaf * math.cos(ang))
        end = (x, ys + 2 * leaf * math.cos(ang))
        m.prism((x, ys), apex, t, 10, H - 45, S["front"])
        m.prism(apex, end, t, 10, H - 45, S["front"])
        hx, hy = end[0] + (apex[0] - end[0]) * 0.1, end[1] + (apex[1] - end[1]) * 0.1  # handle near the free edge
        m.box(hx + 10, hy - 8, hx + 30, hy + 8, 900, 1300, S["chrome"])


def hook_rail(d, m, a):
    """Wall rail with hooks for towels, bags and clothes (on a south wall, hooks pointing north)."""
    (x0, x1), wy, z = d["x"], d["wall_y"], d["z"]
    m.box(x0, wy - 25, x1, wy + 25, z - 40, z + 40, S["wood"])                         # timber rail
    n = d["hooks"]
    xs = [x0 + 60 + k * (x1 - x0 - 120) / (n - 1) for k in range(n)]
    for hx in xs:
        m.box(hx - 6, wy - 85, hx + 6, wy - 25, z - 10, z + 2, S["chrome"])           # hook arm
        m.box(hx - 6, wy - 95, hx + 6, wy - 85, z - 10, z + 40, S["chrome"])          # upturned tip
    for it in d.get("items", []):                                                     # things hanging, for scale
        hx = xs[it["hook"]]
        w, L, kind = it["width"], it["length"], it["kind"]
        if kind == "bag":
            a.box(hx - w / 2, wy - 200, hx + w / 2, wy - 60, z - 120 - L, z - 120, S["fabric"])
            a.prism((hx - w / 2 + 40, wy - 130), (hx, wy - 90), 15, z - 120, z - 5, S["black"])
            a.prism((hx, wy - 90), (hx + w / 2 - 40, wy - 130), 15, z - 120, z - 5, S["black"])
        else:  # towel / clothes: draped flat over the hook
            a.box(hx - w / 2, wy - 110, hx + w / 2, wy - 80, z - L, z + 30,
                  S["towel"] if kind == "towel" else S["clothes_a"])


def wall_monitor(d, appl):
    """Curved monitor on a VESA wall arm, facing south off a north-side wall (the back of the feature wall).

    Modelled on the PRISM+ X340 PRO: 1500R curve, thin curved panel, rounded housing bulge at the back.
    """
    cx, wy, cz = d["center_x"], d["wall_y"], d["center_z"]
    W, H, R = d["width"], d["height"], d["curve_radius"]
    pt, bulge, off = d["panel_depth"], d["housing_depth"], d["standoff"]
    bs, bt, bb = d["bezel"]                                  # side, top, bottom bezel
    a = appl()
    # Circle centre on the viewer's side (+y); the screen centre is the deepest point.
    yc = wy + off + bulge + pt + R
    phi = math.asin((W / 2) / R)
    n = 32

    def arc(r, th):
        return (cx + r * math.sin(th), yc - r * math.cos(th))

    z0, z1 = cz - H / 2, cz + H / 2
    for k in range(n):                                       # curved panel body
        t0, t1 = -phi + 2 * phi * k / n, -phi + 2 * phi * (k + 1) / n
        a.prism(arc(R + pt / 2, t0), arc(R + pt / 2, t1), pt, z0, z1, S["monitor"])
    phs = math.asin((W / 2 - bs) / R)                        # screen inside the bezels
    for k in range(n):
        t0, t1 = -phs + 2 * phs * k / n, -phs + 2 * phs * (k + 1) / n
        a.prism(arc(R - 0.5, t0), arc(R - 0.5, t1), 1.5, z0 + bb, z1 - bt, S["screen"])
    a.box(cx - 30, yc - R - 2, cx + 30, yc - R, z0 + 5, z0 + 12, S["chrome"])  # logo on the chin
    # Rounded housing bulge at the back (two stepped blocks), then VESA plate + arm to the wall plate.
    yb = yc - R - pt                                         # back of the panel at the centre
    a.box(cx - 300, yb - bulge * 0.5, cx + 300, yb, cz - 150, cz + 120, S["monitor"])
    a.box(cx - 200, yb - bulge, cx + 200, yb - bulge * 0.5, cz - 110, cz + 80, S["monitor"])
    v = d["vesa"] / 2 + 15
    a.box(cx - v, yb - bulge - 8, cx + v, yb - bulge, cz - v - 15, cz + v - 15, S["black"])
    a.box(cx - 20, wy + 10, cx + 20, yb - bulge - 8, cz - 35, cz + 5, S["black"])    # arm
    a.box(cx - 50, wy, cx + 50, wy + 10, cz - 90, cz + 60, S["black"])               # wall plate
    return a


def office_chair(f, at, faces):
    """Office chair: 5-star base, gas column, seat, backrest. `faces` = direction the user looks."""
    cx, cy = at
    for k in range(5):                                                                # star base
        ang = 2 * math.pi * k / 5
        ex, ey = cx + 320 * math.cos(ang), cy + 320 * math.sin(ang)
        f.prism((cx, cy), (ex, ey), 40, 60, 100, S["black"])
        f.cyl_z(ex, ey, 25, 0, 60, S["black"])
    f.cyl_z(cx, cy, 25, 100, 430, S["chrome"])
    f.box(cx - 250, cy - 250, cx + 250, cy + 250, 430, 490, S["black"])
    back = {"north": (0, 1), "south": (0, -1), "east": (-1, 0), "west": (1, 0)}[faces]  # backrest opposite
    bx, by = cx + back[0] * 240, cy + back[1] * 240
    if back[0]:
        f.box(bx - 20, cy - 230, bx + 20, cy + 230, 520, 1050, S["black"])
    else:
        f.box(cx - 230, by - 20, cx + 230, by + 20, 520, 1050, S["black"])


def l_desk(d, carp, furn):
    """L-shaped study table, no cabinets below: tops + end panels + a corner post, wall cabinets above."""
    top, t = d["top"], d["thickness"]
    m = carp()
    for x0, y0, x1, y1 in d["tops"]:
        m.box(x0, y0, x1, y1, top - t, top, S["wood"])
    for x0, y0, x1, y1 in d["panels"]:
        m.box(x0, y0, x1, y1, 0, top - t, S["carcass"])
    for px, py in d["posts"]:
        m.box(px, py - 40, px + 40, py, 0, top - t, S["chrome"])
    o = d["overhead"]
    x0, y0, x1, y1 = o["rect"]
    z0, z1 = o["z"]
    m.box(x0 + 18, y0, x1, y1, z0, z1, S["carcass"])                                  # wall cabinet body
    dw = (y1 - y0) / o["doors"]
    for k in range(o["doors"]):                                                       # doors facing west
        m.box(x0, y0 + k * dw + 2, x0 + 18, y0 + (k + 1) * dw - 2, z0 + 2, z1 - 2, S["front"])
        hy = y0 + (k + 1) * dw - 60 if k % 2 == 0 else y0 + k * dw + 40
        m.box(x0 - 20, hy, x0, hy + 20, z0 + 40, z0 + 200, S["chrome"])
    m.box(x0 + 30, y0 + 20, x0 + 80, y1 - 20, z0 - 15, z0, S["led"])                  # task light under
    f = furn()
    for c in d["chairs"]:
        office_chair(f, c["at"], c["faces"])
    return m, f


def wall_mirrors(items, m):
    """Full-length mirrors on a wall: timber frame + mirror face."""
    for it in items:
        z0, z1 = it["z"]
        fr = 30
        if it["wall"] == "south":       # mirror on a south wall, facing north
            (x0, x1), y = it["x"], it["wall_y"]
            m.box(x0, y - 30, x1, y, z0, z1, S["wood"])
            m.box(x0 + fr, y - 35, x1 - fr, y - 30, z0 + fr, z1 - fr, S["mirror"])
        elif it["wall"] == "north":     # on a north wall, facing south
            (x0, x1), y = it["x"], it["wall_y"]
            m.box(x0, y, x1, y + 30, z0, z1, S["wood"])
            m.box(x0 + fr, y + 30, x1 - fr, y + 35, z0 + fr, z1 - fr, S["mirror"])


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
    mats = materials(data["finishes"])
    carp = child_collection("Carpentry", "Carpentry.MainBedroom")
    furn = child_collection("Furniture", "Furniture.MainBedroom")
    appl = child_collection("Appliances", "Appliances.MainBedroom")
    acc = child_collection("Accessories", "Accessories.MainBedroom")

    if "wardrobe" in data:
        wm, wa = Mesh(), Mesh()
        for leg in data["wardrobe"]["legs"]:
            wardrobe_leg(leg, data["wardrobe"], wm, wa)
        wm.finish("MB_Wardrobe", carp, mats)
        wa.finish("MB_Wardrobe_Contents", acc, mats)
    if "desk" in data:
        dm, ch = desk(data["desk"], Mesh, Mesh)
        dm.finish("MB_Desk", carp, mats)
        ch.finish("MB_DeskChair", furn, mats)
    if "l_desk" in data:
        dm, ch = l_desk(data["l_desk"], Mesh, Mesh)
        dm.finish("MB_StudyTable", carp, mats)
        ch.finish("MB_OfficeChairs", furn, mats)
    if "pole_closet" in data:
        pm, pa = Mesh(), Mesh()
        pole_closet(data["pole_closet"], pm, pa)
        pm.finish("MB_HangingSystem", carp, mats)
        pa.finish("MB_HangingClothes", acc, mats)
    if "bifold" in data:
        bm_ = Mesh()
        bifold_doors(data["bifold"], bm_)
        bm_.finish("MB_WardrobeBifold", carp, mats)
    if "hook_rail" in data:
        hm, ha = Mesh(), Mesh()
        hook_rail(data["hook_rail"], hm, ha)
        hm.finish("MB_HookRail", carp, mats)
        ha.finish("MB_HookRail_Items", acc, mats)
    if "monitor" in data:
        wall_monitor(data["monitor"], Mesh).finish("MB_Monitor", appl, mats)
    bed(data["bed"], Mesh).finish("MB_Bed", furn, mats)
    cm, tm = tv(data["tv"], Mesh, Mesh)
    if cm:
        cm.finish("MB_TVConsole", carp, mats)
    tm.finish("MB_TV", appl, mats)
    if "feature_wall" in data:
        feature_wall(data["feature_wall"], Mesh).finish("MB_FeatureWall", carp, mats)
    if "partitions" in data:
        pm = Mesh()
        partitions(data["partitions"], pm)
        pm.finish("MB_Partitions", carp, mats)
    if "vanity" in data:
        vm, va, vf = Mesh(), Mesh(), Mesh()
        vanity(data["vanity"], vm, va, vf)
        vm.finish("MB_Vanity", carp, mats)
        va.finish("MB_Vanity_Cosmetics", acc, mats)
        if "stool" in data["vanity"]:
            vf.finish("MB_VanityStool", furn, mats)
        else:
            vf.bm.free()
    if "mirrors" in data:
        mm = Mesh()
        wall_mirrors(data["mirrors"], mm)
        mm.finish("MB_FullLengthMirror", carp, mats)

    # Register this design's camera views for render_views.py (replacing any old main-bedroom ones).
    scene = bpy.context.scene
    cams = {k: v for k, v in json.loads(scene.get("room_cameras", "{}")).items() if not k.startswith("mbr_")}
    cams.update(data.get("cameras", {}))
    scene["room_cameras"] = json.dumps(cams)
    scene["mb_design"] = DESIGN
    print(f"[main bedroom] built design {DESIGN}")


main()
