"""Mesh tools: primitive creation via procedural (from_pydata) builders, edit
mode control, mesh stats and bounding boxes.

Primitives are generated in pure Python (mm -> m at build time) instead of
calling bpy.ops.mesh.primitive_*_add, so they work headless and deterministically.
"""

from __future__ import annotations

import math

import bpy

from blender_addon.scene.bounds import world_bounds as _world_bounds  # noqa: F401 (re-exported for product tools)
from blender_addon.scene.objid import ensure_obj_id, resolve_object
from blender_addon.scene.units import mm3_to_m3, m3_to_mm3, round_list
from blender_addon.scene.vec import apply_matrix_rows, euler_rad_matrix, mul
from blender_addon.tools._registry import ToolFailure, register

# ---------------------------------------------------------------------------
# geometry generators (outputs in mm)
# ---------------------------------------------------------------------------


def _cube_mesh(w_mm: float, d_mm: float, h_mm: float):
    hx, hy, hz = w_mm / 2.0, d_mm / 2.0, h_mm / 2.0
    v = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    f = [
        [0, 3, 2, 1],  # bottom (-z)
        [4, 5, 6, 7],  # top (+z)
        [1, 2, 6, 5],  # +x
        [0, 4, 7, 3],  # -x
        [3, 7, 6, 2],  # +y
        [0, 1, 5, 4],  # -y
    ]
    return v, f


def _plane_mesh(w_mm: float, d_mm: float):
    hx, hy = w_mm / 2.0, d_mm / 2.0
    v = [(-hx, -hy, 0.0), (hx, -hy, 0.0), (hx, hy, 0.0), (-hx, hy, 0.0)]
    f = [[0, 1, 2, 3]]
    return v, f


def _cylinder_mesh(radius_mm: float, depth_mm: float, n: int):
    r, h = radius_mm, depth_mm / 2.0
    v = []
    for k in range(n):
        a = 2.0 * math.pi * k / n
        v.append((r * math.cos(a), r * math.sin(a), -h))
    for k in range(n):
        a = 2.0 * math.pi * k / n
        v.append((r * math.cos(a), r * math.sin(a), h))
    v.append((0.0, 0.0, -h))   # bottom center  2n
    v.append((0.0, 0.0, h))    # top center     2n+1
    f = []
    for k in range(n):
        nxt = (k + 1) % n
        f.append([k, nxt, nxt + n, k + n])  # side quads, outward
    f.append([2 * n] + list(range(n - 1, -1, -1)))  # bottom cap (-z)
    f.append([2 * n + 1] + list(range(n, 2 * n)))   # top cap (+z)
    return v, f


def _uv_sphere_mesh(radius_mm: float, segments: int, rings: int):
    r = radius_mm
    v = [(0.0, 0.0, r)]
    for j in range(1, rings + 1):
        alpha = math.pi / 2.0 - math.pi * j / (rings + 1.0)
        z = r * math.sin(alpha)
        rr = r * math.cos(alpha)
        for k in range(segments):
            a = 2.0 * math.pi * k / segments
            v.append((rr * math.cos(a), rr * math.sin(a), z))
    v.append((0.0, 0.0, -r))
    f = []
    # top fan
    for k in range(segments):
        nxt = (k + 1) % segments
        f.append([0, k + 1, nxt + 1])
    # middle quads between ring j and j+1
    for j in range(rings - 1):
        for k in range(segments):
            nxt = (k + 1) % segments
            a = 1 + j * segments + k
            b = 1 + j * segments + nxt
            c = 1 + (j + 1) * segments + nxt
            d = 1 + (j + 1) * segments + k
            f.append([a, b, c, d])
    # bottom fan
    last = 1 + (rings - 1) * segments
    bottom = 1 + rings * segments
    for k in range(segments):
        nxt = (k + 1) % segments
        f.append([bottom, last + nxt, last + k])
    return v, f


