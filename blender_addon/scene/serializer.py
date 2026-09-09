"""Turn the live Blender scene into the structured representation the AI sees.

All lengths are converted to millimetres here — the model never sees metres.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from blender_addon.scene.objid import ensure_all, ensure_obj_id
from blender_addon.scene.units import m3_to_mm3, rad3_to_deg3


def _mesh_stats(obj: Any) -> Optional[Dict[str, int]]:
    if obj.type != "MESH":
        return None
    try:
        me = obj.data
        tris = sum(max(0, len(p.vertices) - 2) for p in me.polygons)
        return {"vertices": len(me.vertices), "edges": len(me.edges),
                "faces": len(me.polygons), "triangles": tris}
    except Exception:  # noqa: BLE001
        return None


def _modifier_params(mod: Any) -> Dict[str, Any]:
    t = mod.type
    out: Dict[str, Any] = {"name": mod.name, "type": t}
    try:
        if t == "BEVEL":
            out["width_mm"] = round(mod.width * 1000.0, 3)
            out["segments"] = mod.segments
            out["profile"] = mod.profile
        elif t == "SOLIDIFY":
            out["thickness_mm"] = round(mod.thickness * 1000.0, 3)
            out["offset"] = mod.offset
        elif t == "ARRAY":
            out["count"] = mod.count
            vec = getattr(mod, "constant_offset_displace", None)
            if vec is not None:
                out["constant_offset_mm"] = m3_to_mm3([vec[0], vec[1], vec[2]])
        elif t == "SUBSURF":
            out["levels_viewport"] = mod.levels
            out["levels_render"] = mod.render_levels
        elif t == "MIRROR":
            out["axis"] = [bool(getattr(mod, "use_axis", [False] * 3)[i]) for i in range(3)]
        elif t == "BOOLEAN":
            out["operation"] = mod.operation
            if mod.object:
                out["tool_object"] = mod.object.name
    except Exception:  # noqa: BLE001
        pass
    return out


def object_entry(obj: Any, detail: bool = True) -> Dict[str, Any]:
    from blender_addon.scene.units import m_to_mm, rad_to_deg

    entry: Dict[str, Any] = {
        "id": ensure_obj_id(obj),
        "name": obj.name,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "collection": None,
    }
    try:
        colls = obj.users_collection
        if colls:
            entry["collection"] = colls[0].name
    except Exception:  # noqa: BLE001
        pass
    try:
        entry["visible"] = not bool(obj.hide_viewport)
    except Exception:  # noqa: BLE001
        entry["visible"] = True
    try:
        entry["selectable"] = not bool(obj.hide_select)
    except Exception:  # noqa: BLE001
        entry["selectable"] = True

    dims = getattr(obj, "dimensions", None)
    loc = getattr(obj, "location", None)
    rot = getattr(obj, "rotation_euler", None)
    sc = getattr(obj, "scale", None)
    from blender_addon.scene.bounds import world_size_m

    wsize = world_size_m(obj)
    entry["dimensions_mm"] = m3_to_mm3([wsize[0], wsize[1], wsize[2]])
    entry["location_mm"] = m3_to_mm3([loc[0], loc[1], loc[2]], ndigits=4) if loc is not None else [0, 0, 0]
    entry["rotation_deg"] = rad3_to_deg3([rot[0], rot[1], rot[2]]) if rot is not None else [0, 0, 0]
    entry["scale"] = [round(float(sc[i]), 5) for i in range(3)] if sc is not None else [1, 1, 1]

    if obj.type == "MESH":
        entry["mesh"] = _mesh_stats(obj)
        entry["modifiers"] = [_modifier_params(m) for m in obj.modifiers]
        try:
            entry["materials"] = [m.name for m in obj.data.materials if m]
        except Exception:  # noqa: BLE001
            entry["materials"] = []
    elif obj.type == "CAMERA":
        entry["lens_mm"] = round(getattr(obj.data, "lens", 50.0), 2)
    elif obj.type == "LIGHT":
        entry["energy"] = getattr(obj.data, "energy", 0.0)
    if detail:
        entry["data_name"] = obj.data.name if obj.data else None
    if entry["scale"] == [0.0, 0.0, 0.0]:
        entry["scale"] = [1.0, 1.0, 1.0]
    return entry


def scene_summary() -> Dict[str, Any]:
    import bpy

    ensure_all()
    scene = bpy.context.scene
    objects = list(bpy.data.objects)
    meshes = sum(1 for o in objects if o.type == "MESH")
    lights = sum(1 for o in objects if o.type == "LIGHT")
    cameras = [o for o in objects if o.type == "CAMERA"]
    active = bpy.context.view_layer.objects.active if bpy.context.view_layer else None
    selected = _selected_objects()

    unit = None
    try:
        us = scene.unit_settings
        unit = {"system": us.system, "scale": us.scale_length,
                "length_unit": us.length_unit, "mass_unit": us.mass_unit}
    except Exception:  # noqa: BLE001
        unit = None
    file_path = bpy.data.filepath or None

    collections = []
    try:
        for coll in bpy.data.collections:
            collections.append(coll.name)
    except Exception:  # noqa: BLE001
        pass

    return {
        "object_count": len(objects),
        "mesh_objects": meshes,
        "light_count": lights,
        "active_object": {"id": ensure_obj_id(active), "name": active.name} if active else None,
        "selected_objects": [{"id": ensure_obj_id(o), "name": o.name} for o in selected],
        "collections": collections,
        "camera": {"id": ensure_obj_id(scene.camera), "name": scene.camera.name} if scene.camera else None,
        "unit_settings": unit,
        "file_path": file_path,
        "engine": scene.render.engine,
        "mode": bpy.context.mode if bpy.context else None,
    }


def _selected_objects() -> list:
    import bpy

    try:
        sel = list(bpy.context.selected_objects)
        if sel:
            return sel
    except Exception:  # noqa: BLE001
        pass
    out = []
    try:
        for o in bpy.context.view_layer.objects:
            if o.select_get():
                out.append(o)
    except Exception:  # noqa: BLE001
        pass
    return out


def all_objects() -> List[Dict[str, Any]]:
    import bpy

    ensure_all()
    return [object_entry(o) for o in bpy.data.objects]


def selection_payload() -> Dict[str, Any]:
    objs = _selected_objects()
    return {"objects": [{"id": ensure_obj_id(o), "name": o.name, "type": o.type} for o in objs]}
