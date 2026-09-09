"""Render / vision tools: PNG screenshots from several angles via Blender's
EEVEE renderer (bpy.ops.render.render) with a temporary camera.

Output images are base64-encoded and returned to the harness server, which
persists them and feeds them to the vision reviewer.
"""

from __future__ import annotations

import base64
import os
import tempfile
import time

import bpy

from blender_addon.scene.objid import ensure_obj_id
from blender_addon.scene.quat import quat_look_at
from blender_addon.scene.units import mm3_to_m3
from blender_addon.scene.vec import add, mul, scale as vscale, sub
from blender_addon.tools._registry import ToolFailure, register

_ANGLES = {
    "front": (0.0, -1.0, 0.0),
    "back": (0.0, 1.0, 0.0),
    "left": (1.0, 0.0, 0.0),
    "right": (-1.0, 0.0, 0.0),
    "top": (0.0, 0.0, 1.0),
    "bottom": (0.0, 0.0, -1.0),
    "perspective": (0.7071, -0.7071, 0.5),
}


def _collect_targets(obj_ids) -> list:
    if obj_ids:
        objs = []
        for oid in obj_ids:
            for o in bpy.data.objects:
                if str(o.get("bh_id")) == oid:
                    objs.append(o)
                    break
        if objs:
            return objs
    return [o for o in bpy.data.objects if o.type in {"MESH", "CURVE", "SURFACE", "META", "FONT", "LATTICE"}]


def _scene_bounds(objs) -> tuple:
    """Aggregate world bounds in metres (pure math, modifier-less)."""
    from blender_addon.scene.vec import apply_matrix_rows, euler_rad_matrix

    mins = [1e18] * 3
    maxs = [-1e18] * 3
    for o in objs:
        loc = (o.location[0], o.location[1], o.location[2])
        rot = [float(x) for x in o.rotation_euler]
        scl = [float(x) for x in o.scale]
        m = euler_rad_matrix(rot[0], rot[1], rot[2])
        for c in o.bound_box:
            w = apply_matrix_rows(mul((c[0], c[1], c[2]), scl), m)
            for i in range(3):
                v = loc[i] + w[i]
                if v < mins[i]:
                    mins[i] = v
                if v > maxs[i]:
                    maxs[i] = v
    if mins[0] > maxs[0]:  # nothing to frame
        mins = [0.0, 0.0, 0.0]
        maxs = [0.1, 0.1, 0.1]
    return mins, maxs


def _set_eevee(scene) -> None:
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            return
        except Exception:  # noqa: BLE001
            continue
    raise ToolFailure("no EEVEE engine available for screenshots")


def _render_png(scene, filepath: str, width: int, height: int) -> None:
    if os.path.exists(filepath):
        os.remove(filepath)
    render = scene.render
    old = (render.resolution_x, render.resolution_y, render.resolution_percentage,
           render.image_settings.file_format, render.filepath)
    render.resolution_x = width
    render.resolution_y = height
    render.resolution_percentage = 100
    render.image_settings.file_format = "PNG"
    render.filepath = filepath
    try:
        try:
            bpy.ops.render.render({"scene": scene}, write_still=True)
        except Exception:  # noqa: BLE001
            bpy.ops.render.render(write_still=True)
    finally:
        (render.resolution_x, render.resolution_y, render.resolution_percentage,
         render.image_settings.file_format, render.filepath) = old
    if not os.path.exists(filepath):
        # Blender appends the extension when none was given
        candidate = filepath + ".png"
        if os.path.exists(candidate):
            os.replace(candidate, filepath)
        else:
            raise ToolFailure("render produced no output file")


