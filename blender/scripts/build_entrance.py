"""Build the entrance / foyer from blender/data/entrance.json.

Creates these collections (rebuilt each run, nothing else touched):
  Carpentry.Entrance   - cupboard C2: shoe cabinet + key surface + niche, shoe-on seat with
                         drawers + alcove, top cabinets to the ceiling
  Accessories.Entrance - key tray + keys, a pair of shoes
It also registers the foyer camera views (foy_*) in scene["room_cameras"].

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_entrance.py
or send via the Blender MCP `execute_blender_code` tool.
"""
import importlib
import json
import os
import sys

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "entrance.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "entrance.json")
sys.path.insert(0, os.path.join(ROOT, "blender", "scripts"))
import door_motion  # noqa: E402
import room_kit as rk  # noqa: E402
importlib.reload(door_motion)
importlib.reload(rk)

SLOTS = ["carcass", "front", "oak", "cushion", "black", "led", "chrome", "leather"]
S = {name: i for i, name in enumerate(SLOTS)}
B = 18  # board thickness


def doors(f, a0, a1, z0, z1, n, handle_z=None):
    """n equal fronts across a0-a1 with a slim black bar handle on the meeting edges."""
    w = (a1 - a0) / n
    for k in range(n):
        f.box(a0 + k * w + 1.5, a0 + (k + 1) * w - 1.5, 0, B, z0 + 1.5, z1 - 1.5, S["front"])
        if handle_z:
            hx = a0 + (k + 1) * w - 40 if k % 2 == 0 else a0 + k * w + 28
            f.box(hx, hx + 12, B, B + 15, handle_z[0], handle_z[1], S["black"])


def drawers(f, a0, a1, z0, z1, n):
    h = (z1 - z0) / n
    for k in range(n):
        f.box(a0 + 1.5, a1 - 1.5, 0, B, z0 + k * h + 1.5, z0 + (k + 1) * h - 1.5, S["front"])
        mid = (a0 + a1) / 2
        f.box(mid - 80, mid + 80, B, B + 12, z0 + (k + 1) * h - 45, z0 + (k + 1) * h - 33, S["black"])


def hooks(f, a0, a1, n, z, depth):
    for k in range(n):
        a = a0 + (k + 1) * (a1 - a0) / (n + 1)
        f.box(a - 8, a + 8, -depth + B, -depth + B + 60, z - 8, z + 8, S["black"])
        f.box(a - 8, a + 8, -depth + B + 45, -depth + B + 60, z, z + 30, S["black"])


