"""HDB Reno view tools for the 3D viewport (also in the N panel > HDB Reno tab).

- Alt+W        toggle the walls on/off. Hides the `Flat.Walls` collection plus window
               frames/glass (they'd float without walls). Doors stay visible.
- Shift+Alt+P  jump to the plan view: straight down from above (orthographic), north up,
               framed on the whole flat - like the HDB floor plan.
- Shift+Alt+O  open / close all doors smoothly (swing doors, WC bi-folds, yard door, kitchen glass).
Viewport only - renders are not affected (except the doors, which render where you leave them).

Doors section of the panel: a 0-1 slider per door (drag it), close (<) / open (>) buttons
(two-way doors like the wardrobe bi-folds: -1..1 slider, < to one end, [] closed, > to the other), and
"Make Animation" which keyframes open -> hold -> close on the timeline (press Space to play,
or render it as a video). "Clear Animation" removes those keyframes so the buttons work again.
Movable doors come from the build scripts (blender/scripts/door_motion.py): each door's
position is driven by scene["door_<id>"]; the list of doors is scene["hdb_doors"].

Install: Edit > Preferences > Add-ons > Install from Disk... > this file, then enable it.
"""
import json
import time

import bpy
from mathutils import Quaternion, Vector

bl_info = {
    "name": "HDB Reno View Tools",
    "author": "hdb-reno",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Alt+W / Shift+Alt+P / Shift+Alt+O, N panel > HDB Reno",
    "description": "Toggle the flat's walls; jump to the plan view; open and close doors",
    "category": "3D View",
}

WALLS = "Flat.Walls"
OPENINGS = "Flat.Openings"
WINDOW_PREFIXES = ("Window_", "Glass_")
FLAT = "Flat"
PLAN_MARGIN = 1.08   # a little breathing room around the flat


def find_layer_collection(layer_coll, name):
    if layer_coll.name == name:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, name)
        if found:
            return found
    return None


def walls_hidden(context):
    lc = find_layer_collection(context.view_layer.layer_collection, WALLS)
    return bool(lc and lc.hide_viewport)


class HDB_OT_toggle_walls(bpy.types.Operator):
    bl_idname = "hdb.toggle_walls"
    bl_label = "Toggle Walls"
    bl_description = "Show/hide the flat's walls and windows in the viewport"

    def execute(self, context):
        lc = find_layer_collection(context.view_layer.layer_collection, WALLS)
        if not lc:
            self.report({"WARNING"}, f"Collection '{WALLS}' not found")
            return {"CANCELLED"}
        hide = not lc.hide_viewport
        lc.hide_viewport = hide  # the eye icon in the Outliner
        openings = bpy.data.collections.get(OPENINGS)
        if openings:
            for obj in openings.objects:
                if obj.name.startswith(WINDOW_PREFIXES):
                    obj.hide_set(hide, view_layer=context.view_layer)
        self.report({"INFO"}, "Walls hidden" if hide else "Walls shown")
        return {"FINISHED"}


def flat_bounds():
    """World-space XY bounds of everything in the Flat collection (metres)."""
    coll = bpy.data.collections.get(FLAT)
    if not coll:
        return None
    xs, ys = [], []
    for obj in coll.all_objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            xs.append(w.x)
            ys.append(w.y)
    if not xs:
        return None
    return min(xs), max(xs), min(ys), max(ys)


class HDB_OT_plan_view(bpy.types.Operator):
    bl_idname = "hdb.plan_view"
    bl_label = "Plan View"
    bl_description = "Look straight down on the whole flat (orthographic, north up)"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        b = flat_bounds()
        if not b:
            self.report({"WARNING"}, f"Collection '{FLAT}' not found")
            return {"CANCELLED"}
        x0, x1, y0, y1 = b
        space = context.space_data
        r3d = space.region_3d
        region = next((r for r in context.area.regions if r.type == "WINDOW"), None)
        r3d.view_perspective = "ORTHO"
        r3d.view_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))     # top view, north (+Y) up
        r3d.view_location = Vector(((x0 + x1) / 2, (y0 + y1) / 2, 0.0))
        # Ortho view width = view_distance * 72 / lens (Blender's viewport sensor). Fit both axes.
        w, h = (x1 - x0) * PLAN_MARGIN, (y1 - y0) * PLAN_MARGIN
        aspect = region.width / max(region.height, 1) if region else 1.6
        width_needed = max(w, h * aspect)
        r3d.view_distance = width_needed * space.lens / 72.0
        return {"FINISHED"}


