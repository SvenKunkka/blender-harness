"""Visual reviewer: sends rendered screenshots to a vision-capable model and
asks for a strict PASS / REFINE verdict so the agent can iterate.

The reviewer only produces *evidence-based* judgements: if a vision model is not
configured it returns SKIPPED instead of pretending everything is fine.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness_server.config import Settings
from harness_server.llm.provider import ChatProvider, ProviderError

log = logging.getLogger("harness.vision")

_REVIEW_PROMPT = """You are the visual QA stage of a Blender AI harness. Look carefully at the rendered screenshots of a 3D object/scene.

Original user instruction:
{instruction}

Scene facts (from Blender):
{facts}

Judge ONLY what the images show:
- Does the result satisfy the user's measurable requirements (dimensions, proportions, region limits, count, etc.)?
- Is there obvious interpenetration (穿模), missing geometry, an object that vanished, an abnormal aspect ratio, or changes applied to the WRONG region?
- Any other obvious defect a human reviewer would flag?

Respond with JSON only, exactly this shape:
{{"verdict": "PASS" or "REFINE", "issues": ["short issue 1", ...], "comment": "one-sentence summary"}}

Use PASS only when requirements are visually satisfied or you cannot see any violation; otherwise REFINE with concrete, actionable issues."""


class VisionReviewer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider: Optional[ChatProvider] = None

    def _ensure_provider(self) -> Optional[ChatProvider]:
        if not self.settings.vision_configured:
            return None
        if self.provider is None:
            self.provider = ChatProvider(
                base_url=self.settings.vision_base_url,
                api_key=self.settings.vision_api_key,
                model=self.settings.vision_model or "",
                timeout_s=self.settings.llm_timeout_s,
            )
        return self.provider

    @staticmethod
    def _data_url(path: Path) -> str:
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def build_messages(self, instruction: str, facts: str, image_paths: List[Path]) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": _REVIEW_PROMPT.format(instruction=instruction, facts=facts)}
        ]
        for p in image_paths:
            content.append({"type": "image_url", "image_url": {"url": self._data_url(p)}})
        return [{"role": "user", "content": content}]

    async def review(self, instruction: str, facts: str, image_paths: List[Path]) -> Dict[str, Any]:
        """Returns {verdict: PASS|REFINE|SKIPPED|ERROR, issues: [...], comment: str}."""
        provider = self._ensure_provider()
        if provider is None:
            log.info("vision not configured; skipping visual review")
            return {"verdict": "SKIPPED", "issues": [], "comment": "No vision model configured (set AI_VISION_MODEL or AI_MODEL with image support)."}
        existing = [p for p in image_paths if Path(p).exists()]
        if not existing:
            return {"verdict": "SKIPPED", "issues": [], "comment": "No screenshot files available to review."}
        try:
            out = await provider.chat(self.build_messages(instruction, facts, existing), temperature=0.0)
            content = (out.get("message") or {}).get("content") or ""
            return self._parse(content)
        except ProviderError as exc:
            log.warning("vision review failed: %s", exc)
            return {"verdict": "ERROR", "issues": [str(exc)], "comment": "Vision model call failed."}

    @staticmethod
    def _parse(content: str) -> Dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        try:
            data = json.loads(content)
        except ValueError:
            # tolerate "verdict: PASS" style free text
            text = content.upper()
            verdict = "PASS" if "PASS" in text and "REFINE" not in text else ("REFINE" if "REFINE" in text else "ERROR")
            return {"verdict": verdict, "issues": [content[:500]], "comment": content[:500]}
        return {
            "verdict": str(data.get("verdict", "ERROR")).upper(),
            "issues": [str(i) for i in (data.get("issues") or [])],
            "comment": str(data.get("comment", "")),
        }
