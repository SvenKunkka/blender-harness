// Tiny toast stack for action feedback (undo results, refresh errors, …).

export type ToastKind = "info" | "ok" | "error";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

export function ToastStack({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`} role="status">
          <span className="toast-mark" aria-hidden="true">
            {t.kind === "ok" ? "✓" : t.kind === "error" ? "✕" : "•"}
          </span>
          <span className="toast-text">{t.text}</span>
          <button
            type="button"
            className="toast-close"
            onClick={() => onDismiss(t.id)}
            title="Dismiss"
            aria-label="Dismiss notification"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
