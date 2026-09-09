import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ToolLogEntry } from "../types";
import { fmtDuration, fmtTime, truncate } from "../format";

function compactValue(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "string") return v.length > 48 ? `"${v.slice(0, 48)}…"` : `"${v}"`;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (typeof v === "object") {
    try {
      const s = JSON.stringify(v);
      return s && s.length > 60 ? `${s.slice(0, 60)}…` : (s ?? "null");
    } catch {
      return "…";
    }
  }
  return String(v);
}

function summarizeArgs(args: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(args)) {
    parts.push(`${k}=${compactValue(v)}`);
    if (parts.join(" ").length > 96) break;
  }
  return truncate(parts.join(" "), 160);
}

export interface ToolLogPanelProps {
  toolLog: ToolLogEntry[];
  runStatus: string | null;
}

export function ToolLogPanel({ toolLog, runStatus }: ToolLogPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [debugLines, setDebugLines] = useState<string[]>([]);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll the tool log to the newest row.
  useEffect(() => {
    if (!collapsed && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [toolLog.length, collapsed, showDebug]);

  // Poll raw server debug lines while the toggle is on.
  useEffect(() => {
    if (!showDebug) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await api.getLogs(200);
        if (!cancelled) setDebugLines(res.lines ?? []);
      } catch {
        if (!cancelled) setDebugLines(["… (log stream unavailable) …"]);
      }
    };
    void load();
    const id = window.setInterval(load, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [showDebug]);

  return (
    <section className="panel log-panel" aria-label="Tool execution log">
      <div className="panel-head">
        <button
          type="button"
          className="head-collapse"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Expand tool log" : "Collapse tool log"}
        >
          <span aria-hidden="true">{collapsed ? "▸" : "▾"}</span>
        </button>
        <span className="panel-title">Tool log</span>
        <span className="count-badge mono" title={`${toolLog.length} tool calls`}>
          {toolLog.length}
        </span>
        {runStatus ? (
          <span className="muted small mono">run {runStatus}</span>
        ) : null}
        <span className="head-spacer" />
        <button
          type="button"
          className={`btn btn-tiny ${showDebug ? "btn-active" : ""}`}
          onClick={() => setShowDebug((d) => !d)}
          title="Toggle raw server debug lines (last 200)"
        >
          debug lines
        </button>
      </div>

      {!collapsed ? (
        <div className="log-body" ref={bodyRef}>
          {showDebug ? (
            <pre className="debug-view">
              {debugLines.length > 0
                ? debugLines.join("\n")
                : "fetching debug lines…"}
            </pre>
          ) : toolLog.length === 0 ? (
            <div className="log-empty">
              No tool calls yet — start a run to watch the agent execute
              Blender operations here.
            </div>
          ) : (
            toolLog.map((entry, i) => (
              <div key={`${entry.ts}-${i}`} className="log-row">
                <span className="log-time mono" title={entry.ts}>
                  {fmtTime(entry.ts)}
                </span>
                <span className="log-tool mono" title={entry.tool}>
                  {entry.tool}
                  {Object.keys(entry.args).length > 0
                    ? `(${summarizeArgs(entry.args)})`
                    : "()"}
                </span>
                <span
                  className={`log-result mono ${entry.ok ? "ok-text" : "err-text"}`}
                >
                  {entry.ok ? (
                    <>
                      OK
                      {entry.duration_ms !== null
                        ? ` ${fmtDuration(entry.duration_ms)}`
                        : ""}
                    </>
                  ) : (
                    <>
                      ERR
                      {entry.error ? ` ${truncate(entry.error, 120)}` : ""}
                    </>
                  )}
                </span>
              </div>
            ))
          )}
        </div>
      ) : null}
    </section>
  );
}
