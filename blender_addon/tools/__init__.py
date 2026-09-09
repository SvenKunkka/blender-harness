"""Structured tool handlers. See blender_addon/tools/_registry.py for the
registration mechanism and `dispatch`."

All lengths in handler signatures are millimetres, all angles degrees — the
conversion to Blender metres/radians happens at the tool boundary.
"""

from blender_addon.tools import file_tools  # noqa: F401
from blender_addon.tools import history_tools  # noqa: F401
from blender_addon.tools import material_tools  # noqa: F401
from blender_addon.tools import mesh_tools  # noqa: F401
from blender_addon.tools import modifier_tools  # noqa: F401
from blender_addon.tools import product_tools  # noqa: F401
from blender_addon.tools import render_tools  # noqa: F401
from blender_addon.tools import scene_tools  # noqa: F401
from blender_addon.tools import transform_tools  # noqa: F401
from blender_addon.tools import camera_tools  # noqa: F401
from blender_addon.tools import exec_tools  # noqa: F401
from blender_addon.tools._registry import HANDLERS, META, ToolFailure, dispatch, known_tools, register  # noqa: F401

__all__ = ["dispatch", "known_tools", "register", "HANDLERS", "META", "ToolFailure"]