# ---------- doors ----------

DOOR_SECONDS = 1.2          # how long Open / Close takes in the viewport
ANIM_FRAMES = (1, 48, 96, 144)   # closed -> open -> hold open -> closed


def door_groups(scene):
    """{group id: label} for the movable doors the build scripts registered."""
    try:
        return json.loads(scene.get("hdb_doors", "{}"))
    except ValueError:
        return {}


def door_meta(scene):
    """{group id: {"min": 0 or -1, "open_to": value used by Open All / Make Animation}}."""
    try:
        return json.loads(scene.get("hdb_door_meta", "{}"))
    except ValueError:
        return {}


def open_value(scene, gid):
    return float(door_meta(scene).get(gid, {}).get("open_to", 1.0))


def door_key(gid):
    return f"door_{gid}"


def door_fcurves(scene):
    """(channelbag, fcurve) pairs for keyframed door values on the scene."""
    ad = scene.animation_data
    if not ad or not ad.action or not ad.action_slot:
        return []
    out = []
    for layer in ad.action.layers:
        for strip in layer.strips:
            bag = strip.channelbag(ad.action_slot)
            if bag:
                out += [(bag, fc) for fc in bag.fcurves if fc.data_path.startswith('["door_')]
    return out


_moves = {}  # gid -> (from value, to value, start time)


def _refresh(scene):
    scene.update_tag()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _tick():
    scene = bpy.context.scene
    now = time.monotonic()
    for gid, (a, b, t0) in list(_moves.items()):
        u = min(1.0, (now - t0) / DOOR_SECONDS)
        ease = u * u * (3 - 2 * u)
        if door_key(gid) in scene:
            scene[door_key(gid)] = a + (b - a) * ease
        if u >= 1.0:
            del _moves[gid]
    _refresh(scene)
    return 0.02 if _moves else None


def move_doors(scene, gids, target):
    for gid in gids:
        if door_key(gid) in scene:
            _moves[gid] = (float(scene[door_key(gid)]), target, time.monotonic())
    if _moves and not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick)


class HDB_OT_door_move(bpy.types.Operator):
    bl_idname = "hdb.door_move"
    bl_label = "Move Door"
    bl_description = "Slide the door open or closed"

    gid: bpy.props.StringProperty(description="Door id (empty = all doors)")
    target: bpy.props.FloatProperty(min=-1.0, max=1.0)

    def execute(self, context):
        scene = context.scene
        if door_fcurves(scene):
            self.report({"WARNING"}, "Doors are keyframed on the timeline - click Clear Animation first")
            return {"CANCELLED"}
        gids = [self.gid] if self.gid else list(door_groups(scene))
        move_doors(scene, gids, self.target)
        return {"FINISHED"}


class HDB_OT_doors_toggle(bpy.types.Operator):
    bl_idname = "hdb.doors_toggle"
    bl_label = "Open / Close All Doors"
    bl_description = "Open all movable doors, or close them if they're already open"

    def execute(self, context):
        scene = context.scene
        gids = list(door_groups(scene))
        if not gids:
            self.report({"WARNING"}, "No movable doors - rebuild with the build scripts")
            return {"CANCELLED"}
        if door_fcurves(scene):
            self.report({"WARNING"}, "Doors are keyframed on the timeline - click Clear Animation first")
            return {"CANCELLED"}
        opening = any(abs(float(scene.get(door_key(g), 0))) < 0.5 for g in gids)
        if opening:
            for g in gids:
                move_doors(scene, [g], open_value(scene, g))
        else:
            move_doors(scene, gids, 0.0)
        self.report({"INFO"}, "Opening doors" if opening else "Closing doors")
        return {"FINISHED"}


