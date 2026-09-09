"""Unit system. The AI always talks millimetres and degrees; Blender stores
metres and radians. All conversion lives here so the model never converts."""

from __future__ import annotations

from typing import List, Sequence, Tuple, Union

MM_PER_M = 1000.0
RAD_PER_DEG = 3.141592653589793 / 180.0


def mm_to_m(v: float) -> float:
    return v / MM_PER_M


def m_to_mm(v: float) -> float:
    return v * MM_PER_M


def deg_to_rad(v: float) -> float:
    return v * RAD_PER_DEG


def rad_to_deg(v: float) -> float:
    return v / RAD_PER_DEG


def mm3_to_m3(v: Sequence[float]) -> List[float]:
    return [mm_to_m(float(x)) for x in v]


def m3_to_mm3(v: Sequence[float], ndigits: int = 3) -> List[float]:
    return [round(m_to_mm(float(x)), ndigits) for x in v]


def deg3_to_rad3(v: Sequence[float]) -> List[float]:
    return [deg_to_rad(float(x)) for x in v]


def rad3_to_deg3(v: Sequence[float], ndigits: int = 2) -> List[float]:
    return [round(rad_to_deg(float(x)), ndigits) for x in v]


def as_vec3(v: Union[Sequence[float], None], default=(0.0, 0.0, 0.0)) -> Tuple[float, float, float]:
    if v is None:
        return (float(default[0]), float(default[1]), float(default[2]))
    return (float(v[0]), float(v[1]), float(v[2]))


def round_list(v: Sequence[float], ndigits: int = 3) -> List[float]:
    return [round(float(x), ndigits) for x in v]
