"""Bridge: keeps the add-on connected to the harness server and marshals work
onto Blender's main thread.

    socket thread  --reads JSON-->  inbound queue  --timer pump (main thread)-->
       executes tool handlers, updates UI state            |
                                                           v
    socket thread  <--writes JSON--  outbound queue  <---- responses/requests

This is the classic Blender async pattern: only the timer pump may touch bpy.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from blender_addon.settings import addon_version
from blender_addon.transport.wsclient import WsClient, WsError

log = logging.getLogger("bh.bridge")

WS_PATH = "/ws/blender"
HELLO_TIMEOUT_S = 8.0
PUMP_INTERVAL_S = 0.05


def _now_iso() -> str:
    return time.strftime("%H:%M:%S")


class BhBridge:
    """Singleton owned by the add-on. See module docstring for the threading
    model. All attributes below are safe to read from the UI thread."""

    instance: Optional["BhBridge"] = None

    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 9876
        self.running = False
        self.status = "disconnected"  # disconnected|connecting|connected|error
        self.last_error: Optional[str] = None
        self.connected_at: Optional[str] = None
        self.server_version: Optional[str] = None
        self.file_path: Optional[str] = None

        self._thread: Optional[threading.Thread] = None
        self._ws: Optional[WsClient] = None
        self._inbound: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._outbound: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._lock = threading.Lock()

        # UI-facing caches refreshed by the pump
        self.log_tail: List[str] = []
        self.history_rows: List[Dict[str, Any]] = []
        self.last_prompt_result: Optional[str] = None
        self.last_run_event: Optional[str] = None
        self.pending_ui: Dict[str, Dict[str, Any]] = {}
        self._timer_registered = False

    # ------------------------------------------------------------ lifecycle
    def configure(self, host: str, port: int) -> None:
        with self._lock:
            self.host = host
            self.port = int(port)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.status = "connecting"
        self.last_error = None
        self._thread = threading.Thread(target=self._worker, daemon=True, name="bh-ws")
        self._thread.start()
        self.ensure_pump()

    def stop(self) -> None:
        self.running = False
        self.status = "disconnected"
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass
        th = self._thread
        if th is not None and th.is_alive():
            th.join(timeout=2.0)
        self._thread = None
        self.log("Stopped")

    def is_connected(self) -> bool:
        return self.status == "connected" and self.running

    # ------------------------------------------------------------ logging
    def log(self, text: str) -> None:
        line = f"{_now_iso()}  {text}"
        self.log_tail.append(line)
        self.log_tail = self.log_tail[-80:]
        log.info("%s", text)

    # ------------------------------------------------------------- sending
    def send(self, payload: Dict[str, Any], expect_reply: bool = False) -> Optional[str]:
        """Queue a JSON message to the server. Returns request_id when
        expect_reply is set (result will be delivered to the UI thread)."""
        request_id = None
        if expect_reply:
            request_id = f"ui_{uuid.uuid4().hex[:10]}"
            payload["request_id"] = request_id
            self.pending_ui[request_id] = {"created": time.time()}
        self._outbound.put(payload)
        return request_id

    def send_tool_call(self, name: str, args: Dict[str, Any]) -> None:
        self.send({"type": "tool_call", "request_id": f"req_{uuid.uuid4().hex[:10]}",
                   "tool": {"name": name, "arguments": args or {}}})

    def run_prompt(self, prompt: str) -> str:
        return self.send({"type": "run_prompt", "prompt": prompt}, expect_reply=True) or ""

    def server_action(self, action: str, args: Optional[Dict[str, Any]] = None) -> Optional[str]:
        return self.send({"type": "server_action", "action": action, "args": args or {}}, expect_reply=True)

    # -------------------------------------------------------------- worker
    def _worker(self) -> None:
        backoff = 1.0
        while self.running:
            try:
                self._connect_once()
                backoff = 1.0
                self._read_until_closed()
            except Exception as exc:  # noqa: BLE001
                if self.running:
                    self.status = "error"
                    self.last_error = str(exc)[:300]
                    self.log(f"connection error: {self.last_error}")
            finally:
                self.status = "disconnected"
                if self.running:
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, 15.0)

    def _connect_once(self) -> None:
        ws = WsClient(self.host, self.port, WS_PATH)
        self._ws = ws
        ws.connect(timeout=5.0)
        ws.on_text = self._on_text
        self.status = "connected"
        self.connected_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"connected to ws://{self.host}:{self.port}{WS_PATH}")
        # announce ourselves
        self.send({
            "type": "hello",
            "app": "blender",
            "addon_version": addon_version(),
            "blender_version": self._blender_version(),
            "file_path": self._file_path(),
        })

    @staticmethod
    def _blender_version() -> str:
        try:
            import bpy

            return ".".join(str(v) for v in bpy.app.version)
        except Exception:  # noqa: BLE001
            return "unknown"

    @staticmethod
    def _file_path() -> Optional[str]:
        try:
            import bpy

            return bpy.data.filepath or None
        except Exception:  # noqa: BLE001
            return None

    def _on_text(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        mtype = msg.get("type")
        if mtype == "ping":
            self._outbound.put({"type": "pong", "ts": msg.get("ts")})
        elif mtype in ("tool_call", "server_action_result", "run_prompt_result",
                       "run_update", "run_finished", "run_prompt_ack"):
            self._inbound.put(msg)
        elif mtype == "hello_ack":
            self.server_version = msg.get("server_version")
            self.file_path = self._file_path()
            self.log(f"server {self.server_version} acknowledged the connection")

    def _read_until_closed(self) -> None:
        ws = self._ws
        if ws is None:
            return
        last_sent = time.monotonic()
        try:
            while self.running and ws is not None and not ws.closed:
                self._flush_outbound()
                if time.monotonic() - last_sent > 12.0:
                    try:
                        ws.send_text(json.dumps({"type": "pong", "ts": time.time()}))
                        last_sent = time.monotonic()
                    except Exception:  # noqa: BLE001
                        break
                try:
                    ws.pump_once(0.25)
                except WsError:
                    break
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:  # noqa: BLE001
                    pass
            if self.running:
                self.log("connection closed — reconnecting…")
                self.status = "disconnected"

    def _flush_outbound(self) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            return
        while True:
            try:
                payload = self._outbound.get_nowait()
            except queue.Empty:
                return
            try:
                ws.send_text(json.dumps(payload))
            except Exception as exc:  # noqa: BLE001
                log.warning("send failed: %s", exc)
                return

    # ------------------------------------------------------- main-thread pump
    def ensure_pump(self) -> None:
        try:
            import bpy

            if not self._timer_registered:
                bpy.app.timers.register(self._pump, persistent=True)
                self._timer_registered = True
        except Exception as exc:  # noqa: BLE001 - headless / tests
            log.warning("timer registration failed: %s", exc)

    def _pump(self) -> Optional[float]:
        """Runs on the main thread. Executes tool calls and updates UI state."""
        if not self.running:
            return PUMP_INTERVAL_S
        drained = 0
        while drained < 20:
            try:
                msg = self._inbound.get_nowait()
            except queue.Empty:
                break
            drained += 1
            try:
                self._handle_inbound(msg)
            except Exception as exc:  # noqa: BLE001
                log.exception("inbound handling failed: %s", exc)
        self._gc_pending()
        return PUMP_INTERVAL_S

    def _handle_inbound(self, msg: Dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "tool_call":
            tool = msg.get("tool") or {}
            name = tool.get("name", "?")
            args = tool.get("arguments") or {}
            request_id = msg.get("request_id")
            started = time.monotonic()
            self.log(f"← tool_call {name}")
            try:
                from blender_addon.tools import dispatch

                ok, result_or_error = dispatch(name, args)
            except Exception as exc:  # noqa: BLE001
                ok, result_or_error = False, f"{exc.__class__.__name__}: {exc}"
            duration_ms = (time.monotonic() - started) * 1000.0
            if ok:
                reply = {"type": "tool_result", "request_id": request_id, "ok": True,
                         "result": result_or_error, "error": None,
                         "duration_ms": round(duration_ms, 1)}
                self.log(f"→ {name} OK ({duration_ms:.0f} ms)")
            else:
                reply = {"type": "tool_result", "request_id": request_id, "ok": False,
                         "result": {}, "error": str(result_or_error),
                         "duration_ms": round(duration_ms, 1)}
                self.log(f"→ {name} ERROR: {result_or_error}")
            self._outbound.put(reply)
        elif mtype == "server_action_result":
            rid = msg.get("request_id")
            if rid:
                self.pending_ui.pop(rid, None)
            action = (msg.get("action") or "")
            if action == "history":
                rows = msg.get("history") or []
                self.history_rows = rows
                self.log(f"history refreshed: {len(rows)} step(s)")
            elif msg.get("ok") is False:
                self.log(f"server action failed: {msg.get('error')}")
            elif action == "undo_step":
                self.log("undo step: " + str(msg.get("message", "done")))
                self.server_action("history")
            elif action == "restore_step":
                self.log("restore step: " + str(msg.get("message", "done")))
                self.server_action("history")
            elif action == "scene":
                scene = msg.get("scene") or {}
                self.scene_info = scene
                count = (scene.get("summary") or {}).get("object_count")
                self.log(f"scene refreshed: {count or '?'} object(s)")
            elif action == "checkpoint":
                result = msg.get("result") or {}
                cid = result.get("checkpoint_id")
                self.log(f"checkpoint created: {cid or '?'}")
            elif action == "screenshot":
                urls = (msg.get("result") or {}).get("urls") or []
                self.log("screenshot taken" + (f": {urls[-1]}" if urls else ""))
            else:
                self.log(f"server_action {action} -> ok={msg.get('ok')}")
        elif mtype == "run_prompt_result":
            rid = msg.get("request_id")
            if rid:
                self.pending_ui.pop(rid, None)
            if msg.get("ok"):
                self.last_prompt_result = f"run started: {msg.get('run_id')}"
            else:
                self.last_prompt_result = f"run rejected: {msg.get('error')}"
            self.log(str(self.last_prompt_result))
        elif mtype == "run_update":
            tool = msg.get("tool")
            ok = msg.get("ok")
            if tool:
                self.log(f"agent tool {tool} {'OK' if ok else 'ERROR: ' + str(msg.get('error'))}")
            elif msg.get("event") == "finished":
                self.log(f"agent run {msg.get('run_id')} finished")
                self.server_action("history")
        elif mtype == "run_finished":
            self.last_run_event = str(msg.get("summary") or msg.get("error") or "finished")
            self.log(f"run finished: {self.last_run_event[:200]}")
        elif mtype == "run_prompt_ack":
            pass
        else:
            self.log(f"unhandled server message: {mtype}")

    def _gc_pending(self) -> None:
        now = time.time()
        stale = [rid for rid, p in self.pending_ui.items() if now - p["created"] > 60]
        for rid in stale:
            self.pending_ui.pop(rid, None)


def bridge() -> BhBridge:
    if BhBridge.instance is None:
        BhBridge.instance = BhBridge()
    return BhBridge.instance
