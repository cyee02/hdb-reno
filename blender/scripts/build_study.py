"""Build the suggested study from blender/data/study.json.

Creates these collections (rebuilt each run, nothing else touched):
  Carpentry.Study   - two full-height glass sliding partitions (living side + dining side),
                      floating book shelf
  Furniture.Study   - two 1200 x 600 study tables, two office chairs
  Accessories.Study - monitors, books
The glass partitions are movable: scene["door_study_glass_west"] / ["door_study_glass_south"]
(0 closed - 1 open, all panels stacked at the hatched spots on the owner's sketch).
It also registers the study camera views (study_*) in scene["room_cameras"].

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_study.py
or send via the Blender MCP `execute_blender_code` tool.
"""
import importlib
import json
import math
import os
import sys

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "study.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "study.json")
sys.path.insert(0, os.path.join(ROOT, "blender", "scripts"))
import door_motion  # noqa: E402
import room_kit as rk  # noqa: E402
importlib.reload(door_motion)
importlib.reload(rk)


def desk(d, m, oak, black):
    x0, y0, x1, y1 = d["rect"]
    h = d["height"]
    m.box(x0, y0, x1, y1, h - 25, h, oak)
    for ly in (y0 + 30, y1 - 70):                                  # black sled legs (west + east)
        m.box(x0 + 40, ly, x0 + 80, ly + 40, 0, h - 25, black)
        m.box(x1 - 80, ly, x1 - 40, ly + 40, 0, h - 25, black)
        m.box(x0 + 40, ly, x1 - 40, ly + 40, h - 65, h - 25, black)
    m.box(x1 - 60, y0 + 30, x1 - 40, y1 - 30, h - 65, h - 25, black)


def office_chair(cx, cy, m, seat, black):
    """Swivel chair facing east (towards the desk)."""
    for k in range(5):                                             # star base + castors
        a =2 * math.pi * k / 5
        ex, ey = cx + 300 * math.cos(a), cy + 300 * math.sin(a)
        m.box(min(cx, ex) - 15, min(cy, ey) - 15, max(cx, ex) + 15, max(cy, ey) + 15, 60, 90, black)
        m.cyl(ex, ey, 30, 0, 60, black, 12)
    m.cyl(cx, cy, 30, 90, 440, black, 16)                          # gas lift
    m.box(cx - 240, cy - 250, cx + 240, cy + 250, 440, 500, seat)  # seat
    m.box(cx - 290, cy - 230, cx - 250, cy + 230, 560, 1050, seat)  # backrest (west side)
    m.box(cx - 270, cy - 20, cx - 230, cy + 20, 440, 560, black)
    for sy in (cy - 260, cy + 240):                                # armrests
        m.box(cx - 120, sy, cx + 160, sy + 20, 680, 700, black)
        m.box(cx - 40, sy, cx - 20, sy + 20, 500, 680, black)


def monitor(d, m, black, screen):
    x0, y0, x1, y1 = d["rect"]
    cy, top = (y0 + y1) / 2, d["height"]
    m.box(x1 - 260, cy - 120, x1 - 140, cy + 120, top, top + 15, black)   # foot
    m.box(x1 - 210, cy - 25, x1 - 180, cy + 25, top + 15, top + 320, black)
    m.box(x1 - 240, cy - 305, x1 - 215, cy + 305, top + 150, top + 510, black)  # 27" panel
    m.box(x1 - 242, cy - 298, x1 - 240, cy + 298, top + 157, top + 503, screen)


def main():
    with open(DATA) as fh:
        d = json.load(fh)
    fin = d["finishes"]
    frame = rk.material("ST_Frame", tuple(fin["frame"]), 0.4)
    glass = rk.glass_material()
    oak = rk.material("ST_Oak", tuple(fin["oak"]), 0.5)
    black = rk.material("ST_Black", (0.04, 0.04, 0.04), 0.4)
    seat = rk.material("ST_ChairMesh", tuple(fin["chair"]), 0.8)
    screen = rk.material("ST_Screen", (0.05, 0.08, 0.12), 0.1)
    books = [rk.material(f"ST_Book{k}", tuple(c), 0.7) for k, c in enumerate(fin["books"])]
    ceiling = 2600

    carp = rk.child_collection("Carpentry", "Carpentry.Study")
    furn = rk.child_collection("Furniture", "Furniture.Study")
    acc = rk.child_collection("Accessories", "Accessories.Study")

    for p in d["partitions"]:
        rk.glass_partition(p, ceiling, carp, frame, glass, "ST")

    sh = d["shelf"]
    x0, y0, x1, y1 = sh["rect"]
    m = rk.Mesh()
    m.box(x0, y0, x1, y1, sh["z"] - 25, sh["z"], 0)
    m.finish("ST_Book shelf (floating)", carp, [oak])

    for k, dk in enumerate(d["desks"]):
        m = rk.Mesh()
        desk(dk, m, 0, 1)
        m.finish(f"ST_Study table {k + 1} (1200 x 600)", furn, [oak, black])
        m = rk.Mesh()
        monitor(dk, m, 0, 1)
        m.finish(f"ST_Monitor {k + 1}", acc, [black, screen])
    for k, (cx, cy) in enumerate(d["chairs"]):
        m = rk.Mesh()
        office_chair(cx, cy, m, 0, 1)
        m.finish(f"ST_Office chair {k + 1}", furn, [seat, black])

    m = rk.Mesh()                                                  # books on the shelf
    y, k = y0 + 60, 0
    while y < y1 - 400:
        for j in range(8):
            h = 220 + (j * 37 % 60)
            m.box(x1 - 230, y, x1 - 30, y + 28, sh["z"], sh["z"] + h, (k + j) % len(books))
            y += 32
        y += 350
        k += 1
    m.finish("ST_Books", acc, books)

    rk.register_cameras("study_", d.get("cameras", {}))
    print(f"Study: {len(carp.objects)} carpentry, {len(furn.objects)} furniture, {len(acc.objects)} accessory objects")


main()
