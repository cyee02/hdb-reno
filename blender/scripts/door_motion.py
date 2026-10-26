"""Movable doors: one 0-1 "open" value per door group, stored on the scene.

Build scripts call `register_group` once per door, then `drive` on each moving piece
(built in its CLOSED position). A driver moves the piece by `delta` x open, so changing
scene["door_<group>"] (slider, button, or keyframes) opens and closes the door.

The view-tools add-on (blender/tools/hdb_view_tools.py) lists the groups in
scene["hdb_doors"] and shows a slider + Open/Close buttons for each.
"""
import json

import bpy


def prop_name(gid):
    return f"door_{gid}"


def register_group(gid, label, value, two_way=False, open_to=1.0):
    """Add a door control. One-way doors run 0 (closed) - 1 (open). Two-way doors (e.g. a
    sliding bi-fold that can park at either end) run -1 - 0 (closed) - 1; `open_to` is where
    "Open all" / "Make Animation" send it."""
    scene = bpy.context.scene
    key = prop_name(gid)
    lo = -1.0 if two_way else 0.0
    scene[key] = float(value)
    desc = (f"{label}: -1 / +1 = folded at either end, 0 = closed" if two_way
            else f"{label}: 0 = closed, 1 = fully open")
    scene.id_properties_ui(key).update(min=lo, max=1.0, soft_min=lo, soft_max=1.0, description=desc)
    groups = json.loads(scene.get("hdb_doors", "{}"))
    groups[gid] = label
    scene["hdb_doors"] = json.dumps(groups)
    meta = json.loads(scene.get("hdb_door_meta", "{}"))
    meta[gid] = {"min": lo, "open_to": open_to}
    scene["hdb_door_meta"] = json.dumps(meta)


def forget_groups(prefix):
    """Drop door controls whose id starts with `prefix` (before a room script rebuilds them)."""
    scene = bpy.context.scene
    for store in ("hdb_doors", "hdb_door_meta"):
        d = json.loads(scene.get(store, "{}"))
        scene[store] = json.dumps({k: v for k, v in d.items() if not k.startswith(prefix)})
    for key in [k for k in scene.keys() if k.startswith(prop_name(prefix))]:
        del scene[key]


def drive_channel(obj, gid, path, index, expression):
    """Drive obj.<path>[index] with `expression` of `o` (the group's 0-1 open value).

    Keep it a simple expression (arithmetic, sin/cos...): Blender evaluates those natively,
    so no "Auto Run Python Scripts" permission is needed.
    """
    obj["door_group"] = gid
    drv = obj.driver_add(path, index).driver
    drv.type = "SCRIPTED"
    var = drv.variables.new()
    var.name = "o"
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "SCENE"
    var.targets[0].id = bpy.context.scene
    var.targets[0].data_path = f'["{prop_name(gid)}"]'
    drv.expression = expression


def drive(obj, gid, delta):
    """Slide `obj` by `delta` (Blender metres, x/y/z) when the group is fully open."""
    obj["door_group"] = gid
    for axis, d in enumerate(delta):
        if abs(d) > 1e-9:
            drive_channel(obj, gid, "location", axis, f"o * {d:.5f}")


def drive_rotation(obj, gid, angle):
    """Turn `obj` about its origin (the hinge) by `angle` radians around Z when fully open."""
    drive_channel(obj, gid, "rotation_euler", 2, f"o * {angle:.5f}")
