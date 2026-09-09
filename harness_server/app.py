"""FastAPI application for the Blender Harness server.

Serves:
  * WS  /ws/blender                    — the Blender add-on connects here
  * REST /api/*                        — Web UI endpoints (polling model)
  * GET  /media/*                      — rendered screenshots
  * GET  /                             — built web UI (web_ui/dist) if present
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from harness_server import APP_NAME, __version__
from harness_server.agent.loop import start_run, stop_run
from harness_server.api import history_payload, refresh_scene_cache, scene_payload
from harness_server.config import Settings
from harness_server.log import configure_logging, recent_lines
from harness_server.schemas.run import RunRequest
from harness_server.state import AppState
from harness_server.tools.registry import all_tool_specs
from harness_server.ws_blender import blender_ws, undo_or_restore

log = logging.getLogger("harness.app")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIST = PROJECT_ROOT / "web_ui" / "dist"

_landing = """<!doctype html><html><head><meta charset="utf-8"><title>Blender Harness</title>
<style>body{background:#0f1115;color:#d7dde6;font-family:ui-sans-serif,system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{max-width:520px;text-align:center}h1{color:#4f8cff}code{background:#1c2230;padding:2px 6px;border-radius:4px}a{color:#4f8cff}</style></head>
<body><div class="card"><h1>Blender Harness</h1>
<p>The backend is running. Launch the Web UI with <code>cd web_ui && npm run dev</code> and open <a href="http://127.0.0.1:5173">http://127.0.0.1:5173</a>,<br>
or build it once (<code>cd web_ui && npm run build</code>) and reload this page to serve it here.</p>
<p>API: <code>/api/status</code> &nbsp;·&nbsp; <code>/api/tools</code> &nbsp;·&nbsp; <code>/api/history</code><br>
Blender add-on connects to <code>ws://127.0.0.1:9876/ws/blender</code></p></div></body></html>"""


def _public_run(detail: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in detail.items() if not k.startswith("_")}


def create_app(settings: Optional[Settings] = None, state: Optional[AppState] = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    configure_logging(settings.log_level, str(settings.logs_dir() / "harness.log"), debug=settings.debug)
    if state is None:
        state = AppState(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        state.close()

    app = FastAPI(title=APP_NAME, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False
    )

    media_root = settings.media_dir()
    app.mount("/media", StaticFiles(directory=str(media_root)), name="media")

    # ------------------------------------------------------------- blender ws
    @app.websocket("/ws/blender")
    async def ws_blender_endpoint(websocket: WebSocket) -> None:
        await blender_ws(websocket, state)

    # ----------------------------------------------------------------- status
    @app.get("/api/status")
    async def api_status() -> Dict[str, Any]:
        return state.status_payload()

    @app.get("/api/tools")
    async def api_tools() -> list:
        specs = all_tool_specs(include_exec=settings.allow_execute_python)
        out = []
        for s in specs:
            out.append({"name": s.name, "description": s.description, "category": s.category,
                        "risk": s.risk, "timeout_default_s": s.timeout_default_s, "parameters": s.parameters})
        return sorted(out, key=lambda t: (t["category"], t["name"]))

    @app.get("/api/logs/latest")
    async def api_logs(n: int = 200) -> Dict[str, Any]:
        return {"lines": recent_lines(max(1, min(n, 500)))}

    # -------------------------------------------------------------------- run
    @app.post("/api/run")
    async def api_run(body: RunRequest = Body(...)) -> Dict[str, Any]:
        try:
            run_id = start_run(state, body.prompt, source="web",
                               reference_images=body.reference_images)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"run_id": run_id}

    @app.get("/api/runs/{run_id}")
    async def api_run_detail(run_id: str) -> Dict[str, Any]:
        rec = state.runs.get(run_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found (server restarted?)")
        return _public_run(rec.detail)

    @app.post("/api/runs/{run_id}/stop")
    async def api_run_stop(run_id: str) -> Dict[str, Any]:
        ok = stop_run(state, run_id)
        return {"ok": ok}

    # ---------------------------------------------------------------- history
    @app.get("/api/history")
    async def api_history() -> list:
        return history_payload(state)

    @app.post("/api/history/{history_id}/undo")
    async def api_history_undo(history_id: int) -> Dict[str, Any]:
        return await undo_or_restore(state, history_id, mode="undo")

    @app.post("/api/history/{history_id}/restore")
    async def api_history_restore(history_id: int) -> Dict[str, Any]:
        return await undo_or_restore(state, history_id, mode="restore")

    # ----------------------------------------------------------------- scene
    @app.get("/api/scene")
    async def api_scene() -> Dict[str, Any]:
        return scene_payload(state)

    @app.post("/api/scene/refresh")
    async def api_scene_refresh() -> Dict[str, Any]:
        try:
            return await refresh_scene_cache(state)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Blender scene refresh failed: {exc}")

    # ------------------------------------------------------------------- root
    @app.get("/", include_in_schema=False)
    async def root():
        index = WEB_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse(_landing)

    return app
