"""Product-design helper tools for consumer/industrial design work:
rounded boxes, shells, cutouts, holes, holes grids, wall thickness, keyboard
case / mouse volume / knob generators, measuring, centring, aligning, mirroring.

All geometry helpers build real meshes in millimetres (no mathutils needed).
"""

from __future__ import annotations

import math

import bpy

from blender_addon.scene.objid import ensure_obj_id, resolve_object
from blender_addon.scene.units import mm3_to_m3, m3_to_mm3
from blender_addon.scene.vec import add, apply_matrix_rows, euler_rad_matrix, mul, sub
from blender_addon.tools._registry import ToolFailure, register
from blender_addon.tools.mesh_tools import (
    _cube_mesh,
    _cylinder_mesh,
    _world_bounds,
    create_mesh_object,
    rounded_prism_mesh,
    spheroid_mesh,
)
from blender_addon.tools.modifier_tools import apply_modifier_op

MM = 0.001


def _finish(obj, oid_name: str, extra: dict) -> dict:
    extra.update({"object_id": ensure_obj_id(obj), "name": obj.name, "type": "MESH"})
    return extra


# ---------------------------------------------------------------------------
# geometry modifiers (boolean helpers)
# ---------------------------------------------------------------------------

def _bool_difference(target, cutter, label: str = "BH_Cut") -> dict:
    """Subtract cutter from target. Applies when possible; otherwise leaves an
    applied-on-demand modifier and hides the cutter."""
    mod = target.modifiers.new(name=label, type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    try:
        apply_modifier_op(target, mod.name)
        if cutter.name in bpy.data.objects:
            bpy.data.objects.remove(cutter, do_unlink=True)
        return {"applied": True, "modifier": None}
    except ToolFailure as exc:
        cutter.hide_viewport = True
        cutter.hide_render = True
        return {"applied": False, "modifier": mod.name, "note": str(exc)}


def _make_cutter(shape: str, dims_mm, location_m, axis: str = "Z", radius: float = 0.0,
                 segments: int = 6) -> object:
    if shape == "box":
        v, f = _cube_mesh(dims_mm[0], dims_mm[1], dims_mm[2])
    elif shape == "cylinder":
        depth = dims_mm[0] if len(dims_mm) == 1 else dims_mm[0]
        v, f = _cylinder_mesh(radius, depth, 32)
    else:  # rounded box
        v, f = rounded_prism_mesh(dims_mm[0], dims_mm[1], dims_mm[2], radius, segments)
    obj = create_mesh_object("BH_Cutter", v, f)
    obj.location = (location_m[0], location_m[1], location_m[2])
    axis = axis.upper()
    if shape == "cylinder":
        if axis == "X":
            obj.rotation_euler = (0.0, math.pi / 2.0, 0.0)
        elif axis == "Y":
            obj.rotation_euler = (-math.pi / 2.0, 0.0, 0.0)
    return obj


def _remove_object_quiet(obj) -> None:
    try:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@register("create_rounded_box", category="product", risk="mutating")
def tool_create_rounded_box(args: dict) -> dict:
    w, d, h = (float(x) for x in args["dimensions_mm"])
    r = float(args.get("corner_radius_mm", 0.0))
    seg = int(args.get("corner_segments", 6))
    name = args.get("name") or "RoundedBox"
    v, f = rounded_prism_mesh(w, d, h, r, seg)
    obj = create_mesh_object(name, v, f, args.get("location_mm"))
    return _finish(obj, name, {"kind": "rounded_box", "dimensions_mm": [w, d, h],
                               "corner_radius_mm": r, "corner_segments": seg})


@register("create_shell", category="product", risk="mutating")
def tool_create_shell(args: dict) -> dict:
    w, d, h = (float(x) for x in args["dimensions_mm"])
    wall = float(args["wall_thickness_mm"])
    bottom = float(args.get("bottom_thickness_mm", 2.0))
    r = float(args.get("corner_radius_mm", 0.0))
    seg = int(args.get("corner_segments", 6))
    name = args.get("name") or "Shell"
    if wall * 2 >= min(w, d) or bottom >= h:
        raise ToolFailure("wall_thickness/bottom_thickness are too large for the outer dimensions")
    outer_v, outer_f = rounded_prism_mesh(w, d, h, r, seg)
    inner_w = w - 2.0 * wall
    inner_d = d - 2.0 * wall
    inner_h = h - bottom
    inner_r = max(0.0, r - wall)
    inner_v, inner_f = rounded_prism_mesh(inner_w, inner_d, inner_h, inner_r, seg)

    outer = create_mesh_object(name, outer_v, outer_f)
    loc_m = mm3_to_m3(args.get("location_mm") or [0.0, 0.0, 0.0])
    outer.location = (loc_m[0], loc_m[1], loc_m[2])

    inner = create_mesh_object(f"{name}_cavity", inner_v, inner_f)
    # cavity sits on top of the base: centre z = bottom/2 above the shell centre
    inner.location = (loc_m[0], loc_m[1], loc_m[2] + bottom * MM / 2.0)

    res = _bool_difference(outer, inner, label="BH_Shell")
    return _finish(outer, name, {"kind": "shell", "dimensions_mm": [w, d, h],
                                 "wall_thickness_mm": wall, "bottom_thickness_mm": bottom,
                                 "corner_radius_mm": r,
                                 "boolean": res})


@register("measure_distance", category="product", risk="safe")
def tool_measure_distance(args: dict) -> dict:
    a = resolve_object(args, field="object_a_id")
    b = resolve_object(args, field="object_b_id")
    mode = args.get("mode", "origin")
    if mode == "origin":
        pa = (a.location[0], a.location[1], a.location[2])
        pb = (b.location[0], b.location[1], b.location[2])
        dist = math.sqrt(sum((pa[i] - pb[i]) ** 2 for i in range(3)))
    elif mode == "center":
        ca = _world_center(a)
        cb = _world_center(b)
        dist = math.sqrt(sum((ca[i] - cb[i]) ** 2 for i in range(3)))
    elif mode == "closest":
        dist = _aabb_distance(a, b)
    else:
        raise ToolFailure(f"unknown mode '{mode}' (origin|center|closest)")
    return {"object_a_id": ensure_obj_id(a), "object_b_id": ensure_obj_id(b),
            "mode": mode, "distance_mm": round(dist * 1000.0, 3)}


def _world_center(obj):
    mins, maxs = _world_bounds(obj)
    return tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))


