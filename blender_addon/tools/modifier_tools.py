"""Modifier tools: add / configure / remove / apply modifiers."""

from __future__ import annotations

import bpy

from blender_addon.scene.objid import ensure_obj_id, resolve_object
from blender_addon.tools._registry import ToolFailure, register

# property alias -> (blender attr, scale factor, type)
_PROPS = {
    "width_mm": ("width", 0.001, float),
    "thickness_mm": ("thickness", 0.001, float),
    "segments": ("segments", 1.0, int),
    "profile": ("profile", 1.0, float),
    "count": ("count", 1.0, int),
    "levels_viewport": ("levels", 1.0, int),
    "levels_render": ("render_levels", 1.0, int),
    "offset": ("offset", 1.0, float),
    "operation": ("operation", 1.0, str),
    "solver": ("solver", 1.0, str),
}


def find_modifier(obj, name: str):
    for m in obj.modifiers:
        if m.name == name:
            return m
    raise ToolFailure(f"modifier '{name}' not found on '{obj.name}'. Existing: "
                      + ", ".join(m.name for m in obj.modifiers) or "(none)")


def apply_modifier_op(obj, mod_name: str) -> None:
    """Apply a modifier to the mesh with context handling for headless runs."""
    try:
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.object.modifier_apply(apply_as="DATA", modifier=mod_name)
        return
    except Exception:  # noqa: BLE001 - fall through to the plain call
        pass
    try:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(apply_as="DATA", modifier=mod_name)
    except Exception as exc:  # noqa: BLE001
        raise ToolFailure(f"could not apply modifier '{mod_name}': {exc}") from exc


def _new_modifier(obj, type_name: str, fallback_name: str):
    try:
        return obj.modifiers.new(name=fallback_name, type=type_name)
    except TypeError as exc:
        raise ToolFailure(f"modifier type '{type_name}' not supported here: {exc}") from exc


def _set_known_prop(mod, property: str, value):
    if property in _PROPS:
        attr, factor, typ = _PROPS[property]
        if property == "constant_offset":
            raise ToolFailure("use 'constant_offset' key with a 3-value array")
        setattr(mod, attr, typ(value) * factor if typ in (float, int) and factor != 1.0 else typ(value))
        return
    if property == "constant_offset":
        vec = [float(x) * 0.001 for x in value]
        try:
            mod.constant_offset_displace = (vec[0], vec[1], vec[2])
            return
        except Exception as exc:  # noqa: BLE001
            raise ToolFailure(f"this modifier has no constant_offset_displace: {exc}") from exc
    raise ToolFailure(f"unsupported property '{property}'. Supported keys: "
                      + ", ".join(sorted(_PROPS)) + ", constant_offset")


@register("add_bevel", category="modifier", risk="mutating")
def tool_add_bevel(args: dict) -> dict:
    obj = resolve_object(args)
    mod = _new_modifier(obj, "BEVEL", "Bevel")
    mod.width = float(args["width_mm"]) / 1000.0
    mod.segments = int(args.get("segments", 4))
    mod.profile = float(args.get("profile", 0.5))
    if args.get("limit_method"):
        mod.limit_method = args["limit_method"]
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "modifier_name": mod.name, "type": "BEVEL", "width_mm": args["width_mm"]}


@register("add_boolean", category="modifier", risk="mutating")
def tool_add_boolean(args: dict) -> dict:
    obj = resolve_object(args)
    tool_obj = resolve_object(args, field="tool_object_id")
    if tool_obj.type != "MESH":
        raise ToolFailure("boolean tool object must be a mesh")
    mod = _new_modifier(obj, "BOOLEAN", "Boolean")
    mod.operation = args.get("operation", "DIFFERENCE")
    mod.object = tool_obj
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "modifier_name": mod.name, "type": "BOOLEAN",
            "operation": mod.operation, "tool_object_id": ensure_obj_id(tool_obj)}


@register("add_solidify", category="modifier", risk="mutating")
def tool_add_solidify(args: dict) -> dict:
    obj = resolve_object(args)
    mod = _new_modifier(obj, "SOLIDIFY", "Solidify")
    mod.thickness = float(args["thickness_mm"]) / 1000.0
    mod.offset = float(args.get("offset", -1.0))
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "modifier_name": mod.name, "type": "SOLIDIFY",
            "thickness_mm": args["thickness_mm"]}


@register("add_subdivision", category="modifier", risk="mutating")
def tool_add_subdivision(args: dict) -> dict:
    obj = resolve_object(args)
    mod = _new_modifier(obj, "SUBSURF", "Subdivision")
    mod.levels = int(args.get("levels_viewport", 2))
    mod.render_levels = int(args.get("levels_render", args.get("levels_viewport", 2)))
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "modifier_name": mod.name, "type": "SUBSURF",
            "levels_viewport": mod.levels, "levels_render": mod.render_levels}


@register("add_mirror", category="modifier", risk="mutating")
def tool_add_mirror(args: dict) -> dict:
    obj = resolve_object(args)
    mod = _new_modifier(obj, "MIRROR", "Mirror")
    axis = str(args.get("axis", "X")).upper()
    mod.use_axis[0] = axis == "X"
    mod.use_axis[1] = axis == "Y"
    mod.use_axis[2] = axis == "Z"
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "modifier_name": mod.name, "type": "MIRROR", "axis": axis}


@register("add_array", category="modifier", risk="mutating")
def tool_add_array(args: dict) -> dict:
    obj = resolve_object(args)
    mod = _new_modifier(obj, "ARRAY", "Array")
    mod.count = int(args.get("count", 1))
    offset = args.get("offset_mm") or [0.0, 0.0, 0.0]
    vec = [float(x) * 0.001 for x in offset]
    mod.constant_offset_displace = (vec[0], vec[1], vec[2])
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "modifier_name": mod.name, "type": "ARRAY", "count": mod.count}


@register("remove_modifier", category="modifier", risk="mutating")
def tool_remove_modifier(args: dict) -> dict:
    obj = resolve_object(args)
    mod = find_modifier(obj, str(args["modifier_name"]))
    name = mod.name
    obj.modifiers.remove(mod)
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "removed_modifier": name}


@register("apply_modifier", category="modifier", risk="mutating")
def tool_apply_modifier(args: dict) -> dict:
    obj = resolve_object(args)
    mod_name = str(args["modifier_name"])
    find_modifier(obj, mod_name)
    apply_modifier_op(obj, mod_name)
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "applied_modifier": mod_name, "applied": True}


@register("set_modifier_property", category="modifier", risk="mutating")
def tool_set_modifier_property(args: dict) -> dict:
    obj = resolve_object(args)
    mod = find_modifier(obj, str(args["modifier_name"]))
    prop = str(args["property"])
    value = args["value"]
    _set_known_prop(mod, prop, value)
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "modifier_name": mod.name, "property": prop, "value": value}