class HDB_OT_doors_keyframe(bpy.types.Operator):
    bl_idname = "hdb.doors_keyframe"
    bl_label = "Make Door Animation"
    bl_description = ("Keyframe every movable door: closed -> open -> hold -> closed "
                      f"(frames {ANIM_FRAMES[0]}-{ANIM_FRAMES[-1]}). Press Space to play")

    def execute(self, context):
        scene = context.scene
        gids = list(door_groups(scene))
        if not gids:
            self.report({"WARNING"}, "No movable doors - rebuild with the build scripts")
            return {"CANCELLED"}
        for bag, fc in door_fcurves(scene):
            bag.fcurves.remove(fc)
        for gid in gids:
            v = open_value(scene, gid)
            for frame, value in zip(ANIM_FRAMES, (0.0, v, v, 0.0)):
                scene[door_key(gid)] = value
                scene.keyframe_insert(data_path=f'["{door_key(gid)}"]', frame=frame)
        scene.frame_start, scene.frame_end = ANIM_FRAMES[0], ANIM_FRAMES[-1]
        scene.frame_set(ANIM_FRAMES[0])
        self.report({"INFO"}, "Door animation keyframed - press Space in the viewport to play")
        return {"FINISHED"}


class HDB_OT_doors_clear_anim(bpy.types.Operator):
    bl_idname = "hdb.doors_clear_anim"
    bl_label = "Clear Door Animation"
    bl_description = "Remove the door keyframes (doors stay where they are now)"

    def execute(self, context):
        scene = context.scene
        values = {g: float(scene.get(door_key(g), 0)) for g in door_groups(scene)}
        for bag, fc in door_fcurves(scene):
            bag.fcurves.remove(fc)
        for gid, v in values.items():
            scene[door_key(gid)] = v
        _refresh(scene)
        return {"FINISHED"}


class HDB_PT_view_tools(bpy.types.Panel):
    bl_label = "HDB Reno"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "HDB Reno"

    def draw(self, context):
        hidden = walls_hidden(context)
        self.layout.operator(HDB_OT_toggle_walls.bl_idname,
                             text="Show Walls" if hidden else "Hide Walls",
                             icon="HIDE_ON" if hidden else "HIDE_OFF")
        self.layout.label(text="Hotkey: Alt+W")
        self.layout.operator(HDB_OT_plan_view.bl_idname, text="Plan View", icon="VIEW_ORTHO")
        self.layout.label(text="Hotkey: Shift+Alt+P")

        scene = context.scene
        groups = door_groups(scene)
        box = self.layout.box()
        box.label(text="Doors", icon="MOD_BUILD")
        if not groups:
            box.label(text="No movable doors - rebuild the model")
            return
        animated = bool(door_fcurves(scene))
        meta = door_meta(scene)
        for gid, label in sorted(groups.items(), key=lambda kv: kv[1]):
            if door_key(gid) not in scene:
                continue
            two_way = meta.get(gid, {}).get("min", 0.0) < 0
            box.label(text=label)
            row = box.row(align=True)
            row.prop(scene, f'["{door_key(gid)}"]', text="Position" if two_way else "Open", slider=True)
            sub = row.row(align=True)
            sub.enabled = not animated
            if two_way:   # -1 = folded at one end, 0 = closed, +1 = folded at the other end
                buttons = ((-1.0, "TRIA_LEFT"), (0.0, "SNAP_INCREMENT"), (1.0, "TRIA_RIGHT"))
            else:
                buttons = ((0.0, "TRIA_LEFT"), (1.0, "TRIA_RIGHT"))
            for target, icon in buttons:
                op = sub.operator(HDB_OT_door_move.bl_idname, text="", icon=icon)
                op.gid, op.target = gid, target
        row = box.row()
        row.enabled = not animated
        row.operator(HDB_OT_doors_toggle.bl_idname, text="Open / Close All", icon="ARROW_LEFTRIGHT")
        box.label(text="Hotkey: Shift+Alt+O")
        if animated:
            box.label(text="Keyframed: press Space to play", icon="PLAY")
            box.operator(HDB_OT_doors_clear_anim.bl_idname, text="Clear Animation", icon="X")
        else:
            box.operator(HDB_OT_doors_keyframe.bl_idname, text="Make Animation", icon="KEYFRAME")


addon_keymaps = []


CLASSES = (HDB_OT_toggle_walls, HDB_OT_plan_view, HDB_OT_door_move, HDB_OT_doors_toggle,
           HDB_OT_doors_keyframe, HDB_OT_doors_clear_anim, HDB_PT_view_tools)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(HDB_OT_toggle_walls.bl_idname, "W", "PRESS", alt=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(HDB_OT_plan_view.bl_idname, "P", "PRESS", alt=True, shift=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(HDB_OT_doors_toggle.bl_idname, "O", "PRESS", alt=True, shift=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
