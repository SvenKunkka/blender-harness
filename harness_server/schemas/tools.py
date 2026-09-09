"""Tool descriptions, JSON schemas and the wire messages exchanged with the
Blender add-on over WebSocket.

Every add-on tool call looks like:
  {"type":"tool_call","request_id":"req_x","tool":{"name":...,"arguments":{...}}}
and the add-on answers with:
  {"type":"tool_result","request_id":"req_x","ok":true,"result":{...},"error":null,"duration_ms":12}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

Risk = str  # "safe" | "mutating" | "destructive" | "exec"


class ToolSpec(BaseModel):
    name: str
    description: str
    category: str = "misc"
    risk: Risk = "safe"
    timeout_default_s: float = 60.0
    parameters: Dict[str, Any] = Field(default_factory=dict)  # JSON Schema object


class ToolCallMsg(BaseModel):
    type: str = "tool_call"
    request_id: str
    tool: Dict[str, Any]  # {"name": str, "arguments": {...}}


class ToolResultMsg(BaseModel):
    type: str = "tool_result"
    request_id: str
    ok: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class ToolExecution(BaseModel):
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    ts: str = ""


def to_llm_tool(spec: ToolSpec) -> Dict[str, Any]:
    """Convert a ToolSpec into an OpenAI-compatible function tool definition."""
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def specs_to_llm(specs: List[ToolSpec]) -> List[Dict[str, Any]]:
    return [to_llm_tool(s) for s in specs]
