"""Checkpoint & journal history for the add-on.

A checkpoint is a full copy of the current session saved as a temporary .blend
plus a JSON journal entry. Restoring opens that file again — reliable undo at
the cost of a full reload (Blender undo is preferred for tiny steps; checkpoints
guarantee recovery across edits, saves and crashes).

Journal schema (JSON file at <data_dir>/journal.json):
    {"seq": N, "entries": [{"id","kind","label","created_at","path", ...}]}
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from blender_addon.settings import checkpoints_dir, journal_path

log = logging.getLogger("bh.history")


def _load_journal() -> Dict[str, Any]:
    p = journal_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):  # noqa: BLE001
            pass
    return {"seq": 0, "entries": []}


def _save_journal(j: Dict[str, Any]) -> None:
    tmp = journal_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(j, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(journal_path()))


def _append(kind: str, label: str, path: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    j = _load_journal()
    j["seq"] += 1
    entry: Dict[str, Any] = {
        "id": f"ckpt_{j['seq']:05d}",
        "kind": kind,
        "label": label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "path": path,
    }
    if extra:
        entry.update(extra)
    j["entries"].append(entry)
    # keep the journal small
    j["entries"] = j["entries"][-500:]
    _save_journal(j)
    return entry


def _safe_slug(text: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_." else "_" for c in text)
    return keep[:48] or "checkpoint"


def create_checkpoint(label: str = "") -> Dict[str, Any]:
    import bpy

    label = label or f"checkpoint {datetime.now().isoformat(timespec='seconds')}"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = checkpoints_dir() / f"ckpt_{stamp}_{_safe_slug(label)}.blend"
    path_str = str(target)
    try:
        if os.path.exists(path_str):
            os.remove(path_str)
        if bpy.data.filepath:
            # save a copy of the current session without switching file paths
            result = bpy.ops.wm.save_as_mainfile(filepath=path_str, copy=True)
        else:
            result = bpy.ops.wm.save_as_mainfile(filepath=path_str, copy=True)
        if not os.path.exists(path_str):
            raise RuntimeError("Blender did not write the checkpoint file")
    except RuntimeError as exc:
        if "Error: " in str(exc):
            raise RuntimeError(f"checkpoint save failed: {exc}")
        raise
    entry = _append("checkpoint", label, path_str, {"bpy_file": bpy.data.filepath or None})
    log.info("checkpoint %s created: %s", entry["id"], path_str)
    return {"checkpoint_id": entry["id"], "label": label, "path": path_str,
            "created_at": entry["created_at"]}


def list_checkpoints() -> List[Dict[str, Any]]:
    j = _load_journal()
    out = []
    for e in j["entries"]:
        if e.get("kind") == "checkpoint":
            out.append({"checkpoint_id": e["id"], "label": e["label"],
                        "created_at": e["created_at"], "path": e.get("path")})
    return out


def _find(checkpoint_id: str) -> Optional[Dict[str, Any]]:
    j = _load_journal()
    for e in j["entries"]:
        if e.get("id") == checkpoint_id:
            return e
    # fall back to scanning the directory (journal may have been cleared)
    for f in sorted(checkpoints_dir().glob("*.blend")):
        if f.stem.startswith(checkpoint_id) or checkpoint_id in f.stem:
            return {"id": checkpoint_id, "label": f.stem, "path": str(f)}
    return None


def restore_checkpoint(checkpoint_id: str) -> Dict[str, Any]:
    import bpy

    entry = _find(checkpoint_id)
    if entry is None or not entry.get("path") or not Path(entry["path"]).exists():
        raise ValueError(f"checkpoint '{checkpoint_id}' not found on disk")
    path_str = entry["path"]
    log.info("restoring checkpoint %s from %s", checkpoint_id, path_str)
    _append("restore", f"restore {checkpoint_id}", path_str, {"checkpoint_id": checkpoint_id})
    bpy.ops.wm.open_mainfile(filepath=path_str)
    return {"restored_checkpoint_id": checkpoint_id, "path": path_str, "ok": True}


def undo_last_ai_action() -> Dict[str, Any]:
    """Restore the newest 'before-*' checkpoint (created by the harness before
    an AI run started mutating the scene)."""
    j = _load_journal()
    for e in reversed(j["entries"]):
        if e.get("kind") == "checkpoint" and str(e.get("label", "")).startswith("before"):
            return restore_checkpoint(e["id"])
    raise ValueError("no 'before' checkpoint found — nothing to undo")
