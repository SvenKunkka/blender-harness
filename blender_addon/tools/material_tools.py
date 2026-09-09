"""Material tools: create, assign, and set Principled-BSDF factors."""

from __future__ import annotations

import bpy

from blender_addon.scene.objid import ensure_obj_id, resolve_object
from blender_addon.tools._registry import ToolFailure, register


def _hex_to_rgba(hex_color: str):
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        raise ToolFailure("color_hex must look like '#rrggbb'")
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)
    except ValueError as exc:
        raise ToolFailure("color_hex must look like '#rrggbb'") from exc


def _get_mat(name: str):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    return mat


def _principled(mat, fallback_diffuse=None):
    """Return a Principled BSDF node (creating a node tree if needed)."""
    try:
        if not mat.use_nodes or mat.node_tree is None:
            mat.use_nodes = True
        tree = mat.node_tree
        nodes = tree.nodes
        p = nodes.get("Principled BSDF")
        if p is None:
            # fresh default node trees already contain one; create otherwise
            from bpy import ops  # noqa: PLC0415

            try:
                for n in list(nodes):
                    nodes.remove(n)
                p = nodes.new("ShaderNodeBsdfPrincipled")
                p.location = (0, 0)
                out = nodes.new("ShaderNodeOutputMaterial")
                out.location = (300, 0)
                tree.links.new(p.outputs["BSDF"], out.inputs["Surface"])
            except Exception:  # noqa: BLE001
                p = None
        return p
    except Exception:  # noqa: BLE001 - read-only/material-less contexts
        return None


def _set_factor(mat, field: str, value: float, min_v: float = 0.0, max_v: float = 1.0) -> None:
    value = max(min_v, min(max_v, float(value)))
    node = _principled(mat)
    if node is not None:
        try:
            if field == "color":
                node.inputs["Base Color"].default_value = value
            else:
                node.inputs[field].default_value = value
            return
        except Exception:  # noqa: BLE001
            pass
    # fallback for environments without node access (e.g. some headless runs)
    if field == "color":
        mat.diffuse_color = value
    else:
        mat[field] = value


@register("create_material", category="material", risk="mutating")
def tool_create_material(args: dict) -> dict:
    name = str(args.get("name") or "Material").strip()
    if not name:
        raise ToolFailure("name is required")
    mat = _get_mat(name)
    if args.get("color_hex"):
        _set_factor(mat, "color", _hex_to_rgba(args["color_hex"]))
    if args.get("metallic") is not None:
        _set_factor(mat, "Metallic", float(args["metallic"]))
    if args.get("roughness") is not None:
        _set_factor(mat, "Roughness", float(args["roughness"]))
    return {"material_name": mat.name, "created": mat.name == name}


@register("assign_material", category="material", risk="mutating")
def tool_assign_material(args: dict) -> dict:
    obj = resolve_object(args)
    mat_name = str(args["material_name"])
    mat = _get_mat(mat_name)
    created = False
    if obj.type != "MESH":
        raise ToolFailure("materials can only be assigned to mesh objects")
    try:
        if mat.name not in [m.name for m in obj.data.materials]:
            obj.data.materials.append(mat)
            created = True
    except Exception as exc:  # noqa: BLE001
        raise ToolFailure(f"could not assign material: {exc}") from exc
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "material_name": mat.name, "assigned": True}


def _obj_mat(obj, material_name=None):
    mat_name = material_name or obj.active_material.name if obj.active_material else None
    if mat_name is None:
        try:
            mats = obj.data.materials
            if mats:
                mat_name = mats[0].name
        except Exception:  # noqa: BLE001
            pass
    if mat_name is None:
        raise ToolFailure(f"'{obj.name}' has no material — call create_material / assign_material first")
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        raise ToolFailure(f"material '{mat_name}' no longer exists")
    return mat


@register("set_base_color", category="material", risk="mutating")
def tool_set_base_color(args: dict) -> dict:
    obj = resolve_object(args)
    mat = _obj_mat(obj, args.get("material_name"))
    rgba = _hex_to_rgba(str(args["color_hex"]))
    _set_factor(mat, "color", rgba)
    return {"object_id": ensure_obj_id(obj), "material_name": mat.name, "base_color": str(args["color_hex"])}


@register("set_metallic", category="material", risk="mutating")
def tool_set_metallic(args: dict) -> dict:
    obj = resolve_object(args)
    mat = _obj_mat(obj, args.get("material_name"))
    _set_factor(mat, "Metallic", float(args["metallic"]))
    return {"object_id": ensure_obj_id(obj), "material_name": mat.name, "metallic": float(args["metallic"])}


@register("set_roughness", category="material", risk="mutating")
def tool_set_roughness(args: dict) -> dict:
    obj = resolve_object(args)
    mat = _obj_mat(obj, args.get("material_name"))
    _set_factor(mat, "Roughness", float(args["roughness"]))
    return {"object_id": ensure_obj_id(obj), "material_name": mat.name, "roughness": float(args["roughness"])}


@register("list_materials", category="material", risk="safe")
def tool_list_materials(args: dict) -> dict:
    out = []
    for mat in bpy.data.materials:
        objects = 0
        try:
            for o in bpy.data.objects:
                if o.type == "MESH" and o.data and mat.name in [m.name for m in o.data.materials if m]:
                    objects += 1
        except Exception:  # noqa: BLE001
            pass
        out.append({"name": mat.name, "objects": objects})
    return {"materials": out}