def _b64(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _render_angles(obj_ids, angles, width, height) -> dict:
    import math

    scene = bpy.context.scene
    prev_engine = scene.render.engine
    _set_eevee(scene)
    objs = _collect_targets(obj_ids)
    mins, maxs = _scene_bounds(objs)
    center = tuple((mins[i] + maxs[i]) / 2.0 for i in range(3))
    diag = sum((maxs[i] - mins[i]) ** 2 for i in range(3)) ** 0.5

    fov = 0.85  # approx vertical fov for a 50mm full-frame camera
    dist = max(diag / (2.0 * math.tan(fov / 2.0)), 0.05) * 1.4 + 0.15

    tmp_dir = tempfile.gettempdir()
    shots_dir = os.path.join(tmp_dir, "blender_harness_shots")
    os.makedirs(shots_dir, exist_ok=True)

    # camera management
    created_cam = None
    prev_camera = scene.camera
    cam = prev_camera
    if cam is None or cam.type != "CAMERA":
        cam_data = bpy.data.cameras.new("BH_ShotCam")
        cam = bpy.data.objects.new("BH_ShotCam", cam_data)
        scene.collection.objects.link(cam)
        created_cam = cam
    prev_lens = cam.data.lens
    cam.data.lens = 50.0
    scene.camera = cam
    stamp = int(time.time() * 1000)
    images = []
    try:
        for angle_name in angles:
            direction = _ANGLES.get(angle_name)
            if direction is None:
                direction = (1.0, -1.0, 0.7)
            ln = (direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2) ** 0.5
            dir_n = (direction[0] / ln, direction[1] / ln, direction[2] / ln)
            pos = add(center, vscale(dir_n, dist))
            cam.location = (pos[0], pos[1], pos[2])
            q = quat_look_at(sub(center, pos))
            cam.rotation_mode = "QUATERNION"
            cam.rotation_quaternion = (q[0], q[1], q[2], q[3])
            filepath = os.path.join(shots_dir, f"shot_{angle_name}_{stamp}.png")
            _render_png(scene, filepath, width, height)
            images.append({"angle": angle_name, "width": width, "height": height,
                           "path": filepath, "image_b64": _b64(filepath)})
    finally:
        scene.render.engine = prev_engine
        scene.camera = prev_camera
        cam.data.lens = prev_lens
        if created_cam is not None:
            try:
                bpy.data.objects.remove(created_cam, do_unlink=True)
            except Exception:  # noqa: BLE001
                pass
    return {"images": images, "count": len(images), "angles": list(angles)}


@register("capture_viewport", category="render", risk="safe")
def tool_capture_viewport(args: dict) -> dict:
    obj_ids = args.get("object_ids") or None
    width = int(args.get("width", 1024))
    height = int(args.get("height", 768))
    out = _render_angles(obj_ids, ["perspective"], width, height)
    img = out["images"][0]
    return {"image_b64": img["image_b64"], "width": img["width"], "height": img["height"],
            "path": img["path"], "angle": "perspective"}


@register("render_image", category="render", risk="safe")
def tool_render_image(args: dict) -> dict:
    obj_ids = args.get("object_ids") or None
    width = int(args.get("width", 1024))
    height = int(args.get("height", 768))
    out = _render_angles(obj_ids, ["perspective"], width, height)
    img = out["images"][0]
    return {"image_b64": img["image_b64"], "width": img["width"], "height": img["height"],
            "path": img["path"], "angle": "perspective"}


@register("render_multi_angle", category="render", risk="safe")
def tool_render_multi_angle(args: dict) -> dict:
    obj_ids = args.get("object_ids") or None
    angles = args.get("angles") or ["front", "back", "left", "right", "top", "perspective"]
    width = int(args.get("width", 1024))
    height = int(args.get("height", 768))
    return _render_angles(obj_ids, angles, width, height)


@register("capture_object_views", category="render", risk="safe")
def tool_capture_object_views(args: dict) -> dict:
    obj_ids = args.get("object_ids") or None
    width = int(args.get("width", 640))
    height = int(args.get("height", 480))
    angles = ["front", "back", "left", "right", "top", "perspective"]
    return _render_angles(obj_ids, angles, width, height)
