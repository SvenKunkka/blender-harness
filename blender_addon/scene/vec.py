"""Tiny pure-python 3D vector helpers (no mathutils dependency).

Keeps the add-on unit-testable outside Blender while staying exact enough for
the operations that use it (framing cameras, apply-transform math).
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

V3 = Tuple[float, float, float]


def add(a: Sequence[float], b: Sequence[float]) -> V3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Sequence[float], b: Sequence[float]) -> V3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Sequence[float], s: float) -> V3:
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Sequence[float], b: Sequence[float]) -> V3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a: Sequence[float]) -> float:
    return math.sqrt(dot(a, a))


def normalized(a: Sequence[float]) -> V3:
    ln = length(a)
    if ln < 1e-12:
        return (0.0, 0.0, 1.0)
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def mul(a: Sequence[float], b: Sequence[float]) -> V3:
    """Element-wise multiply."""
    return (a[0] * b[0], a[1] * b[1], a[2] * b[2])


def euler_rad_matrix(rx: float, ry: float, rz: float):
    """Rotation matrix (3x3, rows) applying R = Rx * Ry * Rz to column vectors,
    i.e. v' = M @ v with global-axis order matching Blender's 'XYZ' euler when
    applied as Rx*Ry*Rz. Used only for our own geometry math."""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    # Rx
    # Ry
    # Rz
    # M = Rz @ Ry @ Rx (columns)
    m00 = cy * cz
    m01 = sx * sy * cz - cx * sz
    m02 = cx * sy * cz + sx * sz
    m10 = cy * sz
    m11 = sx * sy * sz + cx * cz
    m12 = cx * sy * sz - sx * cz
    m20 = -sy
    m21 = sx * cy
    m22 = cx * cy
    return (m00, m01, m02), (m10, m11, m12), (m20, m21, m22)


def apply_matrix_rows(v: Sequence[float], m) -> V3:
    r0, r1, r2 = m
    return (r0[0] * v[0] + r0[1] * v[1] + r0[2] * v[2],
            r1[0] * v[0] + r1[1] * v[1] + r1[2] * v[2],
            r2[0] * v[0] + r2[1] * v[1] + r2[2] * v[2])
