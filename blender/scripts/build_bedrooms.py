"""Build Bedroom 2 and Bedroom 3 from blender/data/bedrooms.json.

Creates, per room (rebuilt each run, nothing else touched):
  Carpentry.<Room>  - 1-person wardrobe to the ceiling, sliding doors
  Furniture.<Room>  - bed (queen / single), bedside table, optional table + stool
It also registers the bedroom camera views (bed2_*, bed3_*) in scene["room_cameras"].

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_bedrooms.py
or send via the Blender MCP `execute_blender_code` tool.
"""
import importlib
import json
import os
import sys

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "bedrooms.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "bedrooms.json")
sys.path.insert(0, os.path.join(ROOT, "blender", "scripts"))
import door_motion  # noqa: E402
import room_kit as rk  # noqa: E402
importlib.reload(door_motion)
importlib.reload(rk)

SLOTS = ["oak", "white", "black", "mattress", "duvet", "frame"]
S = {name: i for i, name in enumerate(SLOTS)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}


def bed(b, m):
    """Upholstered bed; built in a frame whose front is the foot end."""
    f = rk.Frame(m, b["rect"], OPPOSITE[b["head"]])
    a0, a1, D = f.a0, f.a1, f.depth
    hb = 80
    for a in (a0 + 40, a1 - 80):                                   # legs
        for dd in (-60, -D + hb + 20):
            f.box(a, a + 40, dd - 40, dd, 0, 80, S["black"])
    f.box(a0, a1, -D + hb, 0, 80, 330, S["frame"])                 # base
    f.box(a0 + 20, a1 - 20, -D + hb + 10, -20, 330, 560, S["mattress"])
    f.box(a0 + 10, a1 - 10, -D + hb + 520, -10, 520, 590, S["duvet"])  # duvet, folded back at the head
    f.box(a0, a1, -D, -D + hb, 0, 1100, S["frame"])                # headboard
    n = b["pillows"]
    w = (a1 - a0 - 80) / n
    for k in range(n):
        s = a0 + 40 + k * w
        f.box(s + 10, s + w - 10, -D + hb + 60, -D + hb + 460, 560, 680, S["mattress"])


def wardrobe(w, m, door_slot):
    """Full-height wardrobe with two sliding doors on a double track."""
    f = rk.Frame(m, w["rect"], w["front"])
    a0, a1, D = f.a0, f.a1, f.depth
    f.box(a0, a1, -D, -50, 0, 2600, S["white"])                    # carcass
    f.box(a0, a1, -50, 0, 0, 70, S["white"])                       # plinth
    f.box(a0, a1, -50, 0, 2540, 2600, S["white"])                  # track pelmet
    mid = (a0 + a1) / 2
    f.box(a0 + 2, mid + 25, -48, -28, 72, 2538, door_slot)         # back door
    f.box(mid - 25, a1 - 2, -26, -6, 72, 2538, door_slot)          # front door
    f.box(a0 + 30, a0 + 45, -28, -20, 900, 1400, S["black"])       # pull strips
    f.box(a1 - 45, a1 - 30, -6, 2, 900, 1400, S["black"])


def table(t, m):
    x0, y0, x1, y1 = t["rect"]
    h = t["height"]
    m.box(x0, y0, x1, y1, h - 25, h, S["oak"])
    for lx, ly in ((x0 + 20, y0 + 20), (x1 - 55, y0 + 20), (x0 + 20, y1 - 55), (x1 - 55, y1 - 55)):
        m.box(lx, ly, lx + 35, ly + 35, 0, h - 25, S["black"])
    m.box(x0 + 40, y0 + 20, x1 - 40, y0 + 120, h - 120, h - 25, S["white"])  # slim drawer


def stool(at, m):
    cx, cy = at
    m.cyl(cx, cy, 170, 420, 450, S["oak"], 32)
    for dx, dy in ((-100, -100), (100, -100), (-100, 100), (100, 100)):
        m.cyl(cx + dx, cy + dy, 15, 0, 420, S["black"], 10)
    m.box(cx - 110, cy - 8, cx + 110, cy + 8, 180, 196, S["black"])
    m.box(cx - 8, cy - 110, cx + 8, cy + 110, 180, 196, S["black"])


def bedside(r, m):
    x0, y0, x1, y1 = r["rect"]
    m.box(x0, y0, x1, y1, 80, 520, S["white"])
    m.box(x0, y0, x1, y1, 520, 540, S["oak"])
    for lx, ly in ((x0 + 20, y0 + 20), (x1 - 45, y0 + 20), (x0 + 20, y1 - 45), (x1 - 45, y1 - 45)):
        m.box(lx, ly, lx + 25, ly + 25, 0, 80, S["black"])


def main():
    with open(DATA) as fh:
        d = json.load(fh)
    fin = d["finishes"]
    for room in d["rooms"]:
        rid = room["id"]
        b = room["bed"]
        mats = [
            rk.material("BR_Oak", tuple(fin["oak"]), 0.5),
            rk.material("BR_White", tuple(fin["white"]), 0.45),
            rk.material("BR_Black", tuple(fin["black"]), 0.4),
            rk.material("BR_Mattress", tuple(fin["mattress"]), 0.9),
            rk.material(f"BR_Duvet_{rid}", tuple(b["duvet"]), 0.9),
            rk.material(f"BR_BedFrame_{rid}", tuple(b["frame"]), 0.9),
        ]
        carp = rk.child_collection("Carpentry", f"Carpentry.{rid}")
        furn = rk.child_collection("Furniture", f"Furniture.{rid}")
        kind = "queen" if b["pillows"] > 1 else "single"
        m = rk.Mesh(); bed(b, m); m.finish(f"BR_{rid} {kind} bed", furn, mats)
        m = rk.Mesh(); bedside(room["bedside"], m); m.finish(f"BR_{rid} bedside table", furn, mats)
        if "table" in room:
            t = room["table"]
            m = rk.Mesh(); table(t, m); m.finish(f"BR_{rid} table {t['rect'][2] - t['rect'][0]:.0f}", furn, mats)
        if "stool" in room:
            m = rk.Mesh(); stool(room["stool"]["at"], m); m.finish(f"BR_{rid} stool", furn, mats)
        w = room["wardrobe"]
        m = rk.Mesh(); wardrobe(w, m, S["oak"] if w["doors"] == "oak" else S["white"])
        m.finish(f"BR_{rid} wardrobe (1 person)", carp, mats)
        print(f"{rid}: {len(carp.objects)} carpentry, {len(furn.objects)} furniture objects")
    rk.register_cameras("bed", d.get("cameras", {}))


main()
