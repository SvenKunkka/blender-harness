"""Persist screenshot payloads that arrive from Blender (base64 PNG) into the
server media directory and produce public /media URLs."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness_server.config import Settings


class MediaStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.media_dir()

    def run_dir(self, run_id: str) -> Path:
        d = self.root / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_base64(self, rel_path: str, b64: str) -> str:
        data = base64.b64decode(b64)
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"/media/{rel_path}"

    def save_capture(self, run_id: str, tool_name: str, result: Dict[str, Any]) -> List[str]:
        """Save any images embedded in a capture tool result. Returns public urls."""
        urls: List[str] = []
        if "image_b64" in result:
            ext = "png"
            rel = f"{run_id}/{tool_name}.png"
            urls.append(self.save_base64(rel, result["image_b64"]))
        for img in result.get("images") or []:
            if not isinstance(img, dict) or not img.get("image_b64"):
                continue
            angle = img.get("angle", "view")
            rel = f"{run_id}/{tool_name}_{angle}.png"
            urls.append(self.save_base64(rel, img["image_b64"]))
        return urls

    def abs_url_to_path(self, url: str) -> Path:
        rel = url.removeprefix("/media/")
        return self.root / rel
