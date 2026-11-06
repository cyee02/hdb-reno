"""Build the bathroom (WC1 + WC2) renovation from blender/data/bathrooms.json.

Creates these collections (rebuilt each run, nothing else touched):
  Carpentry.Bathrooms   - WC1 shower half wall (tiled cement + frosted glass) with 2 niches
  Appliances.Bathrooms  - rain shower sets, ceiling ventilator + LED lights
  Accessories.Bathrooms - shampoo / body wash bottles in the niches
Toilets and sinks stay in "Fixtures" (build_fixtures.py, HDB-provided positions).
It also registers the bathroom camera views (wc*) in scene["room_cameras"].

Run after build_flat.py:
    Blender -b <file>.blend -P blender/scripts/build_bathrooms.py
or send via the Blender MCP `execute_blender_code` tool.
"""
import importlib
import json
import os
import sys

HDB_RENO_ROOT = os.path.expanduser("~/workspace/hdb-reno")
try:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if not os.path.exists(os.path.join(ROOT, "blender", "data", "bathrooms.json")):
        ROOT = HDB_RENO_ROOT
except NameError:
    ROOT = HDB_RENO_ROOT

DATA = os.path.join(ROOT, "blender", "data", "bathrooms.json")
sys.path.insert(0, os.path.join(ROOT, "blender", "scripts"))
import door_motion  # noqa: E402
import room_kit as rk  # noqa: E402
importlib.reload(door_motion)
importlib.reload(rk)

SLOTS = ["tile", "frosted", "black", "fan", "led", "grille", "bottle_a", "bottle_b"]
S = {name: i for i, name in enumerate(SLOTS)}
CEILING = 2600


def materials(fin):
    return [
        rk.material("WC_Tile", tuple(fin["tile"]), 0.35),
        rk.material("WC_FrostedGlass", tuple(fin["frosted"]), 0.45, alpha=0.55),
        rk.material("WC_Black", tuple(fin["black"]), 0.4),
        rk.material("WC_FanBody", tuple(fin["fan_body"]), 0.4),
        rk.material("WC_FanLED", (1.0, 0.93, 0.80), 0.5, emission=6.0),
        rk.material("WC_FanGrille", (0.75, 0.75, 0.74), 0.5),
        rk.material("WC_BottleA", (0.20, 0.45, 0.55), 0.25),
        rk.material("WC_BottleB", (0.92, 0.90, 0.85), 0.25),
    ]


def wall_frame(m, face, facing):
    """Frame on a wall face: `a` along the wall, `d` out from the face into the room."""
    rect = {"north": [0, face, 1, face + 1], "south": [0, face - 1, 1, face],
            "west": [face, 0, face + 1, 1], "east": [face - 1, 0, face, 1]}[facing]
    return rk.Frame(m, rect, facing)


def half_wall(h, m):
    """Tiled cement wall with recessed niches on its east face, frosted glass on top."""
    x0, y0, x1, y1 = h["rect"]
    H = h["height"]
    n = h["niches"]
    nd, (nz0, nz1) = n["depth"], n["z"]
    xb = x1 - nd                                                   # niche back face
    m.box(x0, y0, xb, y1, 0, H, S["tile"])                         # back slab (full)
    m.box(xb, y0, x1, y1, 0, nz0, S["tile"])                       # front slab below niches
    m.box(xb, y0, x1, y1, nz1, H, S["tile"])                       # ... and above
    edges = [y0] + [v for pair in n["y"] for v in pair] + [y1]
    for s, e in zip(edges[0::2], edges[1::2]):                     # piers between niches
        m.box(xb, s, x1, e, nz0, nz1, S["tile"])
    xc = (x0 + x1) / 2
    m.box(xc - 12, y0, xc + 12, y1, H, H + 25, S["black"])         # glass channel
    m.box(xc - 5, y0 + 10, xc + 5, y1, H + 25, h["glass_top"], S["frosted"])
    m.box(xc - 8, y0, xc + 8, y0 + 10, H + 25, h["glass_top"], S["black"])  # free-edge profile


def shower(s, m):
    f = wall_frame(m, s["wall_face"], s["facing"])
    a = s["at"]
    f.box(a - 70, a + 70, 0, 12, 950, 1100, S["black"])            # mixer plate
    f.box(a - 100, a + 100, 12, 70, 1000, 1050, S["black"])        # thermostatic mixer
    f.box(a - 12, a + 12, 35, 60, 1050, 2080, S["black"])          # riser rail
    f.box(a - 12, a + 12, 35, 330, 2080, 2100, S["black"])         # top arm
    f.cyl(a, 300, 125, 2060, 2080, S["black"], 32)                 # rain head
    f.box(a + 30, a + 60, 60, 90, 1250, 1500, S["black"])          # hand shower


def fan_light(at, spec, m):
    cx, cy = at
    r, h = spec["diameter"] / 2, spec["height"]
    m.cyl(cx, cy, r * 0.75, CEILING - 50, CEILING, S["grille"], 32)       # vent grille ring
    m.cyl(cx, cy, r, CEILING - h, CEILING - 50, S["fan"], 48)            # body
    m.cyl(cx, cy, r * 0.88, CEILING - h - 4, CEILING - h, S["led"], 48)  # LED diffuser


def bottles(h, m):
    x1 = h["rect"][2]
    n = h["niches"]
    z0 = n["z"][0]
    for k, (s, e) in enumerate(n["y"]):
        for j in range(3):
            y = s + 60 + j * (e - s - 120) / 2
            slot = S["bottle_a"] if (j + k) % 2 else S["bottle_b"]
            m.cyl(x1 - 45, y, 32, z0, z0 + 180 + 30 * (j % 2), slot, 16)
            m.cyl(x1 - 45, y, 12, z0 + 180 + 30 * (j % 2), z0 + 215 + 30 * (j % 2), S["black"], 12)


def main():
    with open(DATA) as fh:
        d = json.load(fh)
    mats = materials(d["finishes"])
    carp = rk.child_collection("Carpentry", "Carpentry.Bathrooms")
    appl = rk.child_collection("Appliances", "Appliances.Bathrooms")
    acc = rk.child_collection("Accessories", "Accessories.Bathrooms")

    m = rk.Mesh(); half_wall(d["half_wall"], m); m.finish("WC_WC1 shower half wall + frosted glass", carp, mats)
    for s in d["showers"]:
        m = rk.Mesh(); shower(s, m); m.finish(f"WC_{s['room']} rain shower", appl, mats)
    for fl in d["fan_lights"]:
        m = rk.Mesh(); fan_light(fl["at"], d["fan_light"], m)
        m.finish(f"WC_{fl['room']} ceiling ventilator + light", appl, mats)
    m = rk.Mesh(); bottles(d["half_wall"], m); m.finish("WC_Shampoo + body wash", acc, mats)

    rk.register_cameras("wc", d.get("cameras", {}))
    print(f"Bathrooms: {len(carp.objects)} carpentry, {len(appl.objects)} appliance, {len(acc.objects)} accessory objects")


main()
