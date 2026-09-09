"""Camera tools: create cameras, aim them, position them, frame the viewport."""

from __future__ import annotations

import bpy

from blender_addon.scene.objid import describe_object, ensure_obj_id, resolve_object
from blender_addon.scene.quat import quat_look_at
from blender_addon.scene.units import mm3_to_m3, m3_to_mm3
from blender_addon.scene.vec import sub
from blender_addon.tools._registry import ToolFailure, register


def aim_camera(cam_obj, target_vec_m) -> None:
    """Point cam_obj's -Z axis at target_vec_m (metres)."""
    pos = (cam_obj.location[0], cam_obj.location[1], cam_obj.location[2])
    forward = sub(target_vec_m, pos)
    ln = (forward[0] ** 2 + forward[1] ** 2 + forward[2] ** 2) ** 0.5
    if ln < 1e-9:
        raise ToolFailure("camera and target are at the same position")
    q = quat_look_at(forward)
    cam_obj.rotation_mode = "QUATERNION"
    try:
        cam_obj.rotation_quaternion = (q[0], q[1], q[2], q[3])
    except TypeError:
        # extremely defensive: some API bindings require a real Quaternion
        from mathutils import Quaternion  # type: ignore  # noqa: PLC0415

        cam_obj.rotation_quaternion = Quaternion(q)


def _first_camera() -> object:
    for o in bpy.data.objects:
        if o.type == "CAMERA":
            return o
    raise ToolFailure("no camera in the scene — create one first")


def _resolve_camera(args) -> object:
    if args.get("camera_id") or args.get("object_id"):
        try:
            return resolve_object(args)
        except ValueError:
            if not args.get("camera_id"):
                raise
    cam = bpy.context.scene.camera if bpy.context.scene and bpy.context.scene.camera else None
    if cam is None:
        cam = _first_camera()
    return cam


@register("create_camera", category="camera", risk="mutating")
def tool_create_camera(args: dict) -> dict:
    name = args.get("name") or "Camera"
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = 50.0
    obj = bpy.data.objects.new(name, cam_data)
    if not obj.users_collection:
        bpy.context.scene.collection.objects.link(obj)
    if args.get("location_mm"):
        loc = mm3_to_m3([float(x) for x in args["location_mm"]])
        obj.location = (loc[0], loc[1], loc[2])
    if args.get("look_at_object_id"):
        target = resolve_object(args, field="look_at_object_id")
        aim_camera(obj, (target.location[0], target.location[1], target.location[2]))
    obj.select_set(True)
    if bpy.context.view_layer is not None:
        bpy.context.view_layer.objects.active = obj
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "type": "CAMERA"}


@register("set_active_camera", category="camera", risk="safe")
def tool_set_active_camera(args: dict) -> dict:
    obj = resolve_object(args)
    if obj.type != "CAMERA":
        raise ToolFailure(f"'{obj.name}' is not a camera")
    bpy.context.scene.camera = obj
    return {"camera_id": ensure_obj_id(obj), "name": obj.name, "active": True}


@register("frame_selected", category="camera", risk="safe")
def tool_frame_selected(args: dict) -> dict:
    area = None
    for screen in bpy.data.screens:
        for a in screen.areas:
            if a.type == "VIEW_3D":
                area = a
                break
        if area:
            break
    if area is None:
        raise ToolFailure("frame_selected needs an open 3D viewport (not available headless)")
    try:
        with bpy.context.temp_override(area=area, region=area.regions[0]):
            bpy.ops.view3d.view_selected()
    except Exception as exc:  # noqa: BLE001
        raise ToolFailure(f"view_selected failed: {exc}") from exc
    return {"framed": True}


@register("look_at_object", category="camera", risk="mutating")
def tool_look_at_object(args: dict) -> dict:
    cam = _resolve_camera({"camera_id": args.get("camera_id")})
    target = resolve_object(args, field="target_id")
    aim_camera(cam, (target.location[0], target.location[1], target.location[2]))
    return {"camera_id": ensure_obj_id(cam), "name": cam.name,
            "target_id": ensure_obj_id(target), "target": target.name}


@register("set_camera_position", category="camera", risk="mutating")
def tool_set_camera_position(args: dict) -> dict:
    cam = _resolve_camera(args)
    loc = mm3_to_m3([float(x) for x in args["location_mm"]])
    cam.location = (loc[0], loc[1], loc[2])
    return {"camera_id": ensure_obj_id(cam), "name": cam.name,
            "location_mm": m3_to_mm3([cam.location[i] for i in range(3)])}
