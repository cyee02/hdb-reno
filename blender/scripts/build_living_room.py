"""Build the living room from blender/data/living_room.json.

Creates these collections (rebuilt each run, nothing else touched):
  Carpentry.Living   - walnut slat TV feature wall, floating TV console
  Appliances.Living  - 65" TV
  Furniture.Living   - 3-seater sofa, armchair, coffee table, side table, rug
  Accessories.Living - floor lamp, plant
It also registers the living-room camera views (liv_*) in scene["room_cameras"].

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_living_room.py
or send via the Blender MCP `execute_blender_code` tool.
"""
import importlib
import json
import os
import sys

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "living_room.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "living_room.json")
sys.path.insert(0, os.path.join(ROOT, "blender", "scripts"))
import door_motion  # noqa: E402
import room_kit as rk  # noqa: E402
importlib.reload(door_motion)
importlib.reload(rk)

SLOTS = ["fabric", "cushion", "oak", "walnut", "white", "rug", "black", "glass_dark",
         "ceramic", "leaf", "shade", "steel", "accent"]
S = {name: i for i, name in enumerate(SLOTS)}


def materials(fin):
    return [
        rk.material("LV_Fabric", tuple(fin["fabric"]), 0.9),
        rk.material("LV_Cushion", tuple(fin["cushion"]), 0.9),
        rk.material("LV_Oak", tuple(fin["oak"]), 0.5),
        rk.material("LV_Walnut", tuple(fin["walnut"]), 0.55),
        rk.material("LV_White", tuple(fin["white"]), 0.45),
        rk.material("LV_Rug", tuple(fin["rug"]), 1.0),
        rk.material("LV_Black", (0.04, 0.04, 0.04), 0.4),
        rk.material("LV_Screen", (0.02, 0.025, 0.03), 0.05),
        rk.material("LV_Ceramic", (0.90, 0.88, 0.84), 0.3),
        rk.material("LV_Leaf", (0.20, 0.42, 0.18), 0.7),
        rk.material("LV_Shade", (0.97, 0.93, 0.85), 0.8, emission=1.5),
        rk.material("LV_Steel", (0.75, 0.74, 0.72), 0.3, metallic=1.0),
        rk.material("LV_Accent", tuple(fin["accent"]), 0.8),
    ]


def tv_wall(d, m):
    x0, y0, x1, y1 = d["rect"]
    m.box(x0, y0, x0 + 18, y1, 0, 2600, S["walnut"])                  # backing board
    y, pitch = y0 + d["slat_gap"] / 2, d["slat"] + d["slat_gap"]
    while y + d["slat"] <= y1:
        m.box(x0 + 18, y, x1, y + d["slat"], 0, 2600, S["walnut"])     # vertical slats
        y += pitch


def console(d, m):
    f = rk.Frame(m, d["rect"], d["front"])
    z0, z1 = d["z"]
    f.box(f.a0, f.a1, -f.depth, -18, z0, z1 - 25, S["white"])         # carcass
    f.box(f.a0, f.a1, -f.depth, 0, z1 - 25, z1, S["oak"])              # oak top
    n = d["drawers"]
    w = (f.a1 - f.a0) / n
    for k in range(n):                                                 # handle-less push fronts
        f.box(f.a0 + k * w + 2, f.a0 + (k + 1) * w - 2, -18, 0, z0 + 2, z1 - 27, S["white"])
    f.box(f.a0 + 30, f.a1 - 30, -f.depth + 40, -60, z0 - 4, z0, S["shade"])  # LED glow under


def tv(d, m):
    cy, (x0, x1) = d["centre_y"], d["x"]
    w, h = d["size"]
    z0 = d["bottom"]
    m.box(x0, cy - w / 2, x1, cy + w / 2, z0, z0 + h, S["black"])
    m.box(x1, cy - w / 2 + 8, x1 + 2, cy + w / 2 - 8, z0 + 8, z0 + h - 8, S["glass_dark"])


