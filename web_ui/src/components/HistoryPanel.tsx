import type { HistoryEntry } from "../types";
import { fmtDateTime, truncate } from "../format";
import { StatusPill } from "./pills";

const TONE: Record<HistoryEntry["status"], string> = {
  done: "done",
  undone: "undone",
  failed: "failed",
};

export interface HistoryPanelProps {
  history: HistoryEntry[];
  /** While a run is active, selection/undo are disabled. */
  busy: boolean;
  loadingRunId: string | null;
  onSelect: (entry: HistoryEntry) => void;
  onUndo: (entry: HistoryEntry) => void;
  onRestore: (entry: HistoryEntry) => void;
}

export function HistoryPanel({
  history,
  busy,
  loadingRunId,
  onSelect,
  onUndo,
  onRestore,
}: HistoryPanelProps) {
  const empty = history.length === 0;
  return (
    <div className="history-list">
      {empty ? (
        <div className="panel-hint">
          No runs yet. Every finished agent run lands here and can be undone.
        </div>
      ) : (
        history.map((entry) => {
          const loadingThis = loadingRunId !== null && loadingRunId === entry.run_id;
          return (
            <div
              key={entry.id}
              className={`hrow ${busy ? "hrow-disabled" : ""}`}
              onClick={() => {
                if (!busy && !loadingThis) onSelect(entry);
              }}
              title={
                entry.run_id
                  ? `load run ${entry.run_id}`
                  : "no run detail recorded for this entry"
              }
            >
              <span className="hrow-seq mono">{entry.seq}</span>
              <span className="hrow-main">
                <span className="hrow-prompt">{truncate(entry.prompt, 90)}</span>
                <span className="hrow-sub muted">
                  {fmtDateTime(entry.timestamp)}
                  {entry.tool_count > 0 ? ` · ${entry.tool_count} tools` : ""}
                  {entry.objects_affected.length > 0
                    ? ` · ${entry.objects_affected.length} obj`
                    : ""}
                </span>
              </span>
              {loadingThis ? (
                <span className="muted small mono">…</span>
              ) : (
                <StatusPill tone={TONE[entry.status]} label={entry.status} />
              )}
              {entry.status === "done" ? (
                <button
                  type="button"
                  className="btn btn-tiny"
                  disabled={busy}
                  onClick={(e) => {
                    e.stopPropagation();
                    onUndo(entry);
                  }}
                  title="Undo this run in Blender"
                >
                  undo
                </button>
              ) : entry.status === "undone" ? (
                <button
                  type="button"
                  className="btn btn-tiny"
                  disabled={busy}
                  onClick={(e) => {
                    e.stopPropagation();
                    onRestore(entry);
                  }}
                  title="Re-apply this run in Blender"
                >
                  restore
                </button>
              ) : (
                <span className="hrow-fail-note muted">no undo</span>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
