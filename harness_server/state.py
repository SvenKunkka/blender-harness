"""Central runtime state for the harness server."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from harness_server.config import Settings
from harness_server.log import configure_logging
from harness_server.memory.store import HistoryStore

log = logging.getLogger("harness.state")

if TYPE_CHECKING:  # pragma: no cover
    from harness_server.ws_blender import BlenderSession


@dataclass
class RunRecord:
    detail: Dict[str, Any]
    task: Optional[asyncio.Task] = None
    cancelled: bool = False
    history_id: Optional[int] = None


@dataclass
class SceneCache:
    summary: Optional[Dict[str, Any]] = None
    objects: List[Dict[str, Any]] = field(default_factory=list)
    object_details: Dict[str, Any] = field(default_factory=dict)
    fetched_at: Optional[str] = None


class AppState:
    """One instance per server process. Holds the Blender connection, active
    agent runs, the scene cache and the history store."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.started_at = datetime.now().isoformat(timespec="seconds")
        configure_logging(settings.log_level, str(settings.logs_dir() / "harness.log"), debug=settings.debug)
        self.store = HistoryStore(settings.data_dir)

        self.blender: Optional["BlenderSession"] = None
        self.blender_changed = threading.Event()
        self.exec_gate = asyncio.Lock()  # serialises Blender mutations

        self.runs: Dict[str, RunRecord] = {}
        self.scene_cache = SceneCache()
        self.scene_lock = asyncio.Lock()
        self.recent_events: List[Dict[str, Any]] = []
        self._close_events: List[asyncio.Event] = []

    # -- helpers -----------------------------------------------------------
    def now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def status_payload(self) -> Dict[str, Any]:
        s = self.settings
        blender = None
        if self.blender is not None:
            blender = {
                "connected": True,
                "last_seen": self.blender.last_seen,
                "file_path": self.blender.file_path,
                "blender_version": self.blender.blender_version,
                "addon_version": self.blender.addon_version,
            }
        else:
            blender = {"connected": False, "last_seen": None, "file_path": None, "blender_version": None, "addon_version": None}
        return {
            "server": {"version": s.version, "uptime_s": self.uptime_s(), "started_at": self.started_at},
            "blender": blender,
            "llm": {
                "chat": {"configured": s.chat_configured, "model": s.chat_model, "base_url": s.base_url},
                "vision": {"configured": s.vision_configured, "model": s.vision_model or "", "base_url": s.vision_base_url},
            },
            "limits": {"max_agent_steps": s.max_agent_steps, "max_vision_refinements": s.max_vision_refinements},
            "debug": s.debug,
            "allow_execute_python": s.allow_execute_python,
        }

    def uptime_s(self) -> float:
        from datetime import datetime as dt

        return (dt.fromisoformat(self.started_at) - dt.now()).total_seconds() * -1

    def close(self) -> None:
        for ev in list(self._close_events):
            ev.set()
        try:
            self.store.close()
        except Exception:  # pragma: no cover
            pass


_state_holder: Optional[AppState] = None
_state_holder_lock = threading.Lock()


def get_state() -> AppState:
    """Process-wide singleton used by FastAPI route handlers."""
    global _state_holder
    if _state_holder is None:
        with _state_holder_lock:
            if _state_holder is None:
                _state_holder = AppState(Settings())
    return _state_holder


def set_state(state: AppState) -> None:  # for tests / app factory
    global _state_holder
    _state_holder = state
