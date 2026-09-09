"""Pure-python quaternion helpers used to aim cameras (no mathutils)."""

from __future__ import annotations

import math
from typing import Sequence, Tuple

from blender_addon.scene.vec import V3, add, cross, dot, length, mul, normalized, scale, sub

# ---------------------------------------------------------------------------
# rotation matrix -> quaternion (Shepperd's method), returns (w, x, y, z)
# ---------------------------------------------------------------------------


def rotmat3_to_quat(m) -> Tuple[float, float, float, float]:
    m00, m01, m02 = m[0]
    m10, m11, m12 = m[1]
    m20, m21, m22 = m[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    return (w / n, x / n, y / n, z / n)


def quat_rotate(q: Sequence[float], v: Sequence[float]) -> V3:
    """Rotate vector v by unit quaternion q=(w,x,y,z) using Hamilton product."""
    w, x, y, z = q
    t = cross((x, y, z), v)
    t = scale(t, 2.0)
    return add(v, add(scale(cross((x, y, z), t), w), cross(t, (x, y, z))))


def quat_mul(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float, float, float]:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


# ---------------------------------------------------------------------------
# camera aiming: build a quaternion whose local -Z axis points along `forward`.
# ---------------------------------------------------------------------------


def quat_look_at(forward: Sequence[float], up_hint: Sequence[float] = (0.0, 0.0, 1.0)) -> Tuple[float, float, float, float]:
    f = normalized(forward)
    up = up_hint
    # avoid the degenerate case where forward is (anti-)parallel to the up hint
    if abs(dot(f, up)) > 0.98:
        up = (1.0, 0.0, 0.0) if abs(f[0]) < 0.7 else (0.0, 1.0, 0.0)
    right = normalized(cross(f, up))
    cam_up = cross(right, f)
    # columns: local +X -> right, local +Y -> cam_up, local +Z -> -f
    m = ((right[0], cam_up[0], -f[0]),
         (right[1], cam_up[1], -f[1]),
         (right[2], cam_up[2], -f[2]))
    return rotmat3_to_quat(m)


def dirs_from_quat(q: Sequence[float]):
    """Return (right, up, forward) world vectors of a camera with quaternion q."""
    right = quat_rotate(q, (1.0, 0.0, 0.0))
    up = quat_rotate(q, (0.0, 1.0, 0.0))
    forward = quat_rotate(q, (0.0, 0.0, -1.0))
    return right, up, forward
