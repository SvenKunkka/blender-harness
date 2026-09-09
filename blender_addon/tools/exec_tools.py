"""Sandboxed `execute_blender_python`.

Guards (AST based):
  * only a small set of imports is allowed (bpy, mathutils, math, json, typing);
  * dangerous builtins are removed (open/exec/eval/compile/globals/input/breakpoint…);
  * attribute chains that would reach subprocess/os/socket/ctypes/requests etc.
    are rejected at compile time;
  * a size cap and a *soft* time budget are enforced (Blender runs this on the
    main thread, so a runaway loop cannot be preempted — the result flags it and
    the UI is blocked meanwhile, which is why this tool is opt-in and a last
    resort; structured tools are always preferred).

The tool is only reachable when the server runs with ALLOW_EXECUTE_PYTHON=true.
"""

from __future__ import annotations

import ast
import builtins
import io
import math
import time
from contextlib import redirect_stdout

from blender_addon.tools._registry import ToolFailure, register

MAX_LINES = 80
MAX_CHARS = 12000
SOFT_TIMEOUT_S = 8.0

ALLOWED_IMPORTS = {"bpy", "mathutils", "math", "json", "typing"}
BANNED_NAME_FRAGMENTS = (
    "subprocess", "os.", "os)", "system(", "popen", "socket", "ctypes", "requests",
    "urllib", "http", "shutil", "pickle", "shelve", "pathlib", "tempfile",
    "builtins", "__import__", "compile", "eval", "exec", "breakpoint", "input(",
    "globals(", "locals(", "vars(", "open(", "file(",
)
SAFE_BUILTINS = {
    "len": len, "range": range, "enumerate": enumerate, "zip": zip, "min": min,
    "max": max, "sum": sum, "abs": abs, "round": round, "int": int, "float": float,
    "str": str, "list": list, "dict": dict, "set": set, "tuple": tuple, "bool": bool,
    "sorted": sorted, "reversed": reversed, "all": all, "any": any, "filter": filter,
    "map": map, "pow": pow, "isinstance": isinstance, "type": type, "print": print,
    "divmod": divmod, "complex": complex, "slice": slice, "repr": repr, "format": format,
    "iter": iter, "next": next, "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "RuntimeError": RuntimeError, "KeyError": KeyError, "IndexError": IndexError,
}


def _check_source(code: str) -> None:
    lines = code.strip("\n").splitlines()
    if len(lines) > MAX_LINES:
        raise ToolFailure(f"code too long: {len(lines)} lines (max {MAX_LINES})")
    if len(code) > MAX_CHARS:
        raise ToolFailure(f"code too long: {len(code)} chars (max {MAX_CHARS})")
    lowered = code.lower()
    for frag in BANNED_NAME_FRAGMENTS:
        if frag in lowered:
            raise ToolFailure(f"code rejected: banned fragment '{frag}'")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ToolFailure(f"code does not parse: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names]
            mod = (node.module or "") if isinstance(node, ast.ImportFrom) else names[0]
            root = (mod or names[0]).split(".")[0]
            if root not in ALLOWED_IMPORTS:
                raise ToolFailure(f"code rejected: import '{root}' is not on the whitelist")


def _run(code: str) -> dict:
    _check_source(code)
    import bpy  # noqa: PLC0415

    globs = {
        "bpy": bpy,
        "C": bpy.context,
        "D": bpy.data,
        "math": math,
        "__builtins__": SAFE_BUILTINS,
    }
    buf = io.StringIO()
    started = time.monotonic()
    error = None
    last_value = None
    try:
        with redirect_stdout(buf):
            exec(compile(code, "<blender_harness>", "exec"), globs)  # noqa: S102 - deliberately sandboxed
    except Exception as exc:  # noqa: BLE001 - user code errors are data
        error = f"{exc.__class__.__name__}: {exc}"
    duration = time.monotonic() - started
    output = buf.getvalue()
    return {
        "output": output[-4000:],
        "error": error,
        "execution_time_s": round(duration, 2),
        "soft_timeout_s": SOFT_TIMEOUT_S,
        "timed_out": duration > SOFT_TIMEOUT_S,
        "last_value_repr": repr(last_value)[:2000] if last_value is not None else None,
    }


@register("execute_blender_python", category="python", risk="exec")
def tool_execute_blender_python(args: dict) -> dict:
    code = str(args.get("code") or "").strip()
    if not code:
        raise ToolFailure("code is required")
    return _run(code)
