"""World-space bounds helpers (pure python — no mathutils)."""

from __future__ import annotations

from typing import Any, Tuple

from blender_addon.scene.vec import apply_matrix_rows, euler_rad_matrix, mul


def world_bounds(obj: Any) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Axis-aligned world bounds (metres) computed from the object's local
    bounding box plus its location/rotation/scale. Modifier expansion is
    ignored (matches Blender's own dimension-less fast path)."""
    loc = (obj.location[0], obj.location[1], obj.location[2])
    rot = [float(x) for x in obj.rotation_euler]
    scl = [float(x) for x in obj.scale]
    m = euler_rad_matrix(rot[0], rot[1], rot[2])
    mins = [1e18, 1e18, 1e18]
    maxs = [-1e18, -1e18, -1e18]
    for c in obj.bound_box:
        w = apply_matrix_rows(mul((c[0], c[1], c[2]), scl), m)
        for i in range(3):
            v = loc[i] + w[i]
            if v < mins[i]:
                mins[i] = v
            if v > maxs[i]:
                maxs[i] = v
    if mins[0] > maxs[0]:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    return (mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2])


def world_center(obj: Any) -> Tuple[float, float, float]:
    lo, hi = world_bounds(obj)
    return ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0)


def world_size_m(obj: Any) -> Tuple[float, float, float]:
    lo, hi = world_bounds(obj)
    return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
