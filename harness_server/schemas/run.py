"""Run / history / chat schemas returned by the REST API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

RUN_STATUS = ("queued", "running", "finished", "failed", "stopped")
STEP_STATUS = ("pending", "active", "done", "failed")
HISTORY_STATUS = ("done", "undone", "failed")


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    reference_images: Optional[List[Dict[str, str]]] = None  # [{name, data_url}]


class PlanStep(BaseModel):
    label: str
    status: str = "pending"


class ToolLogEntry(BaseModel):
    ts: str
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class ChatMsg(BaseModel):
    role: str  # user | assistant | system | tool(display only)
    content: str
    ts: str


class VisionReview(BaseModel):
    round: int
    verdict: str  # PASS | REFINE | SKIPPED
    issues: List[str] = Field(default_factory=list)
    comment: str = ""
    image_urls: List[str] = Field(default_factory=list)


class RunDetail(BaseModel):
    run_id: str
    status: str = "queued"
    prompt: str = ""
    source: str = "web"  # web | blender-panel
    created_at: str = ""
    finished_at: Optional[str] = None
    error: Optional[str] = None
    summary: Optional[str] = None
    plan: List[PlanStep] = Field(default_factory=list)
    tool_log: List[ToolLogEntry] = Field(default_factory=list)
    messages: List[ChatMsg] = Field(default_factory=list)
    screenshot_url: Optional[str] = None
    vision: List[VisionReview] = Field(default_factory=list)
    checkpoint_before: Optional[str] = None
    checkpoint_after: Optional[str] = None
    objects_affected: List[str] = Field(default_factory=list)


class HistoryEntry(BaseModel):
    id: int
    seq: int
    run_id: Optional[str] = None
    prompt: str = ""
    timestamp: str = ""
    status: str = "done"
    summary: Optional[str] = None
    tool_count: int = 0
    screenshot_url: Optional[str] = None
    objects_affected: List[str] = Field(default_factory=list)
    checkpoint_before: Optional[str] = None
    checkpoint_after: Optional[str] = None
