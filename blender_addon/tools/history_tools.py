"""History tools: scene checkpoints (.blend copies) and undo/restore."""

from __future__ import annotations

from blender_addon.history import create_checkpoint, list_checkpoints, restore_checkpoint, undo_last_ai_action
from blender_addon.tools._registry import ToolFailure, register


@register("create_checkpoint", category="history", risk="safe")
def tool_create_checkpoint(args: dict) -> dict:
    label = str(args.get("label") or "")
    try:
        return create_checkpoint(label)
    except RuntimeError as exc:
        raise ToolFailure(str(exc)) from exc


@register("restore_checkpoint", category="history", risk="destructive")
def tool_restore_checkpoint(args: dict) -> dict:
    ckpt_id = str(args.get("checkpoint_id") or "").strip()
    if not ckpt_id:
        raise ToolFailure("checkpoint_id is required (use list_checkpoints)")
    try:
        return restore_checkpoint(ckpt_id)
    except ValueError as exc:
        raise ToolFailure(str(exc)) from exc


@register("list_checkpoints", category="history", risk="safe")
def tool_list_checkpoints(args: dict) -> dict:
    return {"checkpoints": list_checkpoints()}


@register("undo_last_ai_action", category="history", risk="destructive")
def tool_undo_last_ai_action(args: dict) -> dict:
    try:
        res = undo_last_ai_action()
        return {"undone": True, "checkpoint_id": res.get("restored_checkpoint_id")}
    except ValueError as exc:
        raise ToolFailure(str(exc)) from exc
