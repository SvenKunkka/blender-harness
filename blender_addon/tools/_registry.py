"""Tool registry and dispatcher.

Every structured tool available to the AI is a plain function:

    def handler(args: dict) -> dict            # result payload

registered with the @register decorator. `dispatch(name, args)` returns
(ok, result_or_error) — exceptions become structured error responses.

The add-on does NOT need JSON schemas (the server holds them); it only needs a
handler for every tool name in the server registry.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
META: Dict[str, Dict[str, Any]] = {}


class ToolFailure(Exception):
    """Raised inside a handler to produce a clean structured error."""


def register(*names: str, category: str = "misc", risk: str = "safe") -> Callable:
    def deco(fn: Callable) -> Callable:
        for n in names:
            if n in HANDLERS:
                raise ValueError(f"duplicate tool registration: {n}")
            HANDLERS[n] = fn
            META[n] = {"category": category, "risk": risk}
        return fn

    return deco


def known_tools() -> List[str]:
    return sorted(HANDLERS.keys())


def dispatch(name: str, args: Dict[str, Any]) -> Tuple[bool, Any]:
    fn = HANDLERS.get(name)
    if fn is None:
        known = ", ".join(known_tools())
        return False, f"unknown tool '{name}'. Known tools: {known}"
    try:
        result = fn(args or {})
        if isinstance(result, dict):
            result.setdefault("tool", name)
        return True, result
    except ToolFailure as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - handlers must never crash the pump
        import traceback

        tb = traceback.format_exc(limit=3)
        return False, f"{exc.__class__.__name__}: {exc}"


# ---------------------------------------------------------------------------
# helpers shared by handlers
# ---------------------------------------------------------------------------

def require(args: Dict[str, Any], key: str):
    if key not in args or args[key] in (None, ""):
        raise ToolFailure(f"missing required argument '{key}'")
    return args[key]


def vec3(args: Dict[str, Any], key: str, what: str = "vector") -> List[float]:
    v = args.get(key)
    if v is None:
        raise ToolFailure(f"missing required argument '{key}' ({what})")
    try:
        return [float(x) for x in v][:3]
    except (TypeError, ValueError) as exc:
        raise ToolFailure(f"argument '{key}' must be [x, y, z], got {v!r}") from exc
