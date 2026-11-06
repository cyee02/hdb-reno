"""Shared helpers for the room renovation scripts (living room, study, entrance).

Geometry is written in plan millimetres (y down the page) and converted to Blender
metres (Y up), like the other build scripts.
"""
import json
import math

import bpy
import bmesh

import door_motion


def material(name, rgb, roughness=0.5, metallic=0.0, emission=0.0, alpha=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = (*rgb, 1.0)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("blend_method", "BLEND"), ("surface_render_method", "BLENDED")):
            if hasattr(mat, attr):
                try:
                    setattr(mat, attr, val)
                except TypeError:
                    pass
    mat.diffuse_color = (*rgb, alpha)
    return mat


def glass_material():
    """Same see-through glass as the kitchen partition."""
    return (bpy.data.materials.get("Glass") or bpy.data.materials.get("KT_Glass")
            or material("KT_Glass", (0.6, 0.8, 0.95), 0.05, alpha=0.25))


class Mesh:
    """Boxes and cylinders in plan mm; `slot` picks the material index."""

    def __init__(self):
        self.bm = bmesh.new()

    def _v(self, x, y, z):
        return self.bm.verts.new((x / 1000, -y / 1000, z / 1000))

    def _faces(self, rings, slot):
        faces = [self.bm.faces.new(list(reversed(rings[0]))), self.bm.faces.new(rings[1])]
        n = len(rings[0])
        for k in range(n):
            j = (k + 1) % n
            faces.append(self.bm.faces.new((rings[0][k], rings[0][j], rings[1][j], rings[1][k])))
        for f in faces:
            f.material_index = slot

    def box(self, x0, y0, x1, y1, z0, z1, slot=0):
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        if x1 - x0 < 0.01 or y1 - y0 < 0.01 or z1 - z0 < 0.01:
            return
        quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        self._faces([[self._v(x, y, z0) for x, y in quad], [self._v(x, y, z1) for x, y in quad]], slot)

    def cyl(self, cx, cy, r, z0, z1, slot=0, n=24):
        ring = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
        self._faces([[self._v(x, y, z0) for x, y in ring], [self._v(x, y, z1) for x, y in ring]], slot)

    def finish(self, name, coll, mats):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in mats:
            me.materials.append(m)
        obj = bpy.data.objects.new(name, me)
        coll.objects.link(obj)
        return obj


class Frame:
    """Local frame for a unit whose front faces `front`: `a` runs along the front (plan x for
    north/south fronts, plan y for east/west), `d` is the distance out from the front face
    (negative = into the unit)."""

    def __init__(self, m, rect, front):
        x0, y0, x1, y1 = rect
        self.m, self.front = m, front
        self.face = {"north": y0, "south": y1, "east": x1, "west": x0}[front]
        self.a0, self.a1 = (x0, x1) if front in ("north", "south") else (y0, y1)
        self.depth = (y1 - y0) if front in ("north", "south") else (x1 - x0)

    def pt(self, a, d):
        if self.front == "north":
            return a, self.face - d
        if self.front == "south":
            return a, self.face + d
        if self.front == "east":
            return self.face + d, a
        return self.face - d, a  # west

    def box(self, a0, a1, d0, d1, z0, z1, slot=0):
        x0, y0 = self.pt(a0, d0)
        x1, y1 = self.pt(a1, d1)
        self.m.box(x0, y0, x1, y1, z0, z1, slot)

    def cyl(self, a, d, r, z0, z1, slot=0, n=24):
        x, y = self.pt(a, d)
        self.m.cyl(x, y, r, z0, z1, slot, n)


def child_collection(parent_name, child_name):
    """Empty (or create) `child_name` under `parent_name`; other collections are untouched."""
    parent = bpy.data.collections.get(parent_name)
    if not parent:
        parent = bpy.data.collections.new(parent_name)
        bpy.context.scene.collection.children.link(parent)
    child = bpy.data.collections.get(child_name)
    if child:
        for obj in list(child.all_objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        child = bpy.data.collections.new(child_name)
        parent.children.link(child)
    return child


def register_cameras(prefix, cams):
    """Replace this room's views (keys starting with `prefix`) in scene["room_cameras"]."""
    scene = bpy.context.scene
    all_cams = {k: v for k, v in json.loads(scene.get("room_cameras", "{}")).items() if not k.startswith(prefix)}
    all_cams.update(cams)
    scene["room_cameras"] = json.dumps(all_cams)


def glass_partition(p, ceiling, coll, frame_mat, glass_mat, prefix):
    """Top-hung, full-height slim black-frame glass panels, one track per panel (like the kitchen).

    p["axis"] "x": the partition runs along plan x at y = p["at"]; "y": along plan y at x = p["at"].
    p["stack"] "start" / "end": when open, every panel slides to that end of p["span"] and stacks.
    Panels are built CLOSED and slide on scene["door_<p['id']>"] (0 closed - 1 open).
    """
    a0, a1 = p["span"]
    c, axis = p["at"], p["axis"]
    n, lap, fw = p["panels"], p["overlap"], p["frame"]
    w = ((a1 - a0) + (n - 1) * lap) / n
    offs = [(t - (p["tracks"] - 1) / 2) * p["track_gap"] for t in range(p["tracks"])]
    to_end = p["stack"] == "end"

    def box(m, s, e, o0, o1, z0, z1, slot):
        if axis == "x":
            m.box(s, c + o0, e, c + o1, z0, z1, slot)
        else:
            m.box(c + o0, s, c + o1, e, z0, z1, slot)

    track = Mesh()
    box(track, a0, a1, offs[0] - 25, offs[-1] + 25, ceiling - 45, ceiling, 0)
    track.finish(f"{prefix}_{p['id']}_track", coll, [frame_mat])

    gid = p["id"]
    door_motion.forget_groups(gid)
    door_motion.register_group(gid, p["label"], p.get("open", 0.0))
    z0, z1 = 10, ceiling - 45
    for k in range(n):
        s = a0 + k * (w - lap)                       # closed position
        parked = a1 - w if to_end else a0            # fully open position
        o = offs[k % len(offs)]
        m = Mesh()
        box(m, s, s + fw, o - 14, o + 14, z0, z1, 0)               # stiles
        box(m, s + w - fw, s + w, o - 14, o + 14, z0, z1, 0)
        box(m, s, s + w, o - 14, o + 14, z0, z0 + fw + 20, 0)      # rails
        box(m, s, s + w, o - 14, o + 14, z1 - fw, z1, 0)
        box(m, s + fw, s + w - fw, o - 4, o + 4, z0 + fw + 20, z1 - fw, 1)  # glass
        obj = m.finish(f"{prefix}_{p['id']} panel {k + 1}", coll, [frame_mat, glass_mat])
        slide = (parked - s) / 1000
        door_motion.drive(obj, gid, (slide, 0, 0) if axis == "x" else (0, -slide, 0))