def rounded_rect_profile(w_mm: float, d_mm: float, r_mm: float, segments: int):
    """CCW profile of a rounded rectangle in mm, interior on the left."""
    w, d = w_mm, d_mm
    r = min(r_mm, min(w, d) / 2.0 - 0.001)
    if r <= 0:
        # plain rectangle (no rounding)
        hx, hy = w / 2.0, d / 2.0
        return [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    hx, hy = w / 2.0 - r, d / 2.0 - r

    def arc(cx, cy, a0, a1):
        pts = []
        steps = max(2, segments)
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts

    pts = []
    pts.append((hx, -d / 2.0))                       # bottom straight start
    pts.extend(arc(hx, -hy, -math.pi / 2.0, 0.0))    # BR arc
    pts.append((w / 2.0, hy))                        # right straight end
    pts.extend(arc(hx, hy, 0.0, math.pi / 2.0))      # TR arc
    pts.append((-hx, d / 2.0))                       # top straight end
    pts.extend(arc(-hx, hy, math.pi / 2.0, math.pi))  # TL arc
    pts.append((-w / 2.0, -hy))                      # left straight end
    pts.extend(arc(-hx, -hy, math.pi, 3.0 * math.pi / 2.0))  # BL arc
    return pts


def rounded_prism_mesh(w_mm: float, d_mm: float, h_mm: float, r_mm: float, segments: int = 6):
    """Solid rounded box (extruded rounded rectangle), bottom flat at -h/2."""
    profile = rounded_rect_profile(w_mm, d_mm, r_mm, segments)
    n = len(profile)
    hz = h_mm / 2.0
    v = [(x, y, -hz) for (x, y) in profile] + [(x, y, hz) for (x, y) in profile]
    f = []
    for i in range(n):
        j = (i + 1) % n
        f.append([i, j, j + n, i + n])  # side quad, outward (profile CCW)
    f.append(list(range(n - 1, -1, -1)))  # bottom cap (-z)
    f.append(list(range(n, 2 * n)))       # top cap (+z)
    return v, f


def spheroid_mesh(l_mm: float, w_mm: float, h_mm: float, segments: int = 48, rings: int = 24):
    """Symmetric mouse-volume approximation: axis-scaled sphere, bottom at z=0."""
    base_v, base_f = _uv_sphere_mesh(1.0, segments, rings)
    v = []
    for (x, y, z) in base_v:
        # unit sphere in z in [-1,1]; map so bottom sits at z=0 and top at h
        zz = h_mm * (z + 1.0) / 2.0
        v.append((x * l_mm / 2.0, y * w_mm / 2.0, zz))
    return v, base_f


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _link(obj, select: bool = True) -> None:
    if not obj.users_collection:
        bpy.context.scene.collection.objects.link(obj)
    if select:
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except Exception:  # noqa: BLE001
            pass
        try:
            obj.select_set(True)
        except Exception:  # noqa: BLE001
            pass
        if bpy.context.view_layer is not None:
            bpy.context.view_layer.objects.active = obj


def create_mesh_object(name: str, verts_mm, faces, location_mm=None) -> object:
    """verts_mm: list of [x, y, z] in mm. Returns the new Blender object."""
    me = bpy.data.meshes.new(name or "BH_Mesh")
    verts_m = [(float(x) / 1000.0, float(y) / 1000.0, float(z) / 1000.0) for (x, y, z) in verts_mm]
    me.from_pydata(verts_m, [], [list(f) for f in faces])
    me.update()
    obj = bpy.data.objects.new(name or "BH_Mesh", me)
    _link(obj)
    if location_mm:
        loc = mm3_to_m3([float(x) for x in location_mm])
        obj.location = (loc[0], loc[1], loc[2])
    return obj


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@register("create_cube", category="mesh", risk="mutating")
def tool_create_cube(args: dict) -> dict:
    dims = args.get("dimensions_mm") or [100.0, 100.0, 100.0]
    w, d, h = (float(dims[0]), float(dims[1]), float(dims[2]))
    name = args.get("name") or "Cube"
    v, f = _cube_mesh(w, d, h)
    obj = create_mesh_object(name, v, f, args.get("location_mm"))
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "type": "MESH",
            "dimensions_mm": [w, d, h]}