def sofa(d, m):
    """Upholstered sofa/armchair: low base, seat cushions, back cushions, arms."""
    f = rk.Frame(m, d["rect"], d["front"])
    a0, a1, D = f.a0, f.a1, f.depth
    arm, back = 180, 220
    for a in (a0 + 60, a1 - 100):                                      # legs
        for dd in (-80, -D + 80):
            f.box(a, a + 40, dd - 40, dd, 0, 100, S["walnut"])
    f.box(a0, a1, -D, 0, 100, 280, S["fabric"])                        # base
    f.box(a0, a0 + arm, -D, 0, 280, 600, S["fabric"])                  # arms
    f.box(a1 - arm, a1, -D, 0, 280, 600, S["fabric"])
    f.box(a0 + arm, a1 - arm, -D, -D + back, 280, 820, S["fabric"])    # back frame
    n = d["seats"]
    w = (a1 - a0 - 2 * arm) / n
    for k in range(n):
        s, e = a0 + arm + k * w + 5, a0 + arm + (k + 1) * w - 5
        f.box(s, e, -D + back, -10, 280, 430, S["cushion"])            # seat cushion
        f.box(s, e, -D + back, -D + back + 170, 430, 800, S["cushion"])  # back cushion
    if n > 1:                                                          # throw cushions
        f.box(a0 + arm + 40, a0 + arm + 450, -D + back + 170, -D + back + 290, 430, 830, S["accent"])
        f.box(a1 - arm - 450, a1 - arm - 40, -D + back + 170, -D + back + 290, 430, 830, S["accent"])


def coffee_table(d, m):
    x0, y0, x1, y1 = d["rect"]
    h = d["height"]
    m.box(x0, y0, x1, y1, h - 30, h, S["oak"])
    m.box(x0 + 60, y0 + 60, x1 - 60, y1 - 60, 120, 140, S["oak"])      # lower shelf
    for lx, ly in ((x0 + 40, y0 + 40), (x1 - 80, y0 + 40), (x0 + 40, y1 - 80), (x1 - 80, y1 - 80)):
        m.box(lx, ly, lx + 40, ly + 40, 0, h - 30, S["black"])


def main():
    with open(DATA) as fh:
        d = json.load(fh)
    mats = materials(d["finishes"])
    carp = rk.child_collection("Carpentry", "Carpentry.Living")
    appl = rk.child_collection("Appliances", "Appliances.Living")
    furn = rk.child_collection("Furniture", "Furniture.Living")
    acc = rk.child_collection("Accessories", "Accessories.Living")

    m = rk.Mesh(); tv_wall(d["tv_wall"], m); m.finish("LV_TV feature wall (walnut slats)", carp, mats)
    m = rk.Mesh(); console(d["console"], m); m.finish("LV_TV console (floating)", carp, mats)
    m = rk.Mesh(); tv(d["tv"], m); m.finish("LV_TV 65in", appl, mats)
    m = rk.Mesh(); sofa(d["sofa"], m); m.finish("LV_Sofa 3-seater", furn, mats)
    m = rk.Mesh(); sofa(d["armchair"], m); m.finish("LV_Armchair", furn, mats)
    m = rk.Mesh(); coffee_table(d["coffee_table"], m); m.finish("LV_Coffee table", furn, mats)
    m = rk.Mesh()
    x0, y0, x1, y1 = d["rug"]["rect"]
    m.box(x0, y0, x1, y1, 1, 13, S["rug"])
    m.finish("LV_Rug", furn, mats)

    st = d["side_table"]
    m = rk.Mesh()
    (cx, cy), r, h = st["at"], st["r"], st["height"]
    m.cyl(cx, cy, r, h - 25, h, S["oak"], 32)
    m.cyl(cx, cy, 25, 20, h - 25, S["black"], 12)
    m.cyl(cx, cy, 160, 0, 20, S["black"], 32)
    m.finish("LV_Side table", furn, mats)

    m = rk.Mesh()
    cx, cy = d["floor_lamp"]["at"]
    m.cyl(cx, cy, 150, 0, 20, S["black"], 32)
    m.cyl(cx, cy, 12, 20, 1450, S["steel"], 12)
    m.cyl(cx, cy, 210, 1450, 1750, S["shade"], 32)
    m.finish("LV_Floor lamp", acc, mats)

    m = rk.Mesh()
    cx, cy = d["plant"]["at"]
    m.cyl(cx, cy, 190, 0, 420, S["ceramic"], 32)
    for r, z0, z1 in ((300, 420, 900), (240, 900, 1300), (150, 1300, 1650)):
        m.cyl(cx, cy, r, z0, z1, S["leaf"], 10)
    m.finish("LV_Plant", acc, mats)

    rk.register_cameras("liv_", d.get("cameras", {}))
    print(f"Living: {len(carp.objects)} carpentry, {len(appl.objects)} appliance, "
          f"{len(furn.objects)} furniture, {len(acc.objects)} accessory objects")


main()
