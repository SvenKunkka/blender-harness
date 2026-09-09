"""Logging helpers. Writes to logs/harness.log and keeps the last N lines in
memory so the Web UI can tail them without touching files."""

from __future__ import annotations

import logging
import sys
from collections import deque
from datetime import datetime
from typing import Deque, List

_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class RingBuffer(logging.Handler):
    """Keeps the most recent formatted records as plain strings."""

    def __init__(self, capacity: int = 400) -> None:
        super().__init__()
        self.lines: Deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - trivial
        try:
            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            self.lines.append(f"{ts} {record.levelname:<7s} {record.name}: {record.getMessage()}")
        except Exception:  # noqa: BLE001 - never break logging
            pass


ring = RingBuffer()


def configure_logging(level: str = "INFO", log_file: str = "logs/harness.log", debug: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter(_FMT))
    root.addHandler(stream)

    ring.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(ring)

    if log_file:
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(logging.Formatter(_FMT))
            root.addHandler(fh)
        except OSError:  # pragma: no cover
            root.warning("could not open log file %s", log_file)


def recent_lines(n: int = 200) -> List[str]:
    lines = list(ring.lines)
    return lines[-n:]
