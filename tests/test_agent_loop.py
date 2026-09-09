"""Agent-loop tests: full run with a fake LLM + fake Blender session."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional


class FakeBlender:
    """Pretends to be the Blender WebSocket session (server side view)."""

    def __init__(self, responder) -> None:
        self.responder = responder
        self.pending: Dict[str, asyncio.Future] = {}
        self.last_seen = "now"
        self.file_path = None
        self.blender_version = "5.1"
        self.addon_version = "0.1.0"

    async def send(self, payload: Dict[str, Any]) -> None:
        rid = payload.get("request_id")
        fut = self.pending.get(rid)
        if fut is None:
            return
        tool = payload.get("tool") or {}
        name = tool.get("name", "")
        args = tool.get("arguments") or {}
        ok, result, error = self.responder(name, args)
        if not fut.done():
            fut.set_result({"type": "tool_result", "request_id": rid, "ok": ok,
                            "result": result, "error": error, "duration_ms": 1.0})


def _scene_entry(oid: str, name: str):
    return {"id": oid, "name": name, "type": "MESH", "parent": None, "collection": "Collection",
            "visible": True, "selectable": True, "dimensions_mm": [100, 100, 100],
            "location_mm": [0, 0, 0], "rotation_deg": [0, 0, 0], "scale": [1, 1, 1],
            "mesh": {"vertices": 8, "edges": 12, "faces": 6, "triangles": 12},
            "modifiers": [], "materials": []}


def _responder(name: str, args: Dict[str, Any]):
    if name == "create_checkpoint":
        return True, {"checkpoint_id": f"ckpt_{args.get('label', 'x')[:8]}"}, None
    if name == "get_scene_summary":
        return True, {"scene": {"object_count": 1, "active_object": {"id": "obj_00001", "name": "Demo"},
                                "selected_objects": [], "collections": ["Collection"], "camera": None,
                                "light_count": 0, "unit_settings": {"system": "METRIC", "scale": 1.0},
                                "file_path": None}}, None
    if name == "get_objects":
        return True, {"objects": [_scene_entry("obj_00001", "Demo")]}, None
    if name == "create_cube":
        dims = args.get("dimensions_mm", [100, 100, 100])
        return True, {"object_id": "obj_00001", "name": args.get("name", "Demo"), "type": "MESH",
                      "dimensions_mm": dims}, None
    if name == "capture_viewport" or name == "capture_object_views":
        return True, {"images": []}, None
    return False, {}, f"unexpected tool {name}"


class FakeProvider:
    """Replaces ChatProvider inside the loop with scripted responses."""

    def __init__(self, responses: List[Dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls = 0

    @staticmethod
    def parse_tool_calls(message):
        return ChatProvider_parse(message)

    async def chat(self, messages, tools=None, temperature=0.2):
        self.calls += 1
        if not self.responses:
            return {"message": {"content": "finished"}, "finish_reason": "stop"}
        return self.responses.pop(0)

    async def close(self) -> None:
        pass


def ChatProvider_parse(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        out.append({"id": tc.get("id"), "name": fn.get("name"),
                    "arguments": json.loads(fn.get("arguments") or "{}")})
    return out


async def _run_prompt(state, prompt: str, responses: List[Dict[str, Any]]) -> dict:
    from harness_server.agent.loop import start_run

    state.blender = FakeBlender(_responder)
    monkey = _patch_provider(responses)
    try:
        run_id = start_run(state, prompt)
        rec = state.runs[run_id]
        try:
            await asyncio.wait_for(rec.task, timeout=10)
        except asyncio.CancelledError:
            pass
        return rec.detail
    finally:
        monkey.restore()


def _patch_provider(responses):
    import harness_server.agent.loop as loop_mod

    original = loop_mod.ChatProvider

    class _Fake(original):
        def __init__(self, *a, **k):
            self._responses = list(responses)
            self.calls = 0

        async def chat(self, messages, tools=None, temperature=0.2):
            self.calls += 1
            if not self._responses:
                return {"message": {"content": "nothing more"}, "finish_reason": "stop"}
            return self._responses.pop(0)

        async def close(self) -> None:
            pass

    loop_mod.ChatProvider = _Fake

    class Restore:
        def restore(self):
            loop_mod.ChatProvider = original

    return Restore()


async def test_full_agent_run_creates_history_and_checkpoints(server_state):
    responses = [
        {"message": {"content": None, "tool_calls": [{"id": "c1", "type": "function",
                      "function": {"name": "create_cube",
                                   "arguments": '{"name": "Demo", "dimensions_mm": [100, 100, 100]}'}}]},
         "finish_reason": "tool_calls"},
        {"message": {"content": "Created Demo\nDimensions: 100 × 100 × 100 mm\nChanges:\n• Created Demo cube"}, "finish_reason": "stop"},
    ]
    detail = await _run_prompt(server_state, "Create a 100mm demo cube.", responses)

    assert detail["status"] == "finished", detail.get("error")
    assert detail["checkpoint_before"] is not None
    assert detail["checkpoint_after"] is not None
    assert detail["summary"] and "Demo" in detail["summary"]

    tools = [e["tool"] for e in detail["tool_log"]]
    assert "create_cube" in tools
    assert detail["plan"], "plan steps should be produced"
    assert any(s["label"] == "Create / edit geometry" for s in detail["plan"])

    entries = server_state.store.list_all()
    assert len(entries) == 1
    assert entries[0]["status"] == "done"
    assert entries[0]["checkpoint_before"] == detail["checkpoint_before"]


async def test_read_only_run_writes_no_history(server_state):
    responses = [
        {"message": {"content": None, "tool_calls": [{"id": "c1", "type": "function",
                      "function": {"name": "get_scene_summary", "arguments": "{}"}}]},
         "finish_reason": "tool_calls"},
        {"message": {"content": "The scene contains 1 object."}, "finish_reason": "stop"},
    ]
    detail = await _run_prompt(server_state, "How many objects are in the scene?", responses)
    assert detail["status"] == "finished"
    assert len(server_state.store.list_all()) == 0  # no mutation -> no AI step


async def test_run_can_be_stopped(server_state):
    import harness_server.agent.loop as loop_mod

    original = loop_mod.ChatProvider

    class HangingProvider(original):
        def __init__(self, *a, **k):
            pass

        @staticmethod
        def parse_tool_calls(message):
            return ChatProvider_parse(message)

        async def chat(self, messages, tools=None, temperature=0.2):
            await asyncio.sleep(60)

        async def close(self):
            pass

    loop_mod.ChatProvider = HangingProvider
    server_state.blender = FakeBlender(_responder)
    try:
        from harness_server.agent.loop import start_run, stop_run

        run_id = start_run(server_state, "long task")
        rec = server_state.runs[run_id]
        await asyncio.sleep(0.1)
        assert rec.detail["status"] in ("queued", "running")
        stop_run(server_state, run_id)
        try:
            await asyncio.wait_for(rec.task, timeout=5)
        except asyncio.CancelledError:
            pass
        assert rec.detail["status"] == "stopped"
    finally:
        loop_mod.ChatProvider = original
