"""REST + WebSocket endpoint tests for the harness FastAPI app."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harness_server.config import Settings
from harness_server.state import AppState


@pytest.fixture()
def client(tmp_env):
    settings = Settings(_env_file=None, data_dir=Path(str(tmp_env)), ai_model=None, ai_base_url=None)
    state = AppState(settings)
    from harness_server.app import create_app

    app = create_app(settings=settings, state=state)
    with TestClient(app) as c:
        yield c, state, settings
    state.close()


def test_status_and_tools(client):
    c, _state, settings = client
    status = c.get("/api/status").json()
    assert status["server"]["version"]
    assert status["blender"]["connected"] is False
    assert status["llm"]["chat"]["configured"] is False

    tools = c.get("/api/tools").json()
    assert len(tools) > 50
    by_name = {t["name"]: t for t in tools}
    assert "execute_blender_python" not in by_name  # disabled by default
    assert "parameters" in by_name["set_dimensions"]
    assert by_name["create_cube"]["category"] == "mesh"


def test_run_requires_llm_configuration(client):
    c, _state, _settings = client
    resp = c.post("/api/run", json={"prompt": "create a cube"})
    assert resp.status_code == 400
    assert "LLM not configured" in resp.json()["detail"]


def test_history_and_scene_empty_states(client):
    c, _state, _settings = client
    assert c.get("/api/history").json() == []
    scene = c.get("/api/scene").json()
    assert scene["summary"] is None and scene["objects"] == []

    logs = c.get("/api/logs/latest?n=5").json()
    assert "lines" in logs


def test_unknown_run_is_404(client):
    c, _state, _settings = client
    assert c.get("/api/runs/does_not_exist").status_code == 404


def test_undo_without_checkpoint_is_clean_error(client):
    c, _state, _settings = client
    resp = c.post("/api/history/1/undo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False


def test_blender_websocket_hello(client):
    c, _state, _settings = client
    with c.websocket_connect("/ws/blender") as ws:
        # the server acks each hello it receives
        ws.send_json({"type": "hello", "app": "blender", "addon_version": "0.1.0",
                      "blender_version": "5.1.0", "file_path": "/tmp/x.blend"})
        ack = ws.receive_json()
        assert ack["type"] == "hello_ack"
        assert ack["server_version"]
        session_id = ack["session_id"]

        ws.send_json({"type": "hello", "app": "blender", "addon_version": "0.1.0",
                      "blender_version": "5.1.0", "file_path": None})
        ack2 = ws.receive_json()
        assert ack2["type"] == "hello_ack"
        assert ack2["session_id"] == session_id
        # status now reports a connected Blender
        status = c.get("/api/status").json()
        assert status["blender"]["connected"] is True
