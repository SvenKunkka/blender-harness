import { useEffect, useRef, useState } from "react";
import type { ChatMsg, PlanStep, RunDetail } from "../types";
import { fmtDateTime, fmtTime } from "../format";
import { StatusPill } from "./pills";

export const EXAMPLE_PROMPTS: string[] = [
  "Create a 75% keyboard base: 325 × 145 × 18 mm, corner radius 6 mm.",
  "Create a mouse concept: length 120 mm, width 64 mm, height 39 mm, highest point ~45 mm from the rear.",
  "Take the selected enclosure and: increase width by 2 mm, keep length unchanged, add a 1.5 mm bevel.",
  "Create three variants of the selected object: A original height, B height -2mm, C height +2mm; arrange side by side.",
];

const ROLE_LABEL: Record<ChatMsg["role"], string> = {
  user: "you",
  assistant: "agent",
  system: "system",
};

const STEP_ICON: Record<PlanStep["status"], string> = {
  pending: "○",
  active: "▶",
  done: "✓",
  failed: "✕",
};

const RUN_TONE: Record<RunDetail["status"], string> = {
  queued: "queued",
  running: "running",
  finished: "finished",
  failed: "failed",
  stopped: "stopped",
};

export interface ChatPanelProps {
  messages: ChatMsg[];
  /** The run whose detail (plan/summary/log) is currently displayed. */
  run: RunDetail | null;
  /** True while a historical run detail is being fetched. */
  loadingRun: boolean;
  running: boolean;
  onSend: (prompt: string) => void;
  onStop: () => void;
}

export function ChatPanel({
  messages,
  run,
  loadingRun,
  running,
  onSend,
  onStop,
}: ChatPanelProps) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const plan = run?.plan ?? [];
  const finished = run !== null && run.status !== "queued" && run.status !== "running";

  // Keep the newest content in view.
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, plan.length, run?.status, run?.summary]);

  const submit = () => {
    const text = draft.trim();
    if (!text || running) return;
    onSend(text);
    setDraft("");
  };

  const sendExample = (example: string) => {
    if (!running) onSend(example);
  };

  return (
    <section className="panel chat-panel" aria-label="Agent chat">
      <div className="panel-head">
        <span className="panel-title">Run chat</span>
        {run ? (
          <span className="head-run mono" title={run.run_id}>
            {run.run_id}
          </span>
        ) : null}
        <span className="head-spacer" />
        {loadingRun ? <span className="muted small">loading run…</span> : null}
        {run ? (
          <StatusPill tone={RUN_TONE[run.status]} label={run.status} />
        ) : null}
      </div>

      <div className="chat-msgs" aria-live="polite">
        {messages.length === 0 && !loadingRun ? (
          <div className="chat-empty">
            Type a prompt to start an agent run — the harness drives Blender and
            streams its plan, tool calls, messages and viewport screenshot back
            here. Pick an example below to try it instantly.
          </div>
        ) : null}

        {messages.map((m, i) => (
          <div
            key={`${m.ts}-${i}`}
            className={`msg msg-${m.role}`}
            role={m.role === "assistant" ? "status" : undefined}
          >
            {m.role === "system" ? (
              <span className="msg-content system-content">{m.content}</span>
            ) : (
              <span className="msg-content">{m.content}</span>
            )}
            <span className="msg-meta">
              {ROLE_LABEL[m.role]} · {fmtTime(m.ts)}
            </span>
          </div>
        ))}

        {plan.length > 0 ? (
          <div className="plan-block">
            <span className="plan-label">plan</span>
            <div className="chips">
              {plan.map((step, i) => (
                <span
                  key={`${i}-${step.label}`}
                  className={`chip chip-${step.status}`}
                  title={step.label}
                >
                  <span className="chip-ico" aria-hidden="true">
                    {STEP_ICON[step.status]}
                  </span>
                  {step.label}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {run && (finished || run.summary !== null) ? (
          <ResultCard run={run} />
        ) : null}

        {run && run.error ? (
          <div className="run-error">
            <span className="mono">{run.error}</span>
          </div>
        ) : null}

        <div ref={scrollRef} />
      </div>

      <div className="composer">
        <div className="examples">
          {EXAMPLE_PROMPTS.map((ex) => (
            <button
              type="button"
              key={ex}
              className="example"
              disabled={running}
              title={`Send example prompt:\n${ex}`}
              onClick={() => sendExample(ex)}
            >
              {ex}
            </button>
          ))}
        </div>
        <div className="composer-row">
          <textarea
            className="chat-input"
            placeholder={
              running
                ? "Agent run in progress…"
                : "Describe what to do in Blender… (Enter to send)"
            }
            value={draft}
            rows={3}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <div className="composer-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={running || draft.trim().length === 0}
              onClick={submit}
            >
              {running ? "Running…" : "Run ▶"}
            </button>
            {running ? (
              <button
                type="button"
                className="btn btn-danger"
                onClick={onStop}
                title="Ask the server to stop the active run"
              >
                ■ Stop
              </button>
            ) : null}
          </div>
        </div>
        <div className="composer-hint">
          {run && finished ? (
            <span>
              finished {fmtDateTime(run.finished_at)} ·{" "}
              {run.tool_log.length} tool call{run.tool_log.length === 1 ? "" : "s"}
            </span>
          ) : run ? (
            <span>
              started {fmtDateTime(run.created_at)} · status {run.status}
            </span>
          ) : (
            <span>agent steps stream live while the run executes</span>
          )}
        </div>
      </div>
    </section>
  );
}

function ResultCard({ run }: { run: RunDetail }) {
  const n = run.objects_affected.length;
  return (
    <div className="result">
      <div className="result-title">
        <span className="result-status">
          <StatusPill tone={RUN_TONE[run.status]} label={run.status} />
        </span>
        <span className="result-summary-label">result</span>
      </div>
      {run.summary ? (
        <p className="result-summary">{run.summary}</p>
      ) : (
        <p className="result-summary muted">
          No textual summary was produced for this run.
        </p>
      )}
      <div className="result-meta">
        {n > 0 ? (
          <span className="result-chip" title={run.objects_affected.join(", ")}>
            <span className="ok-text">{n}</span> object{n === 1 ? "" : "s"} affected
          </span>
        ) : (
          <span className="result-chip muted">no objects recorded</span>
        )}
        {run.checkpoint_id ? (
          <span className="result-chip mono" title="blend checkpoint">
            ✓ {run.checkpoint_id}
          </span>
        ) : null}
        {run.vision.length > 0 ? (
          <span className="result-chip">vision {run.vision.length} review{run.vision.length === 1 ? "" : "s"}</span>
        ) : null}
      </div>
    </div>
  );
}
