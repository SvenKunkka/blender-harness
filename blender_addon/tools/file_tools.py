"""File tools: save the current session or a copy."""

from __future__ import annotations

import os

import bpy

from blender_addon.tools._registry import ToolFailure, register


@register("save_blend", category="file", risk="safe")
def tool_save_blend(args: dict) -> dict:
    path = bpy.data.filepath
    if not path:
        raise ToolFailure("this scene was never saved — use save_blend_as with a full filepath first")
    result = bpy.ops.wm.save_mainfile(filepath=path)
    return {"saved_path": path, "ok": True}


@register("save_blend_as", category="file", risk="safe")
def tool_save_blend_as(args: dict) -> dict:
    filepath = str(args.get("filepath") or "").strip()
    if not filepath:
        raise ToolFailure("filepath is required (absolute path ending in .blend)")
    parent = os.path.dirname(os.path.abspath(filepath))
    if not os.path.isdir(parent):
        raise ToolFailure(f"parent directory does not exist: {parent}")
    if not filepath.lower().endswith(".blend"):
        filepath += ".blend"
    bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True)
    return {"saved_path": filepath, "ok": True, "note": "session file path unchanged (saved as a copy)"}


@register("get_current_file", category="file", risk="safe")
def tool_get_current_file(args: dict) -> dict:
    return {"file_path": bpy.data.filepath or None, "name": os.path.basename(bpy.data.filepath) if bpy.data.filepath else None}