@register("create_uv_sphere", category="mesh", risk="mutating")
def tool_create_uv_sphere(args: dict) -> dict:
    r = float(args.get("radius_mm", 50.0))
    seg = int(args.get("segments", 32))
    rings = int(args.get("rings", 16))
    if r <= 0:
        raise ToolFailure("radius_mm must be positive")
    v, f = _uv_sphere_mesh(r, seg, rings)
    obj = create_mesh_object(args.get("name") or "Sphere", v, f, args.get("location_mm"))
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "type": "MESH",
            "radius_mm": r}


@register("create_cylinder", category="mesh", risk="mutating")
def tool_create_cylinder(args: dict) -> dict:
    r = float(args.get("radius_mm", 50.0))
    depth = float(args.get("depth_mm", 100.0))
    n = max(3, int(args.get("vertices", 32)))
    if r <= 0 or depth <= 0:
        raise ToolFailure("radius_mm and depth_mm must be positive")
    v, f = _cylinder_mesh(r, depth, n)
    obj = create_mesh_object(args.get("name") or "Cylinder", v, f, args.get("location_mm"))
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "type": "MESH"}


@register("create_plane", category="mesh", risk="mutating")
def tool_create_plane(args: dict) -> dict:
    size = args.get("size_mm") or [100.0, 100.0]
    w, d = float(size[0]), float(size[1])
    v, f = _plane_mesh(w, d)
    obj = create_mesh_object(args.get("name") or "Plane", v, f, args.get("location_mm"))
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "type": "MESH"}


@register("create_mesh_from_vertices", category="mesh", risk="mutating")
def tool_create_mesh_from_vertices(args: dict) -> dict:
    verts = args.get("vertices_mm")
    if not verts or len(verts) < 1:
        raise ToolFailure("vertices_mm must contain at least one [x, y, z] vertex")
    verts_mm = [(float(x[0]), float(x[1]), float(x[2])) for x in verts]
    faces = args.get("faces") or []
    obj = create_mesh_object(args.get("name") or "FromVertices", verts_mm, faces)
    return {"object_id": ensure_obj_id(obj), "name": obj.name, "type": "MESH",
            "vertices": len(verts_mm), "faces": len(faces)}


@register("enter_edit_mode", category="mesh", risk="safe")
def tool_enter_edit_mode(args: dict) -> dict:
    obj = resolve_object(args)
    if obj.type != "MESH":
        raise ToolFailure("enter_edit_mode works on MESH objects only")
    try:
        bpy.ops.object.mode_set(mode="EDIT")
    except RuntimeError as exc:
        raise ToolFailure(f"could not enter edit mode: {exc}") from exc
    return {"mode": "EDIT", "object_id": ensure_obj_id(obj)}


@register("exit_edit_mode", category="mesh", risk="safe")
def tool_exit_edit_mode(args: dict) -> dict:
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except RuntimeError as exc:
        raise ToolFailure(f"could not leave edit mode: {exc}") from exc
    return {"mode": "OBJECT"}


@register("get_mesh_stats", category="mesh", risk="safe")
def tool_get_mesh_stats(args: dict) -> dict:
    obj = resolve_object(args)
    if obj.type != "MESH" or obj.data is None:
        raise ToolFailure(f"'{obj.name}' is not a mesh object")
    me = obj.data
    tris = sum(max(0, len(p.vertices) - 2) for p in me.polygons)
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "vertices": len(me.vertices), "edges": len(me.edges),
            "faces": len(me.polygons), "triangles": tris}


def _world_bounds_doc(obj):
    """Kept for backward import compatibility."""
    return _world_bounds(obj)


@register("get_bounding_box", category="mesh", risk="safe")
def tool_get_bounding_box(args: dict) -> dict:
    obj = resolve_object(args)
    mins, maxs = _world_bounds(obj)
    bmin = [round(m * 1000.0, 3) for m in mins]
    bmax = [round(m * 1000.0, 3) for m in maxs]
    center = [round((mins[i] + maxs[i]) / 2.0 * 1000.0, 3) for i in range(3)]
    size = [round((maxs[i] - mins[i]) * 1000.0, 3) for i in range(3)]
    diag = math.sqrt(sum(s * s for s in size))
    return {"object_id": ensure_obj_id(obj), "name": obj.name,
            "bbox_min_mm": bmin, "bbox_max_mm": bmax, "center_mm": center,
            "size_mm": size, "diagonal_mm": round(diag, 3)}