def _aabb_distance(a, b) -> float:
    am, aM = _world_bounds(a)
    bm, bM = _world_bounds(b)
    sq = 0.0
    for i in range(3):
        if aM[i] < bm[i]:
            sq += (bm[i] - aM[i]) ** 2
        elif bM[i] < am[i]:
            sq += (am[i] - bM[i]) ** 2
    return math.sqrt(sq)


@register("measure_object", category="product", risk="safe")
def tool_measure_object(args: dict) -> dict:
    obj = resolve_object(args)
    mins, maxs = _world_bounds(obj)
    size = [maxs[i] - mins[i] for i in range(3)]
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "dimensions_mm": m3_to_mm3([size[0], size[1], size[2]]),
            "center_mm": m3_to_mm3([(mins[i] + maxs[i]) / 2.0 for i in range(3)]),
            "location_mm": m3_to_mm3([obj.location[i] for i in range(3)])}


@register("center_object", category="product", risk="mutating")
def tool_center_object(args: dict) -> dict:
    obj = resolve_object(args)
    if obj.type != "MESH":
        raise ToolFailure("center_object supports MESH objects only")
    loc = tuple(obj.location)
    rot = [float(x) for x in obj.rotation_euler]
    scl = [float(x) for x in obj.scale]
    m = euler_rad_matrix(rot[0], rot[1], rot[2])
    cs = [(c[0], c[1], c[2]) for c in obj.bound_box]
    local_center = tuple((min(c[i] for c in cs) + max(c[i] for c in cs)) / 2.0 for i in range(3))
    world_center_offset = apply_matrix_rows(mul(local_center, scl), m)
    origin_moved = False
    if args.get("origin_to_geometry", True):
        me = obj.data
        for v in me.vertices:
            co = v.co
            v.co = (co[0] - local_center[0], co[1] - local_center[1], co[2] - local_center[2])
        me.update()
        obj.location = (loc[0] + world_center_offset[0],
                        loc[1] + world_center_offset[1],
                        loc[2] + world_center_offset[2])
        origin_moved = True
        loc = tuple(obj.location)

    if args.get("align_to"):
        ref = resolve_object(args, field="align_to")
        target = _world_center(ref)
    else:
        target = (0.0, 0.0, 0.0) if args.get("move_to_world_origin", False) else None
    moved = False
    if target is not None:
        obj.location = (target[0], target[1], target[2])
        moved = True
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "origin_to_geometry": origin_moved, "moved_to_origin": moved,
            "location_mm": m3_to_mm3([obj.location[i] for i in range(3)])}


