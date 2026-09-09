"""Scene-level tools: reading, selection, naming, duplication, deletion, visibility."""

from __future__ import annotations

import bpy

from blender_addon.scene import serializer
from blender_addon.scene.objid import describe_object, ensure_obj_id, resolve_object
from blender_addon.scene.units import mm3_to_m3
from blender_addon.tools._registry import ToolFailure, register


def _link_and_activate(obj, replace_selection: bool = True) -> None:
    """Link an object to the same collections as the active one (or the scene
    collection), select it and make it active."""
    if not obj.name in bpy.context.scene.collection.objects and not obj.users_collection:
        bpy.context.scene.collection.objects.link(obj)
    view_layer = bpy.context.view_layer
    if replace_selection:
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except Exception:  # noqa: BLE001
            pass
    try:
        obj.select_set(True)
    except Exception:  # noqa: BLE001
        pass
    if view_layer is not None:
        view_layer.objects.active = obj


def _collection_of(obj):
    colls = obj.users_collection
    return colls[0] if colls else bpy.context.scene.collection


@register("get_scene_summary", category="scene", risk="safe")
def tool_get_scene_summary(args: dict) -> dict:
    return {"scene": serializer.scene_summary()}


@register("get_objects", category="scene", risk="safe")
def tool_get_objects(args: dict) -> dict:
    return {"objects": serializer.all_objects()}


@register("get_object_details", category="scene", risk="safe")
def tool_get_object_details(args: dict) -> dict:
    obj = resolve_object(args)
    return {"object": serializer.object_entry(obj)}


@register("get_selected_objects", category="scene", risk="safe")
def tool_get_selected_objects(args: dict) -> dict:
    return serializer.selection_payload()


@register("select_object", category="scene", risk="safe")
def tool_select_object(args: dict) -> dict:
    obj = resolve_object(args)
    replace = args.get("replace", True)
    if replace:
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except Exception:  # noqa: BLE001
            pass
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return {"selected": [describe_object(obj)], "object_id": ensure_obj_id(obj)}


@register("rename_object", category="scene", risk="mutating")
def tool_rename_object(args: dict) -> dict:
    obj = resolve_object(args)
    new_name = str(args.get("new_name") or "").strip()
    if not new_name:
        raise ToolFailure("new_name is required")
    old = obj.name
    obj.name = new_name  # Blender may append .001 on collision
    return {"object_id": ensure_obj_id(obj), "old_name": old, "new_name": obj.name}


@register("duplicate_object", category="scene", risk="mutating")
def tool_duplicate_object(args: dict) -> dict:
    obj = resolve_object(args)
    coll = _collection_of(obj)
    new_obj = obj.copy()
    if obj.data is not None:
        # deep copy the data so edits to the copy don't touch the original
        new_obj.data = obj.data.copy()
    new_obj.name = f"{obj.name}_copy"
    coll.objects.link(new_obj)
    offset = args.get("offset_mm")
    if offset:
        off_m = mm3_to_m3([float(x) for x in offset])
        new_obj.location = tuple(obj.location[i] + off_m[i] for i in range(3))
    _link_and_activate(new_obj, replace_selection=False)
    return {"object_id": ensure_obj_id(new_obj), "name": new_obj.name,
            "source_id": ensure_obj_id(obj)}


@register("delete_object", category="scene", risk="destructive")
def tool_delete_object(args: dict) -> dict:
    obj = resolve_object(args)
    name = obj.name
    oid = ensure_obj_id(obj)
    bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": True, "object_id": oid, "name": name}


@register("hide_object", category="scene", risk="safe")
def tool_hide_object(args: dict) -> dict:
    obj = resolve_object(args)
    obj.hide_viewport = True
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "hidden": True}


@register("show_object", category="scene", risk="safe")
def tool_show_object(args: dict) -> dict:
    obj = resolve_object(args)
    obj.hide_viewport = False
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "hidden": False}
