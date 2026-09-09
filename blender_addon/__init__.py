"""Blender Harness add-on.

An AI-native harness that lets a natural-language agent inspect and edit the
current Blender scene through structured tools, with screenshot feedback and
full checkpoint/undo history.

The add-on is deliberately dependency-free: it only uses Blender's own bpy and
the Python standard library (including a minimal built-in WebSocket client), so
it installs cleanly via Edit > Preferences > Add-ons > Install.

Module layout mirrors the top-level spec:
    blender_addon/
        scene/      unit conversion, stable object ids, scene serialization
        history/    checkpoint (.blend copies) + journal
        transport/  websocket client + main-thread bridge
        tools/      structured tool handlers + registry
        ui/         N-panel UI (AI Harness)
"""

bl_info = {
    "name": "Blender Harness",
    "author": "Blender Harness contributors",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > AI Harness",
    "description": "AI-native Blender harness: structured tools, screenshots, history & undo for LLM agents.",
    "category": "Development",
}

from blender_addon import version as _version  # noqa: E402,F401  (registered below)
from blender_addon.ui import register as _register_ui  # noqa: E402
from blender_addon.ui import unregister as _unregister_ui  # noqa: E402


def register() -> None:
    _register_ui()


def unregister() -> None:
    _unregister_ui()
