import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Make `bpy` available before any test module imports blender_addon.
# Real Blender provides its own bpy; anywhere else we install the mock once.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - depends on environment
    import bpy  # noqa: F401

    _FAKE_BPY = None
except ImportError:
    from tests.mockbpy import install_mock_bpy  # type: ignore

    _FAKE_BPY = install_mock_bpy()


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Isolate all harness data + the add-on data dir under one tmp folder."""
    data = tmp_path / "data"
    monkeypatch.setenv("HARNESS_DATA_DIR", str(data))
    monkeypatch.setenv("BLENDER_HARNESS_DATA_DIR", str(tmp_path / "addon_data"))
    return tmp_path


@pytest.fixture()
def mock_bpy(tmp_env):
    """Return the active bpy (fake in unit tests, real inside Blender) and
    reset the fake to a pristine scene between tests."""
    import bpy

    if _FAKE_BPY is not None:
        from tests.mockbpy import reset_mock_bpy

        reset_mock_bpy(_FAKE_BPY)
    return bpy


@pytest.fixture()
def addon(mock_bpy):
    """Imports the add-on tool layer against the mock bpy module."""
    import blender_addon.history as history
    import blender_addon.scene.objid as objid
    import blender_addon.scene.serializer as serializer
    import blender_addon.scene.units as units
    import blender_addon.tools as tools
    from blender_addon.tools._registry import HANDLERS, dispatch, known_tools, register

    return {
        "bpy": mock_bpy,
        "serializer": serializer,
        "objid": objid,
        "units": units,
        "history": history,
        "tools": tools,
        "HANDLERS": HANDLERS,
        "dispatch": dispatch,
        "known_tools": known_tools,
    }


@pytest.fixture()
def server_state(tmp_env):
    from harness_server.config import Settings
    from harness_server.state import AppState

    settings = Settings(
        _env_file=None,
        data_dir=Path(str(tmp_env)),
        max_agent_steps=20,
        max_vision_refinements=0,
        ai_model="test-model",
        ai_base_url="https://example.invalid/v1",
        ai_api_key="test-key",
    )
    state = AppState(settings)
    yield state
    state.close()