@register("align_objects", category="product", risk="mutating")
def tool_align_objects(args: dict) -> dict:
    ids = args.get("object_ids") or []
    if not ids:
        raise ToolFailure("object_ids required")
    axis = {"X": 0, "Y": 1, "Z": 2}[str(args.get("axis", "X")).upper()]
    mode = args.get("mode", "center")
    objs = [resolve_object({"object_id": oid}) for oid in ids]
    ref = objs[0]
    if args.get("reference_id"):
        ref = resolve_object(args, field="reference_id")
    rbounds = _world_bounds(ref)
    if mode == "min":
        coord = rbounds[0][axis]
    elif mode == "max":
        coord = rbounds[1][axis]
    else:
        coord = (rbounds[0][axis] + rbounds[1][axis]) / 2.0
    moved = []
    for o in objs:
        ob = _world_bounds(o)
        if mode == "min":
            cur = ob[0][axis]
        elif mode == "max":
            cur = ob[1][axis]
        else:
            cur = (ob[0][axis] + ob[1][axis]) / 2.0
        loc = list(o.location)
        loc[axis] += coord - cur
        o.location = tuple(loc)
        moved.append({"id": ensure_obj_id(o), "name": o.name})
    return {"aligned": len(moved), "objects": moved, "axis": ["X", "Y", "Z"][axis], "mode": mode}


@register("mirror_object", category="product", risk="mutating")
def tool_mirror_object(args: dict) -> dict:
    obj = resolve_object(args)
    if obj.type != "MESH" or obj.data is None:
        raise ToolFailure("mirror_object supports MESH objects only")
    axis = {"X": 0, "Y": 1, "Z": 2}[str(args.get("axis", "X")).upper()]
    src = obj.data
    verts_new = []
    for v in src.vertices:
        co = list(v.co)
        co[axis] = -co[axis]
        verts_new.append(tuple(co))
    faces_new = [list(reversed(p.vertices)) for p in src.polygons]
    name = args.get("name") or f"{obj.name}_mirror"
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts_new, [], faces_new)
    me.update()
    new_obj = bpy.data.objects.new(name, me)
    if not new_obj.users_collection:
        bpy.context.scene.collection.objects.link(new_obj)
    new_obj.location = tuple(obj.location)
    new_obj.rotation_euler = tuple(obj.rotation_euler)
    new_obj.scale = tuple(obj.scale)
    new_obj.select_set(True)
    if bpy.context.view_layer is not None:
        bpy.context.view_layer.objects.active = new_obj
    return {"object_id": ensure_obj_id(new_obj), "name": new_obj.name,
            "axis": ["X", "Y", "Z"][axis], "source_id": ensure_obj_id(obj)}


@register("create_cutout", category="product", risk="mutating")
def tool_create_cutout(args: dict) -> dict:
    target = resolve_object(args, field="target_id")
    pos = mm3_to_m3([float(x) for x in args["position_mm"]])
    size = [float(x) for x in args["size_mm"]]
    if target.type != "MESH":
        raise ToolFailure("cutouts need a mesh target")
    cutter = _make_cutter("box", size, pos)
    res = _bool_difference(target, cutter, label="BH_Cutout")
    return {"target_id": ensure_obj_id(target), "name": target.name,
            "operation": "cutout", "size_mm": size, **res}


@register("create_hole", category="product", risk="mutating")
def tool_create_hole(args: dict) -> dict:
    target = resolve_object(args, field="target_id")
    pos = mm3_to_m3([float(x) for x in args["position_mm"]])
    radius = float(args["radius_mm"])
    axis = str(args.get("axis", "Z")).upper()
    if radius <= 0:
        raise ToolFailure("radius_mm must be positive")
    # make the cutter comfortably deeper than the target on its axis
    mins, maxs = _world_bounds(target)
    depth = (maxs[2] - mins[2]) + 0.2
    cutter = _make_cutter("cylinder", [depth], pos, axis=axis, radius=radius)
    res = _bool_difference(target, cutter, label="BH_Hole")
    return {"target_id": ensure_obj_id(target), "name": target.name,
            "operation": "hole", "radius_mm": radius, **res}


