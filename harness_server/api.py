"""Scene-cache helpers shared by the REST API and the add-on panel actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict

from harness_server.tools.bridge import execute_tool

if TYPE_CHECKING:  # pragma: no cover
    from harness_server.state import AppState

log = logging.getLogger("harness.api")


def scene_payload(state: "AppState") -> Dict[str, Any]:
    c = state.scene_cache
    return {
        "summary": c.summary,
        "objects": c.objects,
        "object_details": c.object_details,
        "fetched_at": c.fetched_at,
    }


async def refresh_scene_cache(state: "AppState") -> Dict[str, Any]:
    """Ask Blender for a fresh scene summary + object list and cache it."""
    async with state.scene_lock:
        summary = None
        objects: list = []
        details: Dict[str, Any] = {}
        res = await execute_tool(state, "get_scene_summary", {}, timeout_s=60)
        if res.get("ok"):
            summary = (res["result"] or {}).get("scene") or {}
        else:
            log.warning("scene refresh: get_scene_summary failed: %s", res.get("error"))
        res2 = await execute_tool(state, "get_objects", {}, timeout_s=90)
        if res2.get("ok"):
            objects = (res2["result"] or {}).get("objects") or []
            for obj in objects:
                if isinstance(obj, dict) and obj.get("id"):
                    details[obj["id"]] = obj
        state.scene_cache.summary = summary
        state.scene_cache.objects = objects
        state.scene_cache.object_details = details
        state.scene_cache.fetched_at = state.now()
        return scene_payload(state)


def history_payload(state: "AppState") -> list:
    out = []
    for row in state.store.list_all(limit=200):
        out.append({
            "id": row["id"],
            "seq": row["seq"],
            "run_id": row.get("run_id"),
            "prompt": row["prompt"],
            "timestamp": row["timestamp"],
            "status": row["status"],
            "summary": row.get("summary"),
            "tool_count": row.get("tool_count", 0),
            "screenshot_url": row.get("screenshot_url"),
            "objects_affected": row.get("objects_affected", []),
            "checkpoint_before": row.get("checkpoint_before"),
            "checkpoint_after": row.get("checkpoint_after"),
        })
    return out
