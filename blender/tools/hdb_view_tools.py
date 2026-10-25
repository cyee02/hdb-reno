"""HDB Reno view tools for the 3D viewport (also in the N panel > HDB Reno tab).

- Alt+W        toggle the walls on/off. Hides the `Flat.Walls` collection plus window
               frames/glass (they'd float without walls). Doors stay visible.
- Shift+Alt+P  jump to the plan view: straight down from above (orthographic), north up,
               framed on the whole flat - like the HDB floor plan.
Viewport only - renders are not affected.

Install: Edit > Preferences > Add-ons > Install from Disk... > this file, then enable it.
"""
import bpy
from mathutils import Quaternion, Vector

bl_info = {
    "name": "HDB Reno View Tools",
    "author": "hdb-reno",
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Alt+W / Shift+Alt+P, N panel > HDB Reno",
    "description": "Toggle the flat's walls; jump to the plan view",
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


addon_keymaps = []


def register():
    bpy.utils.register_class(HDB_OT_toggle_walls)
    bpy.utils.register_class(HDB_OT_plan_view)
    bpy.utils.register_class(HDB_PT_view_tools)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(HDB_OT_toggle_walls.bl_idname, "W", "PRESS", alt=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(HDB_OT_plan_view.bl_idname, "P", "PRESS", alt=True, shift=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    bpy.utils.unregister_class(HDB_PT_view_tools)
    bpy.utils.unregister_class(HDB_OT_plan_view)
    bpy.utils.unregister_class(HDB_OT_toggle_walls)
