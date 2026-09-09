"""Add-on data directory & runtime settings (mirrors server-side data layout)."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("BLENDER_HARNESS_DATA_DIR")
    if override:
        p = Path(override)
    else:
        p = Path.home() / ".blender_harness"
    p.mkdir(parents=True, exist_ok=True)
    return p


def checkpoints_dir() -> Path:
    d = data_dir() / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def shots_dir() -> Path:
    d = data_dir() / "shots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def journal_path() -> Path:
    return data_dir() / "journal.json"


def addon_version() -> str:
    from blender_addon.version import ADDON_VERSION

    return ADDON_VERSION
