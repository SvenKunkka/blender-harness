"""The agent loop state machine.

User Prompt -> read scene (tools) -> act (tools) -> screenshot -> vision review
-> refine (up to MAX_VISION_REFINEMENTS) -> history step -> summary.

Safety: the very first mutating/destructive tool of a run is preceded by an
automatic checkpoint; a post-run checkpoint is captured so both Undo and
Restore of the step are deterministic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from harness_server.agent.prompts import system_prompt
from harness_server.llm.provider import ChatProvider, ProviderError
from harness_server.media import MediaStore
from harness_server.tools.bridge import execute_tool
from harness_server.tools.registry import category_of, is_known_tool, llm_tools, risk_of
from harness_server.vision.reviewer import VisionReviewer

if TYPE_CHECKING:  # pragma: no cover
    from harness_server.state import AppState

from harness_server.state import RunRecord  # noqa: E402  (no cycle: state never imports the agent)

log = logging.getLogger("harness.agent")

CAPTURE_TOOLS = {"capture_viewport", "render_image", "render_multi_angle", "capture_object_views"}
TOOL_RESULT_LIMIT = 9000  # chars of tool result fed back to the LLM
UI_MSG_ROLES = {"user", "assistant", "system"}

PLAN_LABELS = {
    "scene": "Inspect the scene",
    "transform": "Adjust placement / size",
    "mesh": "Create / edit geometry",
    "modifier": "Tune modifiers",
    "material": "Set materials",
    "camera": "Camera setup",
    "render": "Render screenshots",
    "file": "File handling",
    "history": "Checkpoint / history",
    "product": "Model the product",
    "python": "Run helper script",
}


def _ts(state: "AppState") -> str:
    return state.now()


def _llm_safe_result(result: Dict[str, Any]) -> str:
    """Strip giant base64 payloads before a tool result is fed back to the model."""
    clean = dict(result)
    clean.pop("image_b64", None)
    if "images" in clean and isinstance(clean["images"], list):
        clean["images"] = [{k: (v if k != "image_b64" else "<base64 omitted>") for k, v in img.items()}
                           for img in clean["images"] if isinstance(img, dict)]
    return json.dumps(clean, ensure_ascii=True)[:TOOL_RESULT_LIMIT]


def _collect_affected(result: Dict[str, Any], args: Dict[str, Any], acc: Set[str]) -> None:
    def add(v: Any) -> None:
        if isinstance(v, str) and v:
            acc.add(v)

    val = result.get("objects_affected")
    if isinstance(val, list):
        for item in val:
            if isinstance(item, dict):
                add(item.get("id") or item.get("name"))
            else:
                add(item)
    for k in ("object_id", "target_id", "new_object_id", "camera_id"):
        add(result.get(k))
    add(args.get("object_id"))


def _synth_summary(detail: Dict[str, Any]) -> str:
    tools = [e["tool"] for e in detail["tool_log"]]
    names = ", ".join(dict.fromkeys(tools))
    line = f"Completed {len(tools)} tool step(s): {names}."
    aff = detail.get("objects_affected") or []
    if aff:
        line += f" Affected: {', '.join(aff)}."
    return line


class AgentRun:
    def __init__(self, state: "AppState", run_id: str) -> None:
        self.state = state
        self.run_id = run_id
        self.cfg = state.settings
        self.rec: "RunRecord" = state.runs[run_id]
        self.detail = self.rec.detail
        self.media = MediaStore(state.settings)
        self.llm_messages: List[Dict[str, Any]] = []
        self.mutated = False
        self.affected_ids: Set[str] = set()
        self.vision_rounds = 0
        self.chat_provider: Optional[ChatProvider] = None
        self.vision: Optional[VisionReviewer] = None

    # ------------------------------------------------------------------ utils
    def ui(self, role: str, content: str) -> None:
        if role in UI_MSG_ROLES:
            self.detail["messages"].append({"role": role, "content": content, "ts": _ts(self.state)})

    def plan_step(self, category: str, mark: str) -> Dict[str, Any]:
        label = PLAN_LABELS.get(category, category)
        for step in self.detail["plan"]:
            if step["label"] == label:
                step["status"] = mark
                return step
        step = {"label": label, "status": mark}
        self.detail["plan"].append(step)
        return step

    def is_cancelled(self) -> bool:
        return self.rec.cancelled

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        sess = self.detail.get("_blender_session")
        if sess is not None:
            try:
                await sess.send({"type": "run_update", "run_id": self.run_id, **payload})
            except Exception:  # pragma: no cover
                pass

    async def _make_checkpoint(self, label: str) -> Optional[str]:
        res = await execute_tool(self.state, "create_checkpoint", {"label": label})
        if res.get("ok"):
            return (res.get("result") or {}).get("checkpoint_id")
        log.warning("checkpoint failed (%s): %s", label, res.get("error"))
        return None

    # ------------------------------------------------------------------ tools
    async def call_tool(self, name: str, args: Dict[str, Any], tool_call_id: str) -> bool:
        state = self.state
        started = _ts(state)
        category = category_of(name) if is_known_tool(name) else "misc"
        self.plan_step(category, "active")

        if not is_known_tool(name):
            content = json.dumps({"ok": False, "error": f"unknown tool: {name}"})
            self.llm_messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})
            self.detail["tool_log"].append({"ts": started, "tool": name, "args": args, "ok": False,
                                            "error": "unknown tool", "duration_ms": None})
            self.plan_step(category, "failed")
            return False

        risk = risk_of(name)
        # automatic safety checkpoint before the first scene mutation
        if risk in ("mutating", "destructive") and not self.mutated and self.detail.get("checkpoint_before") is None:
            self.mutated = True
            self.detail["checkpoint_before"] = await self._make_checkpoint(f"before-{self.run_id[:8]}")

        async with state.exec_gate:
            res = await execute_tool(state, name, args)
        ok = bool(res.get("ok"))

        if risk in ("mutating", "destructive") and ok:
            _collect_affected(res.get("result") or {}, args, self.affected_ids)

        # persist captures so /media urls exist for the UI and the vision step
        if ok and name in CAPTURE_TOOLS and (res.get("result") or {}):
            urls = self.media.save_capture(self.run_id, name, res["result"])
            if urls:
                self.detail["screenshot_url"] = urls[-1]

        if ok:
            content = _llm_safe_result(res.get("result") or {})
        else:
            content = json.dumps({"ok": False, "error": res.get("error"),
                                  "hint": res.get("hint") or "retry after checking the scene"}, ensure_ascii=True)
        self.llm_messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})

        err = None if ok else (res.get("error") or "tool failed")
        self.detail["tool_log"].append({"ts": started, "tool": name, "args": args, "ok": ok,
                                        "error": err, "duration_ms": res.get("duration_ms")})
        log.info("tool %s ok=%s err=%s", name, ok, err)
        await self._broadcast({"tool": name, "ok": ok, "error": err})

        # keep the UI scene panel fresh after mutations
        if ok and risk in ("mutating", "destructive"):
            from harness_server.api import refresh_scene_cache

            try:
                await refresh_scene_cache(state)  # locks state.scene_lock internally
            except Exception as exc:  # pragma: no cover
                log.debug("scene refresh after tool failed: %s", exc)

        self.plan_step(category, "done" if ok else ("pending" if "BLENDER_NOT_CONNECTED" in str(err or "") else "failed"))
        return ok

    # ------------------------------------------------------------- main loop
    async def execute(self, prompt: str, reference_images: Optional[List[Dict[str, str]]]) -> None:
        state = self.state
        detail = self.detail
        cfg = self.cfg

        try:
            if not cfg.chat_configured:
                raise ProviderError("LLM not configured — set AI_MODEL (+ AI_BASE_URL / AI_API_KEY) in .env or the Settings modal.")

            self.chat_provider = ChatProvider(cfg.base_url, cfg.ai_api_key, cfg.chat_model, cfg.llm_timeout_s)
            self.vision = VisionReviewer(cfg)

            history_text = [f"v{e['seq']}: {e['prompt'][:120]}" for e in state.store.list_all(limit=20)]
            self.llm_messages.append({"role": "system", "content": system_prompt(history_text, cfg.allow_execute_python)})

            user_content: Any = prompt
            if reference_images:
                parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
                for ref in reference_images[:6]:
                    if ref.get("data_url"):
                        parts.append({"type": "image_url", "image_url": {"url": ref["data_url"]}})
                user_content = parts
            self.llm_messages.append({"role": "user", "content": user_content})
            self.ui("user", prompt)

            steps = 0
            final_text: Optional[str] = None
            refine_feedback: Optional[str] = None
            finished_by_model = False

            while steps < cfg.max_agent_steps:
                if self.is_cancelled():
                    break

                # inject visual-review feedback if a refinement round is pending
                if refine_feedback:
                    self.llm_messages.append({"role": "user", "content": refine_feedback})
                    self.ui("system", refine_feedback)
                    refine_feedback = None

                try:
                    resp = await asyncio.wait_for(
                        self.chat_provider.chat(self.llm_messages, tools=llm_tools(cfg.allow_execute_python)),
                        timeout=cfg.llm_timeout_s,
                    )
                except asyncio.TimeoutError:
                    raise ProviderError(f"LLM call timed out after {cfg.llm_timeout_s:.0f}s")

                message = resp.get("message") or {}
                calls = self.chat_provider.parse_tool_calls(message)

                if calls:
                    self.llm_messages.append(message)
                    for call in calls:
                        if self.is_cancelled() or steps >= cfg.max_agent_steps:
                            break
                        steps += 1
                        await self.call_tool(call["name"], call.get("arguments") or {}, call["id"])
                    continue  # let the model decide the next move

                # ---- model finished its tool work
                content = message.get("content")
                if content and str(content).strip():
                    final_text = str(content).strip()
                    self.ui("assistant", final_text)
                finished_by_model = True

                # ---- visual verification of the changes
                if not self.mutated or self.is_cancelled() or cfg.max_vision_refinements <= 0:
                    break

                verdict = await self._verify(prompt)
                if self.is_cancelled():
                    break
                if verdict == "REFINE" and self.vision_rounds < cfg.max_vision_refinements:
                    self.vision_rounds += 1
                    review = self.detail["vision"][-1]
                    issues = "\n".join(f"- {i}" for i in review.get("issues", []))
                    refine_feedback = "A visual check of the rendered result found problems; fix them, then render again.\n" + issues
                    finished_by_model = False
                    continue
                break  # PASS / SKIPPED / ERROR or budget exhausted

            # ---- terminal bookkeeping
            if self.is_cancelled():
                detail["status"] = "stopped"
                detail["error"] = "run stopped by user"
            elif finished_by_model or detail["tool_log"]:
                if final_text is None and detail["tool_log"]:
                    final_text = _synth_summary(detail)
                    self.ui("assistant", final_text)
                detail["summary"] = final_text
                detail["status"] = "finished"
                detail["error"] = None
            else:
                detail["status"] = "failed"
                detail["error"] = "agent produced no output"

            if detail["status"] == "finished" and self.mutated and detail.get("checkpoint_before"):
                detail["checkpoint_after"] = await self._make_checkpoint(f"after-{self.run_id[:8]}")

            detail["objects_affected"] = self._affected_names()
            detail["checkpoint_id"] = detail.get("checkpoint_before")
            self._write_history()
            if detail["status"] == "finished":
                await self._broadcast({"event": "finished", "summary": detail.get("summary")})

        except asyncio.CancelledError:
            detail["status"] = "stopped"
            detail["error"] = "run stopped by user"
            detail["finished_at"] = self.state.now()
            self._write_history()
            raise
        except ProviderError as exc:
            detail["status"] = "failed"
            detail["error"] = str(exc)
            self.ui("system", f"Agent error: {exc}")
            self._write_history()
        except Exception as exc:  # noqa: BLE001 - surface anything unexpected
            log.exception("agent run %s crashed", self.run_id)
            detail["status"] = "failed"
            detail["error"] = f"{exc.__class__.__name__}: {exc}"
            self._write_history()
        finally:
            detail["finished_at"] = self.state.now()
            if self.chat_provider is not None:
                await self.chat_provider.close()

    # ------------------------------------------------------------ vision step
    def _affected_names(self) -> List[str]:
        names: List[str] = []
        details = self.state.scene_cache.object_details
        for oid in self.affected_ids:
            entry = details.get(oid)
            if entry and entry.get("name"):
                names.append(f"{entry.get('name')} ({oid})")
            else:
                names.append(oid)
        seen: Set[str] = set()
        out: List[str] = []
        for n in names:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    async def _verify(self, instruction: str) -> str:
        """Render multi-angle screenshots of the scene and ask the vision model
        for a PASS/REFINE verdict. Appends one entry to detail['vision']."""
        detail = self.detail
        res = await execute_tool(self.state, "capture_object_views", {})
        if not res.get("ok"):
            detail["vision"].append({"round": self.vision_rounds + 1, "verdict": "SKIPPED", "issues": [],
                                     "comment": f"capture failed: {res.get('error')}", "image_urls": []})
            return "SKIPPED"
        urls = self.media.save_capture(self.run_id, "verify", res["result"])
        paths = [self.media.abs_url_to_path(u) for u in urls]
        facts = "object(s) affected: " + (", ".join(self._affected_names()) or "unknown")
        if self.state.scene_cache.summary:
            facts += f"; scene: {self.state.scene_cache.summary.get('object_count')} objects"
        review = await self.vision.review(instruction, facts, paths)
        detail["vision"].append({
            "round": self.vision_rounds + 1,
            "verdict": review.get("verdict", "SKIPPED"),
            "issues": review.get("issues", []),
            "comment": review.get("comment", ""),
            "image_urls": urls,
        })
        verdict = review.get("verdict", "SKIPPED")
        log.info("vision round %d -> %s", self.vision_rounds + 1, verdict)
        return verdict if verdict in ("PASS", "REFINE") else "SKIPPED"

    # ------------------------------------------------------------ history row
    def _write_history(self) -> None:
        state = self.state
        detail = self.detail
        if detail["status"] in ("queued", "running"):
            return
        tool_count = len(detail["tool_log"])
        mutated = bool(self.mutated and detail.get("checkpoint_before"))
        if not mutated:
            # a read-only answer (or a crash before any scene change) is not an
            # AI step; only record failed runs that already attempted actions
            if not (detail["status"] == "failed" and tool_count > 0):
                return
        status = detail["status"]
        if status == "stopped":
            row_status = "done" if mutated else "failed"
        elif status == "failed":
            row_status = "failed"
        else:
            row_status = "done"
        seq = state.store.next_seq()
        hid = state.store.add({
            "seq": seq,
            "run_id": self.run_id,
            "prompt": detail["prompt"],
            "status": row_status,
            "timestamp": detail["created_at"],
            "summary": detail.get("summary"),
            "tool_count": tool_count,
            "screenshot_url": detail.get("screenshot_url"),
            "objects_affected": detail.get("objects_affected", []),
            "checkpoint_before": detail.get("checkpoint_before"),
            "checkpoint_after": detail.get("checkpoint_after"),
        })
        self.rec.history_id = hid


def start_run(state: "AppState", prompt: str, source: str = "web",
              reference_images: Optional[List[Dict[str, str]]] = None,
              blender_session=None) -> str:
    """Create a run record and spawn its agent task. Returns run_id."""
    if not state.settings.chat_configured:
        raise ValueError("LLM not configured — set AI_MODEL (+ AI_BASE_URL / AI_API_KEY) in .env first.")

    import uuid

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    detail: Dict[str, Any] = {
        "run_id": run_id,
        "status": "queued",
        "prompt": prompt,
        "source": source,
        "created_at": state.now(),
        "finished_at": None,
        "error": None,
        "summary": None,
        "plan": [],
        "tool_log": [],
        "messages": [],
        "screenshot_url": None,
        "vision": [],
        "checkpoint_before": None,
        "checkpoint_after": None,
        "checkpoint_id": None,
        "objects_affected": [],
    }
    if blender_session is not None:
        detail["_blender_session"] = blender_session
    rec = RunRecord(detail=detail)
    state.runs[run_id] = rec
    if len(state.runs) > 60:
        for rid in [r for r, rr in state.runs.items() if rr.task and rr.task.done()][:-60]:
            state.runs.pop(rid, None)

    async def _task_wrapper() -> None:
        detail["status"] = "running"
        runner = AgentRun(state, run_id)
        await runner.execute(prompt, reference_images)

    rec.task = asyncio.create_task(_task_wrapper())
    return run_id


def stop_run(state: "AppState", run_id: str) -> bool:
    rec = state.runs.get(run_id)
    if rec is None:
        return False
    rec.cancelled = True
    if rec.task and not rec.task.done():
        rec.task.cancel()
    return True
