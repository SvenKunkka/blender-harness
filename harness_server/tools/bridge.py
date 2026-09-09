"""Bridge: executes a tool by sending a WebSocket request to the connected
Blender add-on and awaiting its correlated result."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

from harness_server.tools.registry import spec_by_name

if TYPE_CHECKING:  # pragma: no cover
    from harness_server.state import AppState

log = logging.getLogger("harness.bridge")

BLENDER_NOT_CONNECTED = "BLENDER_NOT_CONNECTED"


class ToolError(Exception):
    def __init__(self, message: str, code: str = "TOOL_ERROR") -> None:
        super().__init__(message)
        self.code = code


async def execute_tool(state: "AppState", name: str, arguments: Dict[str, Any],
                       timeout_s: Optional[float] = None) -> Dict[str, Any]:
    """Send one tool call to Blender and wait for the result.

    Returns {"ok": bool, "result": dict, "error": str|None, "duration_ms": float|None,
             "cancelled": bool}
    """
    spec = spec_by_name(name)
    timeout = timeout_s if timeout_s else spec.timeout_default_s
    start = time.monotonic()

    session = state.blender
    if session is None:
        return {
            "ok": False,
            "error": BLENDER_NOT_CONNECTED,
            "result": {},
            "duration_ms": None,
            "hint": "Enable the 'Blender Harness' add-on in Blender and press Connect in the AI Harness panel.",
        }

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    session.pending[request_id] = fut
    try:
        await session.send(
            {
                "type": "tool_call",
                "request_id": request_id,
                "tool": {"name": name, "arguments": arguments or {}},
                "timeout_ms": int(timeout * 1000),
            }
        )
    except Exception as exc:  # pragma: no cover - socket issues
        session.pending.pop(request_id, None)
        return {"ok": False, "error": f"SEND_FAILED: {exc}", "result": {}, "duration_ms": None}

    try:
        payload = await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        session.pending.pop(request_id, None)
        log.warning("tool %s timed out after %.1fs", name, timeout)
        return {"ok": False, "error": f"TOOL_TIMEOUT after {timeout:.0f}s", "result": {}, "duration_ms": None}
    except asyncio.CancelledError:
        session.pending.pop(request_id, None)
        raise
    finally:
        session.pending.pop(request_id, None)

    duration = (time.monotonic() - start) * 1000.0
    if payload.get("type") == "tool_result":
        ok = bool(payload.get("ok", True))
        return {
            "ok": ok,
            "result": payload.get("result") or {},
            "error": payload.get("error"),
            "duration_ms": duration,
        }
    return {"ok": False, "error": f"UNEXPECTED_REPLY: {payload}", "result": {}, "duration_ms": duration}
