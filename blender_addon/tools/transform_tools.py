"""Transform tools: location / rotation / scale / dimensions / apply."""

from __future__ import annotations

import bpy

from blender_addon.scene.objid import ensure_obj_id, resolve_object
from blender_addon.scene.units import deg3_to_rad3, mm3_to_m3, m3_to_mm3, rad3_to_deg3
from blender_addon.scene.vec import add, apply_matrix_rows, euler_rad_matrix, mul, scale as vec_scale
from blender_addon.tools._registry import ToolFailure, register


def _world_apply(obj) -> None:
    """Pure-python equivalent of Object > Apply > All for MESH objects (no
    mathutils dependency). Parents are not supported."""
    if obj.parent is not None:
        raise ToolFailure("apply_transform does not support parented objects yet — unparent first")
    if obj.type != "MESH" or obj.data is None:
        raise ToolFailure("apply_transform currently supports MESH objects only")
    import math

    loc = tuple(obj.location)
    rot = [float(x) for x in obj.rotation_euler]
    scl = [float(x) for x in obj.scale]
    m = euler_rad_matrix(rot[0], rot[1], rot[2])
    me = obj.data
    verts = me.vertices
    # streamable update: direct attribute loop (mesh sizes here are design-scale)
    for v in verts:
        co = v.co
        v.co = add(loc, apply_matrix_rows(mul((co[0], co[1], co[2]), scl), m))
    me.update()
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)


@register("set_location", category="transform", risk="mutating")
def tool_set_location(args: dict) -> dict:
    obj = resolve_object(args)
    vec = mm3_to_m3(args["location_mm"])
    obj.location = (vec[0], vec[1], vec[2])
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "location_mm": m3_to_mm3([obj.location[i] for i in range(3)])}


@register("move_object", category="transform", risk="mutating")
def tool_move_object(args: dict) -> dict:
    obj = resolve_object(args)
    delta = mm3_to_m3(args["delta_mm"])
    obj.location = (obj.location[0] + delta[0], obj.location[1] + delta[1], obj.location[2] + delta[2])
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "location_mm": m3_to_mm3([obj.location[i] for i in range(3)])}


@register("set_rotation", category="transform", risk="mutating")
def tool_set_rotation(args: dict) -> dict:
    obj = resolve_object(args)
    rad = deg3_to_rad3(args["rotation_deg"])
    obj.rotation_euler = (rad[0], rad[1], rad[2])
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "rotation_deg": rad3_to_deg3(list(obj.rotation_euler))}


@register("rotate_object", category="transform", risk="mutating")
def tool_rotate_object(args: dict) -> dict:
    obj = resolve_object(args)
    delta = deg3_to_rad3(args["delta_deg"])
    cur = list(obj.rotation_euler)
    obj.rotation_euler = (cur[0] + delta[0], cur[1] + delta[1], cur[2] + delta[2])
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "rotation_deg": rad3_to_deg3(list(obj.rotation_euler))}


@register("set_scale", category="transform", risk="mutating")
def tool_set_scale(args: dict) -> dict:
    obj = resolve_object(args)
    scl = [float(x) for x in args["scale"]]
    if any(abs(s) < 1e-6 for s in scl):
        raise ToolFailure("scale components must be non-zero")
    obj.scale = (scl[0], scl[1], scl[2])
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "scale": [float(x) for x in obj.scale]}


@register("set_dimensions", "set_exact_dimensions_mm", category="transform", risk="mutating")
def tool_set_dimensions(args: dict) -> dict:
    obj = resolve_object(args)
    dims_m = mm3_to_m3([float(x) for x in args["dimensions_mm"]])
    if any(d <= 0 for d in dims_m):
        raise ToolFailure("dimensions must be positive")
    obj.dimensions = (dims_m[0], dims_m[1], dims_m[2])
    # refresh the view layer so obj.dimensions reports the new values
    view_layer = getattr(bpy.context, "view_layer", None)
    update = getattr(view_layer, "update", None)
    if update is not None:
        update()
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "dimensions_mm": m3_to_mm3([obj.dimensions[i] for i in range(3)])}


@register("apply_transform", category="transform", risk="mutating")
def tool_apply_transform(args: dict) -> dict:
    obj = resolve_object(args)
    _world_apply(obj)
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "applied": True}
