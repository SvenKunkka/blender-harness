"""History store (SQLite) tests + add-on checkpoint/journal tests."""

from __future__ import annotations

import os


def test_history_store_roundtrip(server_state):
    store = server_state.store
    seq = store.next_seq()
    assert seq == 1
    hid = store.add({
        "seq": seq, "run_id": "run_1", "prompt": "make a cube", "status": "done",
        "timestamp": "2025-01-01T00:00:00", "summary": "made a cube", "tool_count": 3,
        "screenshot_url": None, "objects_affected": ["Cube (obj_00001)"],
        "checkpoint_before": "ckpt_00001", "checkpoint_after": "ckpt_00002",
    })
    entry = store.get(hid)
    assert entry["prompt"] == "make a cube"
    assert entry["objects_affected"] == ["Cube (obj_00001)"]

    store.update_status(hid, "undone")
    assert store.get(hid)["status"] == "undone"

    assert store.next_seq() == 2
    rows = store.list_all()
    assert len(rows) == 1 and rows[0]["seq"] == 1


def test_checkpoint_create_list_restore(addon, tmp_env):
    dispatch = addon["dispatch"]

    _, cube = dispatch("create_cube", {"name": "C", "dimensions_mm": [10, 10, 10]})
    ok, res = dispatch("create_checkpoint", {"label": "before test"})
    assert ok, res
    ckpt_id = res["checkpoint_id"]

    listed = dispatch("list_checkpoints", {})
    assert listed[0] and ckpt_id in [c["checkpoint_id"] for c in listed[1]["checkpoints"]]

    checkpoint_file = listed[1]["checkpoints"][0]["path"]
    assert os.path.exists(checkpoint_file)

    ok, res = dispatch("restore_checkpoint", {"checkpoint_id": ckpt_id})
    assert ok, res
    bpy = addon["bpy"]
    assert bpy.ops.wm.opened_files and bpy.ops.wm.opened_files[-1] == checkpoint_file


def test_undo_last_ai_action_requires_before_checkpoint(addon):
    dispatch = addon["dispatch"]
    ok, res = dispatch("create_checkpoint", {"label": "after only"})
    assert ok
    # no 'before-*' checkpoint yet -> must fail cleanly
    ok, res = dispatch("undo_last_ai_action", {})
    assert not ok
    assert "before" in str(res)
