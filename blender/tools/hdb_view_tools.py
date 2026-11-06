"""HDB Reno view tools for the 3D viewport (also in the N panel > HDB Reno tab).

- Alt+W        toggle the walls on/off. Hides the `Flat.Walls` collection plus window
               frames/glass (they'd float without walls). Doors stay visible.
- Shift+Alt+P  jump to the plan view: straight down from above (orthographic), north up,
               framed on the whole flat - like the HDB floor plan.
- Shift+Alt+O  open / close all doors smoothly (swing doors, WC bi-folds, yard door, kitchen glass).
- Shift+Alt+F  first-person walk: eye at 1.6 m, you can't walk through or climb onto walls,
               furniture, glass or closed doors. WASD / arrows move (Shift = faster), mouse looks,
               E or click = open/close the door you look at, H (or Alt+W) = hide/show walls,
               scroll / trackpad / + - = zoom (Z resets), Esc / Enter / right-click = stop.
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
import math
import time

import bpy
import numpy as np
from mathutils import Euler, Quaternion, Vector
from mathutils.bvhtree import BVHTree

bl_info = {
    "name": "HDB Reno View Tools",
    "author": "hdb-reno",
    "version": (1, 3, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Alt+W / Shift+Alt+P / Shift+Alt+O / Shift+Alt+F, N panel > HDB Reno",
    "description": "Toggle the flat's walls; plan view; open and close doors; first-person walk",
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
        hide = toggle_walls(context)
        if hide is None:
            self.report({"WARNING"}, f"Collection '{WALLS}' not found")
            return {"CANCELLED"}
        self.report({"INFO"}, "Walls hidden" if hide else "Walls shown")
        return {"FINISHED"}


def toggle_walls(context):
    """Hide/show the walls + window frames. Returns True if now hidden, None if no walls."""
    lc = find_layer_collection(context.view_layer.layer_collection, WALLS)
    if not lc:
        return None
    hide = not lc.hide_viewport
    lc.hide_viewport = hide  # the eye icon in the Outliner
    openings = bpy.data.collections.get(OPENINGS)
    if openings:
        for obj in openings.objects:
            if obj.name.startswith(WINDOW_PREFIXES):
                obj.hide_set(hide, view_layer=context.view_layer)
    return hide


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


# ---------- first-person walk ----------

EYE_HEIGHT = 1.6                     # m above the floor; you stay on the floor (no climbing)
BODY_RADIUS = 0.2                    # m kept clear of walls / furniture / glass
PROBE_HEIGHTS = (0.2, 0.6, 1.1, 1.7) # knee .. head: anything taller than ~0.15 m blocks you
WALK_SPEED, RUN_SPEED = 1.4, 3.0     # m/s (Shift = run)
STEP = 0.05                          # m per collision check, so fast moves can't tunnel
LOOK_SPEED = 0.0025                  # radians per pixel
LENS_DEFAULT, LENS_MIN, LENS_MAX = 24.0, 10.0, 120.0
REACH = 2.5                          # m: how far away a door can be opened
START = (2.9, -6.9)                  # foyer, just inside the main door (Blender X, Y)
SKIP_COLLECTIONS = {"Cameras", "Flat.Labels", "Flat.Floors"}
MOVE_KEYS = {"W": (1, 0), "UP_ARROW": (1, 0), "S": (-1, 0), "DOWN_ARROW": (-1, 0),
             "A": (0, -1), "LEFT_ARROW": (0, -1), "D": (0, 1), "RIGHT_ARROW": (0, 1)}


def _blocks(obj):
    """Meshes you can bump into: skip floors / rugs (< 0.1 m) and ceiling fittings (> 2.2 m)."""
    if obj.type != "MESH" or not obj.data.polygons:
        return False
    if any(c.name in SKIP_COLLECTIONS for c in obj.users_collection):
        return False
    zs = [(obj.matrix_world @ Vector(c)).z for c in obj.bound_box]
    return max(zs) > 0.1 and min(zs) < 2.2


def _tree(objs, depsgraph=None):
    """BVH of the objects' triangles in world space + the owning object per triangle."""
    verts, tris, owner, base = [], [], [], 0
    for obj in objs:
        me = obj.data
        mw = obj.evaluated_get(depsgraph).matrix_world if depsgraph else obj.matrix_world
        co = np.empty(len(me.vertices) * 3, np.float64)
        me.vertices.foreach_get("co", co)
        m = np.array(mw)
        co = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
        if hasattr(me, "calc_loop_triangles"):
            me.calc_loop_triangles()
        t = np.empty(len(me.loop_triangles) * 3, np.int64)
        me.loop_triangles.foreach_get("vertices", t)
        verts.append(co)
        tris.append(t.reshape(-1, 3) + base)
        owner += [obj] * (len(t) // 3)
        base += len(co)
    if not owner:
        return None, []
    return BVHTree.FromPolygons(np.vstack(verts).tolist(), np.vstack(tris).tolist()), owner


class HDB_OT_walk(bpy.types.Operator):
    bl_idname = "hdb.walk"
    bl_label = "First-Person Walk"
    bl_description = ("Walk through the flat at eye height without passing through walls, furniture "
                      "or closed doors. WASD move, mouse look, E / click door, H walls, scroll zoom, Esc stop")

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    # --- collision ---
    def _build_static(self, context):
        objs = [o for o in context.scene.objects if _blocks(o) and "door_group" not in o]
        self.static, _ = _tree(objs)
        self.door_objs = [o for o in context.scene.objects if "door_group" in o and _blocks(o)]
        self.door_sig = None
        self._update_doors(context)

    def _update_doors(self, context):
        scene = context.scene
        sig = tuple(round(float(scene.get(door_key(g), 0)), 4) for g in door_groups(scene))
        if sig != self.door_sig:
            self.door_sig = sig
            self.doors, self.door_owner = _tree(self.door_objs, context.evaluated_depsgraph_get())

    def _blocked(self, x, y):
        for z in PROBE_HEIGHTS:
            p = Vector((x, y, z))
            for tree in (self.static, self.doors):
                if tree and tree.find_nearest(p, BODY_RADIUS)[0] is not None:
                    return True
        return False

    def _clearance(self, x, y):
        """Distance to the nearest thing you could bump into (capped at 1 m)."""
        best = 1.0
        for z in PROBE_HEIGHTS:
            p = Vector((x, y, z))
            for tree in (self.static, self.doors):
                if tree:
                    d = tree.find_nearest(p, best)[3]
                    if d is not None:
                        best = min(best, d)
        return best

    def _move(self, dx, dy):
        dist = math.hypot(dx, dy)
        n = max(1, math.ceil(dist / STEP))
        for _ in range(n):
            x, y, sx, sy = self.eye.x, self.eye.y, dx / n, dy / n
            if self._blocked(x, y):
                # Started too close to something (or a door swung into you): only allow
                # moves that get you more room, so you step out instead of through it.
                here = self._clearance(x, y)
                for mx, my in ((sx, sy), (sx, 0.0), (0.0, sy)):
                    if self._clearance(x + mx, y + my) > here:
                        self.eye.x, self.eye.y = x + mx, y + my
                        break
                continue
            for mx, my in ((sx, sy), (sx, 0.0), (0.0, sy)):   # slide along walls
                if not self._blocked(x + mx, y + my):
                    self.eye.x, self.eye.y = x + mx, y + my
                    break

    # --- view ---
    def _rotation(self):
        return Euler((math.pi / 2 + self.pitch, 0.0, self.yaw)).to_quaternion()

    def _apply_view(self, context):
        r3d = context.space_data.region_3d
        q = self._rotation()
        r3d.view_perspective = "PERSP"
        r3d.view_rotation = q
        r3d.view_distance = 0.01
        r3d.view_location = self.eye + q @ Vector((0.0, 0.0, -0.01))
        context.area.tag_redraw()

    def _header(self, context):
        walls = "shown" if not walls_hidden(context) else "hidden"
        msg = (f"Walk  |  WASD/arrows move (Shift run)  |  mouse look  |  E / click: door  |  "
               f"H: walls ({walls})  |  scroll/+/-: zoom {context.space_data.lens:.0f} mm (Z reset)  |  Esc: stop")
        if self.note:
            msg += f"  |  {self.note}"
        context.area.header_text_set(msg)

    # --- doors ---
    def _door_ahead(self):
        origin = self.eye.copy()
        fwd = self._rotation() @ Vector((0.0, 0.0, -1.0))
        wall = REACH
        if self.static:
            loc, _n, _i, d = self.static.ray_cast(origin, fwd, REACH)
            if loc is not None:
                wall = d
        if self.doors:
            loc, _n, i, d = self.doors.ray_cast(origin, fwd, REACH)
            if loc is not None and d <= wall + 0.05:
                return self.door_owner[i].get("door_group")
            # Not aimed exactly: nearest door within reach of a point just ahead at hand height.
            hand = Vector((origin.x + fwd.x * 0.6, origin.y + fwd.y * 0.6, 1.0))
            loc, _n, i, d = self.doors.find_nearest(hand, 0.9)
            if loc is not None:
                return self.door_owner[i].get("door_group")
        return None

    def _toggle_door(self, context):
        scene = context.scene
        if door_fcurves(scene):
            self.note = "doors are keyframed - Clear Animation first"
            return
        gid = self._door_ahead()
        if not gid or door_key(gid) not in scene:
            self.note = "no door in reach - look at one"
            return
        opened = abs(float(scene[door_key(gid)])) > 0.5
        move_doors(scene, [gid], 0.0 if opened else open_value(scene, gid))
        self.note = f"{'closing' if opened else 'opening'}: {door_groups(scene).get(gid, gid)}"

    # --- modal ---
    def invoke(self, context, event):
        space = context.space_data
        r3d = space.region_3d
        self.region = next(r for r in context.area.regions if r.type == "WINDOW")
        if r3d.view_perspective == "CAMERA":
            r3d.view_perspective = "PERSP"
        q = r3d.view_rotation
        eye = r3d.view_location + q @ Vector((0.0, 0.0, r3d.view_distance))
        fwd = q @ Vector((0.0, 0.0, -1.0))
        b = flat_bounds()
        inside = (b and r3d.view_perspective == "PERSP" and b[0] < eye.x < b[1]
                  and b[2] < eye.y < b[3] and eye.z < 3.0)
        if inside:
            self.eye = Vector((eye.x, eye.y, EYE_HEIGHT))
            self.yaw = math.atan2(-fwd.x, fwd.y)
            self.pitch = max(-0.6, min(0.6, math.asin(max(-1.0, min(1.0, fwd.z)))))
        else:
            self.eye = Vector((START[0], START[1], EYE_HEIGHT))
            self.yaw, self.pitch = 0.0, 0.0           # facing north, into the flat
        self.saved = (space.lens, space.clip_start)
        space.lens, space.clip_start = LENS_DEFAULT, 0.02
        self._build_static(context)
        self.keys, self.note = set(), ""
        self.last = time.monotonic()
        self.timer = context.window_manager.event_timer_add(1 / 60, window=context.window)
        context.window.cursor_modal_set("NONE")
        self._center(context)
        self._apply_view(context)
        self._header(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _center(self, context):
        self.cx = self.region.x + self.region.width // 2
        self.cy = self.region.y + self.region.height // 2
        context.window.cursor_warp(self.cx, self.cy)

    def _zoom(self, context, factor):
        space = context.space_data
        space.lens = max(LENS_MIN, min(LENS_MAX, space.lens * factor))

    def _finish(self, context):
        context.window_manager.event_timer_remove(self.timer)
        context.window.cursor_modal_restore()
        context.area.header_text_set(None)
        space = context.space_data
        space.lens, space.clip_start = self.saved
        context.area.tag_redraw()
        return {"FINISHED"}

    def modal(self, context, event):
        t, v = event.type, event.value
        if t in {"ESC", "RIGHTMOUSE", "RET", "NUMPAD_ENTER"} and v == "PRESS":
            return self._finish(context)

        if t == "TIMER":
            now = time.monotonic()
            dt, self.last = min(now - self.last, 0.1), now
            self._update_doors(context)
            f = sum(MOVE_KEYS[k][0] for k in self.keys)
            s = sum(MOVE_KEYS[k][1] for k in self.keys)
            if f or s:
                speed = RUN_SPEED if event.shift else WALK_SPEED
                norm = math.hypot(f, s)
                fx, fy = -math.sin(self.yaw), math.cos(self.yaw)      # forward
                rx, ry = math.cos(self.yaw), math.sin(self.yaw)       # right
                step = speed * dt / norm
                self._move((fx * f + rx * s) * step, (fy * f + ry * s) * step)
            self._apply_view(context)
            return {"RUNNING_MODAL"}

        if t == "MOUSEMOVE":
            dx, dy = event.mouse_x - self.cx, event.mouse_y - self.cy
            if dx or dy:
                self.yaw -= dx * LOOK_SPEED
                self.pitch = max(-1.4, min(1.4, self.pitch + dy * LOOK_SPEED))
                context.window.cursor_warp(self.cx, self.cy)
            return {"RUNNING_MODAL"}

        if t in MOVE_KEYS and not (t == "W" and event.alt):
            if v == "PRESS":
                self.keys.add(t)
            elif v == "RELEASE":
                self.keys.discard(t)
            return {"RUNNING_MODAL"}

        if v == "PRESS":
            if t in {"E", "F", "LEFTMOUSE"}:
                self._toggle_door(context)
            elif t == "H" or (t == "W" and event.alt):
                hidden = toggle_walls(context)
                self.note = "" if hidden is None else ("walls hidden" if hidden else "walls shown")
            elif t in {"WHEELUPMOUSE", "NUMPAD_PLUS", "EQUAL"}:
                self._zoom(context, 1.1)
            elif t in {"WHEELDOWNMOUSE", "NUMPAD_MINUS", "MINUS"}:
                self._zoom(context, 1 / 1.1)
            elif t == "Z":
                context.space_data.lens = LENS_DEFAULT
            self._header(context)
        elif t == "TRACKPADPAN":                                       # two-finger scroll
            self._zoom(context, 1.01 ** (event.mouse_y - event.mouse_prev_y))
            self._header(context)
        elif t == "TRACKPADZOOM":                                      # pinch
            self._zoom(context, 1.01 ** (event.mouse_x - event.mouse_prev_x))
            self._header(context)
        return {"RUNNING_MODAL"}


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
        self.layout.operator(HDB_OT_walk.bl_idname, text="Walk (First Person)", icon="MOD_DYNAMICPAINT")
        self.layout.label(text="Hotkey: Shift+Alt+F")

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
           HDB_OT_doors_keyframe, HDB_OT_doors_clear_anim, HDB_OT_walk, HDB_PT_view_tools)


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
        kmi = km.keymap_items.new(HDB_OT_walk.bl_idname, "F", "PRESS", alt=True, shift=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
