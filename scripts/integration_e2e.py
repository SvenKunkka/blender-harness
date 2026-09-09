"""End-to-end integration test (host side).

Brings up:
  1. a fake OpenAI-compatible LLM (scripted tool-calling responses),
  2. the real harness server (FastAPI + WebSocket) on 127.0.0.1:9876,
  3. a real headless Blender running the add-on's bridge as its WebSocket client.

Then it posts a prompt to /api/run and verifies the agent loop drives real
geometry creation inside Blender, records a history step with checkpoints, and
finishes cleanly.

Usage:  .venv/bin/python scripts/integration_e2e.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BLENDER_BIN = os.environ.get("BLENDER_BIN", "/Applications/Blender 5.1.app/Contents/MacOS/Blender")
SERVER_PORT = int(os.environ.get("E2E_SERVER_PORT", "9880"))
FAKE_LLM_PORT = int(os.environ.get("E2E_LLM_PORT", "9803"))
BASE = f"http://127.0.0.1:{SERVER_PORT}"
TMP = ROOT / "data" / "e2e"
TMP.mkdir(parents=True, exist_ok=True)

PROMPT = ("Create a rounded box 'IntegrationCase' with dimensions 90 x 60 x 30 mm "
          "and a 6 mm corner radius.")


class _ChatBody(BaseModel):
    model: str = "fake"
    messages: list = []
    tools: list = []


def fake_llm_app() -> object:
    """Returns an ASGI app that scripts two turns of tool calling."""
    import fastapi
    from fastapi.responses import JSONResponse

    app = fastapi.FastAPI()
    turn = {"n": 0}

    @app.post("/v1/chat/completions")
    async def chat(body: _ChatBody):
        turn["n"] += 1
        if turn["n"] == 1:
            msg = {
                "content": None,
                "tool_calls": [{
                    "id": "call_e2e_1", "type": "function",
                    "function": {"name": "create_rounded_box",
                                 "arguments": json.dumps({"name": "IntegrationCase",
                                                          "dimensions_mm": [90, 60, 30],
                                                          "corner_radius_mm": 6})},
                }],
            }
            fr = "tool_calls"
        else:
            msg = {"content": "Created IntegrationCase\nDimensions: 90 × 60 × 30 mm\nChanges:\n• Created IntegrationCase with 6 mm rounded corners"}
            fr = "stop"
        return JSONResponse({"choices": [{"message": msg, "finish_reason": fr}]})

    return app


def start_uvicorn(app, port: int) -> threading.Thread:
    import uvicorn

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    return th


def http_json(path: str, method: str = "GET", body=None, timeout: float = 10):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def wait_http(path: str, timeout: float = 30.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            return http_json(path, timeout=2)
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"server never answered {path}")


def main() -> int:
    os.environ.update({
        "HARNESS_HOST": "127.0.0.1",
        "HARNESS_PORT": str(SERVER_PORT),
        "HARNESS_DATA_DIR": str(TMP),
        "AI_BASE_URL": f"http://127.0.0.1:{FAKE_LLM_PORT}/v1",
        "AI_MODEL": "fake-llm",
        "AI_API_KEY": "x",
        "MAX_VISION_REFINEMENTS": "0",
        "MAX_AGENT_STEPS": "20",
        "BLENDER_HARNESS_DATA_DIR": str(TMP / "blender_data"),
        "LOG_LEVEL": "WARNING",
    })

    # clear old state
    import shutil

    for p in (TMP / "media", TMP / "harness.db", TMP / "logs"):
        if p.exists():
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()

    print("starting fake LLM + harness server…", flush=True)
    start_uvicorn(fake_llm_app(), FAKE_LLM_PORT)
    from harness_server.app import create_app
    from harness_server.config import Settings

    settings = Settings()
    app = create_app(settings=settings)
    start_uvicorn(app, SERVER_PORT)
    wait_http("/api/status")

    print("starting Blender client…", flush=True)
    blender_proc = subprocess.Popen(
        [BLENDER_BIN, "--background", "--factory-startup",
         "--python", str(ROOT / "scripts" / "blender_agent_client.py")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )

    # wait for the add-on to connect
    connected = False
    end = time.time() + 120
    while time.time() < end:
        try:
            status = http_json("/api/status", timeout=2)
            if status["blender"]["connected"]:
                connected = True
                print("Blender connected to harness server ✔", flush=True)
                break
        except Exception:
            pass
        time.sleep(0.5)
    if not connected:
        print("FAIL: Blender never connected", flush=True)
        _kill(blender_proc)
        return 1

    run_id = http_json("/api/run", method="POST",
                       body={"prompt": PROMPT})["run_id"]
    print(f"run started: {run_id}", flush=True)

    # poll until terminal
    final = None
    end = time.time() + 150
    while time.time() < end:
        detail = http_json(f"/api/runs/{run_id}", timeout=5)
        if detail["status"] in ("finished", "failed", "stopped"):
            final = detail
            break
        time.sleep(0.6)

    out = blender_proc.stdout.read() if blender_proc.stdout else ""
    if final is None:
        print("FAIL: run never reached a terminal state", flush=True)
        _kill(blender_proc)
        print(out[-2000:])
        return 1

    tools = [e["tool"] for e in final["tool_log"]]
    ok_tools = all(e["ok"] for e in final["tool_log"])
    history = http_json("/api/history")
    print("run status:", final["status"], flush=True)
    print("tools:", tools, flush=True)
    print("history entries:", len(history), flush=True)

    passed = (
        final["status"] == "finished"
        and "create_rounded_box" in tools
        and ok_tools
        and len(history) >= 1
        and history[0]["status"] == "done"
        and history[0]["checkpoint_before"]
        and history[0]["checkpoint_after"]
        and "IntegrationCase" in (final["summary"] or "")
    )
    print("E2E_RESULT " + ("PASS" if passed else "FAIL"), flush=True)
    if not passed:
        print(json.dumps({"status": final["status"], "tools": tools, "error": final.get("error"),
                          "history": history[:2]}, indent=2), flush=True)
    _kill(blender_proc)
    return 0 if passed else 1


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
