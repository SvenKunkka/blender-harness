"""WebSocket endpoint that the Blender add-on connects to.

Message flow:
  addon -> server : hello | pong | tool_result | event | run_prompt | server_action
  server -> addon : hello_ack | ping | tool_call | server_action_result | run_update | run_finished

The add-on implements the client side (reconnect + heartbeat); the server only
needs to answer pings and keep the connection registered.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:  # pragma: no cover
    from harness_server.state import AppState

log = logging.getLogger("harness.ws")

HEARTBEAT_INTERVAL_S = 10.0


class BlenderSession:
    def __init__(self, state: "AppState", websocket: WebSocket, session_id: str) -> None:
        self.state = state
        self.ws = websocket
        self.session_id = session_id
        self.connected_at = state.now()
        self.last_seen = self.connected_at
        self.blender_version: Optional[str] = None
        self.addon_version: Optional[str] = None
        self.file_path: Optional[str] = None
        self.pending: Dict[str, asyncio.Future] = {}
        self._closed = False

    def touch(self) -> None:
        self.last_seen = self.state.now()

    async def send(self, payload: Dict[str, Any]) -> None:
        if self._closed:
            raise ConnectionError("websocket closed")
        await self.ws.send_json(payload)

    def close_pending(self, reason: str) -> None:
        for fut in self.pending.values():
            if not fut.done():
                fut.set_result({"type": "tool_result", "ok": False, "error": f"DISCONNECTED: {reason}",
                                "result": {}, "duration_ms": None})
        self.pending.clear()


async def _receive_loop(session: BlenderSession) -> None:
    state = session.state
    while True:
        try:
            msg = await session.ws.receive_json()
        except (WebSocketDisconnect, RuntimeError, ValueError) as exc:
            log.info("blender ws closed (%s)", exc.__class__.__name__)
            return
        if not isinstance(msg, dict):
            continue
        session.touch()
        mtype = msg.get("type")
        if mtype == "hello":
            session.blender_version = str(msg.get("blender_version") or "")
            session.addon_version = str(msg.get("addon_version") or "")
            session.file_path = msg.get("file_path")
            log.info("Blender connected: v%s addon v%s file=%s", session.blender_version, session.addon_version, session.file_path)
            await session.send({"type": "hello_ack", "session_id": session.session_id,
                                "server_version": state.settings.version})
        elif mtype == "pong":
            pass  # last_seen already touched
        elif mtype == "tool_result":
            rid = msg.get("request_id")
            fut = session.pending.pop(rid, None) if rid else None
            if fut and not fut.done():
                fut.set_result(msg)
            else:
                log.warning("tool_result for unknown request_id %s", rid)
        elif mtype == "event":
            state.recent_events.append({"ts": state.now(), **(msg.get("data") or {})})
            state.recent_events = state.recent_events[-50:]
        elif mtype == "run_prompt":
            await _handle_run_prompt(state, session, msg)
        elif mtype == "server_action":
            await _handle_server_action(state, session, msg)
        else:
            log.debug("ignored blender message type=%s", mtype)


async def _handle_run_prompt(state: "AppState", session: BlenderSession, msg: Dict[str, Any]) -> None:
    from harness_server.agent.loop import start_run

    prompt = str(msg.get("prompt") or "").strip()
    if not prompt:
        await session.send({"type": "run_prompt_result", "ok": False, "error": "empty prompt"})
        return
    try:
        run_id = start_run(state, prompt, source="blender-panel", blender_session=session)
        await session.send({"type": "run_prompt_result", "ok": True, "run_id": run_id})
    except Exception as exc:  # pragma: no cover
        log.exception("start_run failed")
        await session.send({"type": "run_prompt_result", "ok": False, "error": str(exc)})


async def _handle_server_action(state: "AppState", session: BlenderSession, msg: Dict[str, Any]) -> None:
    action = msg.get("action")
    args = msg.get("args") or {}
    rid = msg.get("request_id")
    try:
        result = await run_server_action(state, action, args, session)
    except Exception as exc:  # pragma: no cover
        log.exception("server_action %s failed", action)
        result = {"ok": False, "error": str(exc)}
    if rid:
        try:
            await session.send({"type": "server_action_result", "request_id": rid, **result})
        except Exception:  # pragma: no cover
            pass


async def run_server_action(state: "AppState", action: str, args: Dict[str, Any],
                            session: Optional[BlenderSession] = None) -> Dict[str, Any]:
    """Handles button presses coming from the add-on N-panel."""
    from harness_server.tools.bridge import execute_tool

    if action == "status":
        return {"ok": True, "status": state.status_payload()}
    if action == "history":
        entries = state.store.list_all(limit=50)
        return {"ok": True, "history": entries}
    if action == "checkpoint":
        label = str(args.get("label") or f"manual {state.now()}")
        res = await execute_tool(state, "create_checkpoint", {"label": label})
        return res
    if action == "undo_step":
        history_id = args.get("history_id")
        entries = state.store.list_all(limit=50)
        if history_id is None and entries:
            # newest entry that is still 'done'
            for e in entries:
                if e["status"] == "done":
                    history_id = e["id"]
                    break
        if history_id is None:
            return {"ok": False, "error": "no history to undo"}
        return await undo_or_restore(state, int(history_id), mode="undo")
    if action == "restore_step":
        history_id = int(args.get("history_id", 0))
        if not history_id:
            return {"ok": False, "error": "history_id required"}
        return await undo_or_restore(state, history_id, mode="restore")
    if action == "screenshot":
        res = await execute_tool(state, "capture_viewport", {})
        if res.get("ok"):
            from harness_server.media import MediaStore

            media = MediaStore(state.settings)
            urls = media.save_capture("manual", "viewport", res["result"])
            res["result"]["urls"] = urls
        return res
    if action == "scene":
        from harness_server.api import refresh_scene_cache

        payload = await refresh_scene_cache(state)
        return {"ok": True, "scene": payload}
    if action == "stop_run":
        run_id = args.get("run_id")
        if run_id and run_id in state.runs:
            rec = state.runs[run_id]
            rec.cancelled = True
            if rec.task and not rec.task.done():
                rec.task.cancel()
            return {"ok": True, "run_id": run_id}
        return {"ok": False, "error": "run not found"}
    return {"ok": False, "error": f"unknown server_action: {action}"}


async def undo_or_restore(state: "AppState", history_id: int, mode: str = "undo") -> Dict[str, Any]:
    """Undo: restore the checkpoint captured before the AI step.
    Restore: reload the checkpoint captured after the AI step (redo)."""
    from harness_server.tools.bridge import execute_tool

    entry = state.store.get(history_id)
    if entry is None:
        return {"ok": False, "error": f"history entry {history_id} not found"}
    ckpt = entry.get("checkpoint_after" if mode == "restore" else "checkpoint_before")
    if not ckpt:
        return {"ok": False, "error": f"step has no {'after' if mode == 'restore' else 'before'} checkpoint — nothing to restore"}
    res = await execute_tool(state, "restore_checkpoint", {"checkpoint_id": ckpt})
    if res.get("ok"):
        state.store.update_status(history_id, "done" if mode == "restore" else "undone")
        state.scene_cache = type(state.scene_cache)()
        return {"ok": True, "message": f"{'Restored' if mode == 'restore' else 'Undid'} step v{entry['seq']}", "history_id": history_id}
    return {"ok": False, "error": res.get("error") or "checkpoint restore failed", "history_id": history_id}


async def _ping_loop(session: BlenderSession) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)
        try:
            await session.send({"type": "ping", "ts": session.state.now()})
        except Exception:  # pragma: no cover
            return


async def blender_ws(websocket: WebSocket, state: "AppState") -> None:
    await websocket.accept()
    session = BlenderSession(state, websocket, session_id=f"bl-{id(websocket)}")
    if state.blender is not None and state.blender is not session:
        old = state.blender
        old._closed = True
        old.close_pending("replaced by new connection")
        try:
            await old.ws.close(code=4000, reason="replaced")
        except Exception:  # pragma: no cover
            pass
    state.blender = session
    log.info("blender ws session %s registered", session.session_id)
    recv_task = asyncio.create_task(_receive_loop(session))
    ping_task = asyncio.create_task(_ping_loop(session))
    try:
        done, pending = await asyncio.wait({recv_task, ping_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    finally:
        if state.blender is session:
            state.blender = None
        session._closed = True
        session.close_pending("connection lost")
        log.info("blender ws session %s unregistered", session.session_id)
