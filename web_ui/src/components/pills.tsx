// Reusable colored pill used for statuses/verdicts throughout the UI.

export type PillTone =
  | "done"
  | "undone"
  | "failed"
  | "finished"
  | "queued"
  | "running"
  | "stopped"
  | "pass"
  | "refine"
  | "skipped"
  | "neutral";

const TONE_CLASS: Record<string, string> = {
  done: "pill-done",
  finished: "pill-done",
  undone: "pill-undone",
  failed: "pill-failed",
  queued: "pill-queued",
  running: "pill-running",
  stopped: "pill-stopped",
  pass: "pill-done",
  refine: "pill-refine",
  skipped: "pill-idle",
  neutral: "pill-idle",
};

export function StatusPill({
  tone,
  label,
}: {
  tone: PillTone | string;
  label: string;
}) {
  const cls = TONE_CLASS[tone] ?? "pill-idle";
  return (
    <span className={`pill ${cls}`} title={label}>
      {label}
    </span>
  );
}
