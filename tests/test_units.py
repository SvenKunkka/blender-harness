"""Unit conversion tests: everything the AI touches is mm / degrees."""

from __future__ import annotations

import math

from blender_addon.scene.units import (
    deg_to_rad,
    m3_to_mm3,
    m_to_mm,
    mm3_to_m3,
    mm_to_m,
    rad_to_deg,
)


def test_mm_m_roundtrip():
    assert mm_to_m(1000) == 1.0
    assert m_to_mm(1.0) == 1000.0
    assert abs(mm_to_m(2.5) - 0.0025) < 1e-12
    for v in (0.5, 325.0, 18.0, 0.1, 123456.7):
        assert abs(m_to_mm(mm_to_m(v)) - v) < 1e-9


def test_vec3_conversions():
    assert mm3_to_m3([325, 145, 18]) == [0.325, 0.145, 0.018]
    assert m3_to_mm3([0.325, 0.145, 0.018]) == [325.0, 145.0, 18.0]


def test_degrees_radians():
    assert abs(deg_to_rad(180) - math.pi) < 1e-12
    assert abs(rad_to_deg(math.pi) - 180.0) < 1e-9