@register("create_repeated_holes", category="product", risk="mutating")
def tool_create_repeated_holes(args: dict) -> dict:
    target = resolve_object(args, field="target_id")
    radius = float(args["radius_mm"])
    cx, cy = int(args["count_x"]), int(args["count_y"])
    spacing = [float(x) for x in args["spacing_mm"]]
    center = [float(x) for x in args.get("center_mm", [0.0, 0.0, 0.0])]
    axis = str(args.get("axis", "Z")).upper()
    if cx < 1 or cy < 1 or radius <= 0:
        raise ToolFailure("count_x/count_y must be >= 1 and radius_mm > 0")
    mins, maxs = _world_bounds(target)
    depth = (maxs[2] - mins[2]) + 0.2
    made = 0
    for ix in range(cx):
        for iy in range(cy):
            x = center[0] * MM + (ix - (cx - 1) / 2.0) * spacing[0] * MM
            y = center[1] * MM + (iy - (cy - 1) / 2.0) * spacing[1] * MM
            cutter = _make_cutter("cylinder", [depth], (x, y, center[2] * MM),
                                  axis=axis, radius=radius)
            res = _bool_difference(target, cutter, label="BH_HoleGrid")
            made += 1 if res.get("applied") else 0
    return {"target_id": ensure_obj_id(target), "name": target.name,
            "operation": "hole_grid", "holes_requested": cx * cy,
            "holes_applied": made}


@register("set_wall_thickness", category="product", risk="mutating")
def tool_set_wall_thickness(args: dict) -> dict:
    obj = resolve_object(args)
    thickness = float(args["thickness_mm"])
    mod = obj.modifiers.new(name="BH_Wall", type="SOLIDIFY")
    mod.thickness = thickness * MM
    mod.offset = float(args.get("offset", -1.0))
    applied = False
    if args.get("apply"):
        try:
            apply_modifier_op(obj, mod.name)
            applied = True
        except ToolFailure:
            applied = False
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "thickness_mm": thickness, "modifier_name": mod.name if not applied else None,
            "applied": applied}


@register("create_simple_keyboard_case", category="product", risk="mutating")
def tool_create_simple_keyboard_case(args: dict) -> dict:
    name = args.get("name") or "KeyboardCase"
    w = float(args["width_mm"])
    d = float(args["depth_mm"])
    h = float(args["height_mm"])
    r = float(args.get("corner_radius_mm", 6.0))
    wall = float(args.get("wall_thickness_mm", 2.0))
    bottom = float(args.get("bottom_thickness_mm", 2.0))
    seg = int(args.get("corner_segments", 8))
    res = tool_create_shell({
        "name": name, "dimensions_mm": [w, d, h], "wall_thickness_mm": wall,
        "bottom_thickness_mm": bottom, "corner_radius_mm": r, "corner_segments": seg,
    })
    res["kind"] = "keyboard_case"
    return res


@register("create_simple_mouse_volume", category="product", risk="mutating")
def tool_create_simple_mouse_volume(args: dict) -> dict:
    name = args.get("name") or "MouseVolume"
    l = float(args["length_mm"])
    w = float(args["width_mm"])
    h = float(args["height_mm"])
    seg = int(args.get("segments", 48))
    rings = int(args.get("rings", 24))
    v, f = spheroid_mesh(l, w, h, seg, rings)
    obj = create_mesh_object(name, v, f, args.get("location_mm"))
    return _finish(obj, name, {"kind": "mouse_volume",
                               "length_mm": l, "width_mm": w, "height_mm": h,
                               "note": "symmetric concept volume (highest point at the middle)"})


@register("create_simple_knob", category="product", risk="mutating")
def tool_create_simple_knob(args: dict) -> dict:
    name = args.get("name") or "Knob"
    diameter = float(args["diameter_mm"])
    height = float(args["height_mm"])
    if diameter <= 0 or height <= 0:
        raise ToolFailure("diameter_mm and height_mm must be positive")
    v, f = _cylinder_mesh(diameter / 2.0, height, 48)
    obj = create_mesh_object(name, v, f, args.get("location_mm"))
    corner = args.get("corner_radius_mm")
    mod_note = None
    if corner:
        mod = obj.modifiers.new(name="Bevel", type="BEVEL")
        mod.width = float(corner) * MM
        mod.segments = 6
        mod_note = mod.name
    return _finish(obj, name, {"kind": "knob", "diameter_mm": diameter, "height_mm": height,
                               "corner_radius_mm": corner, "modifier_name": mod_note})