def c2(c, m):
    f = rk.Frame(m, c["rect"], c["front"])
    a0, a1, D = f.a0, f.a1, f.depth
    split, kick = c["split"], c["kick"]
    t0, t1 = c["top_cabinets"]["z"]
    # Carcass: ends, back, recessed kick, divider between the two columns.
    f.box(a0, a0 + B, -D, 0, 0, t1, S["carcass"])
    f.box(a1 - B, a1, -D, 0, 0, t1, S["carcass"])
    f.box(a0, a1, -D, -D + B, kick, t1, S["carcass"])
    f.box(a0 + B, a1 - B, -D + B, -60, 0, kick, S["carcass"])
    f.box(split - B / 2, split + B / 2, -D + B, 0, kick, t0, S["carcass"])

    # Top cabinets across both columns.
    f.box(a0 + B, a1 - B, -D + B, 0, t0, t0 + B, S["carcass"])
    doors(f, a0, a1, t0, t1, c["top_cabinets"]["doors"], handle_z=(t0 + 30, t0 + 200))
    f.box(a0 + 30, a1 - 30, -60, -40, t0 - 4, t0, S["led"])               # LED under the top cabinets

    # Left (north) column: shoe cabinet, key surface, open niche.
    sc = c["surface_column"]
    s0, s1 = a0 + B, split - B / 2
    z0, z1 = sc["shoe_cabinet"]["z"]
    for z in sc["shoe_cabinet"]["shelves"]:
        f.box(s0, s1, -D + B, -20, z - B, z, S["carcass"])
    doors(f, a0, split, z0, z1, sc["shoe_cabinet"]["doors"], handle_z=(z1 - 220, z1 - 60))
    sz0, sz1 = sc["surface"]["z"]
    f.box(a0, split, -D + B, sc["surface"]["projects"], sz0, sz1, S["oak"])
    nz0, nz1 = sc["niche"]["z"]
    f.box(s0, s1, -D + B, -D + B + 10, nz0, nz1, S["oak"])               # oak back
    hooks(f, s0 + 100, s1 - 100, sc["niche"]["hooks"], nz0 + 450, D)

    # Right (south) column: drawers, seat + cushion, open alcove.
    st = c["seat_column"]
    r0, r1 = split + B / 2, a1 - B
    dz0, dz1 = st["drawers"]["z"]
    f.box(r0, r1, -D + B, -20, dz0, dz1, S["carcass"])
    drawers(f, split, a1, dz0, dz1, st["drawers"]["count"])
    se0, se1 = st["seat"]["z"]
    f.box(split, a1, -D + B, st["seat"]["projects"], se0, se1, S["oak"])
    f.box(r0 + 10, r1 - 10, -D + B + 40, st["seat"]["projects"] - 10, se1, se1 + st["seat"]["cushion"], S["cushion"])
    az0, az1 = st["alcove"]["z"]
    f.box(r0, r1, -D + B, -D + B + 10, se1, az1, S["oak"])
    hooks(f, r0, r1, st["alcove"]["hooks"], st["alcove"]["hook_z"], D)


def accessories(c, m):
    f = rk.Frame(m, c["rect"], c["front"])
    sc = c["surface_column"]
    top = sc["surface"]["z"][1]
    mid = (f.a0 + c["split"]) / 2
    f.box(mid - 150, mid + 150, -260, -60, top, top + 20, S["oak"])       # key tray
    f.box(mid - 110, mid - 40, -200, -150, top + 20, top + 28, S["chrome"])  # keys
    f.box(mid + 20, mid + 110, -220, -120, top + 20, top + 32, S["leather"])  # wallet
    # Pair of sneakers in front of the seat.
    sm = (c["split"] + f.a1) / 2
    for a in (sm - 140, sm + 30):
        f.box(a, a + 110, 120, 400, 0, 90, S["front"])
        f.box(a, a + 110, 300, 400, 90, 150, S["front"])
        f.box(a, a + 110, 120, 400, 0, 25, S["black"])


def main():
    with open(DATA) as fh:
        d = json.load(fh)
    fin = d["finishes"]
    mats = [
        rk.material("EN_Carcass", tuple(fin["carcass"]), 0.6),
        rk.material("EN_Front", tuple(fin["front"]), 0.45),
        rk.material("EN_Oak", tuple(fin["oak"]), 0.5),
        rk.material("EN_Cushion", tuple(fin["cushion"]), 0.9),
        rk.material("EN_Black", (0.04, 0.04, 0.04), 0.4),
        rk.material("EN_LED", (1.0, 0.95, 0.85), 0.5, emission=3.0),
        rk.material("EN_Chrome", (0.8, 0.8, 0.82), 0.15, metallic=1.0),
        rk.material("EN_Leather", (0.35, 0.20, 0.12), 0.5),
    ]
    carp = rk.child_collection("Carpentry", "Carpentry.Entrance")
    acc = rk.child_collection("Accessories", "Accessories.Entrance")
    m = rk.Mesh()
    c2(d["c2"], m)
    m.finish("EN_C2 shoe cabinet + seat + key surface", carp, mats)
    m = rk.Mesh()
    accessories(d["c2"], m)
    m.finish("EN_Keys, wallet, shoes", acc, mats)
    rk.register_cameras("foy_", d.get("cameras", {}))
    print(f"Entrance: {len(carp.objects)} carpentry, {len(acc.objects)} accessory objects")


main()
