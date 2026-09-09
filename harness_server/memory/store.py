"""SQLite-backed history store. Each user prompt that actually touches the
scene becomes one history entry (an "AI step") with its checkpoints so it can
be undone/restored later."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seq INTEGER NOT NULL,
    run_id TEXT,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'done',
    timestamp TEXT NOT NULL,
    summary TEXT,
    tool_count INTEGER NOT NULL DEFAULT 0,
    screenshot_url TEXT,
    objects_affected TEXT NOT NULL DEFAULT '[]',
    checkpoint_before TEXT,
    checkpoint_after TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_seq ON history(seq);
"""


class HistoryStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.data_dir / "harness.db"), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def next_seq(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM history").fetchone()
            return int(row["m"]) + 1

    def add(self, entry: Dict[str, Any]) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO history
                   (seq, run_id, prompt, status, timestamp, summary, tool_count,
                    screenshot_url, objects_affected, checkpoint_before, checkpoint_after)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry["seq"],
                    entry.get("run_id"),
                    entry["prompt"],
                    entry.get("status", "done"),
                    entry["timestamp"],
                    entry.get("summary"),
                    entry.get("tool_count", 0),
                    entry.get("screenshot_url"),
                    json.dumps(entry.get("objects_affected", [])),
                    entry.get("checkpoint_before"),
                    entry.get("checkpoint_after"),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def update_status(self, history_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE history SET status=? WHERE id=?", (status, history_id))
            self._conn.commit()

    def update_summary(self, history_id: int, summary: Optional[str], screenshot_url: Optional[str] = None,
                       checkpoint_after: Optional[str] = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE history SET summary=?, screenshot_url=COALESCE(?, screenshot_url), checkpoint_after=COALESCE(?, checkpoint_after) WHERE id=?",
                (summary, screenshot_url, checkpoint_after, history_id),
            )
            self._conn.commit()

    def get(self, history_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM history WHERE id=?", (history_id,)).fetchone()
        if row is None:
            return None
        return self._row(row)

    def list_all(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM history ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["objects_affected"] = json.loads(d.get("objects_affected") or "[]")
        return d
