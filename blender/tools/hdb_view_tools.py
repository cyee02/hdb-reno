"""HDB Reno view tools: toggle the walls on/off in the viewport.

Hotkey: Alt+W in the 3D viewport (also in the N panel > HDB Reno tab).
Hides the `Flat.Walls` collection plus window frames/glass (they'd float without walls).
Doors stay visible. Viewport only - renders are not affected.

Install: Edit > Preferences > Add-ons > Install from Disk... > this file, then enable it.
"""
import bpy

bl_info = {
    "name": "HDB Reno View Tools",
    "author": "hdb-reno",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Alt+W, N panel > HDB Reno",
    "description": "Toggle the flat's walls on/off for easier viewing",
    "category": "3D View",
}

WALLS = "Flat.Walls"
OPENINGS = "Flat.Openings"
WINDOW_PREFIXES = ("Window_", "Glass_")


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


addon_keymaps = []


def register():
    bpy.utils.register_class(HDB_OT_toggle_walls)
    bpy.utils.register_class(HDB_PT_view_tools)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new(HDB_OT_toggle_walls.bl_idname, "W", "PRESS", alt=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    bpy.utils.unregister_class(HDB_PT_view_tools)
    bpy.utils.unregister_class(HDB_OT_toggle_walls)
