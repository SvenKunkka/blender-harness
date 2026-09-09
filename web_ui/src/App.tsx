import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorMessage, isRunningStatus, isTerminalRunStatus } from "./api";
import type {
  ChatMsg,
  HistoryEntry,
  RunDetail,
  SceneInfo,
  Status,
  ToolSpec,
} from "./types";

import { StatusBar } from "./components/StatusBar";
import { ChatPanel } from "./components/ChatPanel";
import { ToolLogPanel } from "./components/ToolLogPanel";
import { HistoryPanel } from "./components/HistoryPanel";
import { ScreenshotPanel } from "./components/ScreenshotPanel";
import { ScenePanel } from "./components/ScenePanel";
import { ToolSpecModal } from "./components/ToolSpecModal";
import { ToastStack, type ToastItem, type ToastKind } from "./components/Toast";

interface PendingPrompt {
  prompt: string;
  ts: string;
}

const POLL_INTERVAL_MS = 700;
const STATUS_INTERVAL_MS = 2000;
const HISTORY_INTERVAL_MS = 3000;
const MAX_CONSECUTIVE_POLL_ERRORS = 8;

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [toolsOpen, setToolsOpen] = useState(false);

  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [scene, setScene] = useState<SceneInfo | null>(null);
  const [sceneRefreshing, setSceneRefreshing] = useState(false);

  const [currentRun, setCurrentRun] = useState<RunDetail | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [pendingPrompt, setPendingPrompt] = useState<PendingPrompt | null>(null);
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);

  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastSeq = useRef(0);
  const [bottomTab, setBottomTab] = useState<"log" | "history">("log");

  const notify = useCallback((text: string, kind: ToastKind = "info") => {
    const id = ++toastSeq.current;
    setToasts((prev) => [...prev.slice(-4), { id, kind, text }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const running =
    activeRunId !== null ||
    pendingPrompt !== null ||
    (currentRun !== null && isRunningStatus(currentRun.status));

  // ---------- status poll (every 2 s) ----------
  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    const tick = async () => {
      try {
        const s = await api.getStatus();
        if (!cancelled) setStatus(s);
      } catch {
        // server may be down; keep last known status and retry
      }
      if (!cancelled) timer = window.setTimeout(tick, STATUS_INTERVAL_MS);
    };
    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  // ---------- tools (fetched on open so they stay fresh) ----------
  const openTools = useCallback(async () => {
    setToolsOpen(true);
    try {
      setTools(await api.getTools());
    } catch {
      // keep the previously cached list
    }
  }, []);

  const closeTools = useCallback(() => setToolsOpen(false), []);

  // ---------- history helpers ----------
  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await api.getHistory());
    } catch {
      // transient; next poll will retry
    }
  }, []);

  // Initial history + scene load.
  useEffect(() => {
    void refreshHistory();
    api
      .getScene()
      .then((s) => setScene(s))
      .catch(() => setScene(null));
  }, [refreshHistory]);

  // History poll every 3 s while no run is active.
  useEffect(() => {
    if (running) return;
    let cancelled = false;
    void refreshHistory();
    const id = window.setInterval(() => {
      if (!cancelled) void refreshHistory();
    }, HISTORY_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [running, refreshHistory]);

  // ---------- scene refresh ----------
  const refreshScene = useCallback(async () => {
    setSceneRefreshing(true);
    try {
      setScene(await api.refreshScene());
    } catch (err) {
      notify(`Scene refresh failed: ${errorMessage(err)}`, "error");
    } finally {
      setSceneRefreshing(false);
    }
  }, [notify]);

  // ---------- run lifecycle ----------
  const startRun = useCallback(
    async (prompt: string) => {
      const text = prompt.trim();
      if (!text || running) return;
      // Transient local user bubble while the run_id is being minted.
      setPendingPrompt({ prompt: text, ts: new Date().toISOString() });
      setCurrentRun(null);
      try {
        const { run_id } = await api.startRun(text);
        setPendingPrompt(null);
        setActiveRunId(run_id);
      } catch (err) {
        setPendingPrompt(null);
        notify(`Could not start run: ${errorMessage(err)}`, "error");
      }
    },
    [running, notify],
  );

  const stopRun = useCallback(async () => {
    const id =
      activeRunId ??
      (currentRun !== null && isRunningStatus(currentRun.status)
        ? currentRun.run_id
        : null);
    if (!id) return;
    try {
      const res = await api.stopRun(id);
      notify(res.message ?? "Stop requested", "info");
    } catch (err) {
      notify(`Stop failed: ${errorMessage(err)}`, "error");
    }
  }, [activeRunId, currentRun, notify]);

  const quietSyncAfterRun = useCallback(() => {
    void refreshHistory();
    api
      .getScene()
      .then((s) => setScene(s))
      .catch(() => {});
  }, [refreshHistory]);

  // Active-run poll driver (700 ms until terminal, then sync).
  useEffect(() => {
    if (!activeRunId) return;
    let cancelled = false;
    let timer = 0;
    let errors = 0;

    const tick = async () => {
      try {
        const detail = await api.getRun(activeRunId);
        if (cancelled) return;
        errors = 0;
        setCurrentRun(detail);
        if (isTerminalRunStatus(detail.status)) {
          setActiveRunId(null);
          if (detail.status === "failed") {
            notify(
              `Run failed: ${detail.error ?? "no error detail from server"}`,
              "error",
            );
          } else if (detail.status === "stopped") {
            notify("Run stopped", "info");
          }
          quietSyncAfterRun();
          return;
        }
        timer = window.setTimeout(tick, POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        errors += 1;
        if (errors >= MAX_CONSECUTIVE_POLL_ERRORS) {
          setActiveRunId(null);
          notify(`Lost contact while polling run: ${errorMessage(err)}`, "error");
          return;
        }
        timer = window.setTimeout(tick, 2000);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeRunId, notify, quietSyncAfterRun]);

  // ---------- history entry actions ----------
  const openHistoryRun = useCallback(
    async (entry: HistoryEntry) => {
      if (!entry.run_id) {
        notify("This history entry has no run detail to load", "info");
        return;
      }
      setLoadingRunId(entry.run_id);
      try {
        const detail = await api.getRun(entry.run_id);
        setCurrentRun(detail);
        setPendingPrompt(null);
        setActiveRunId(null);
      } catch (err) {
        notify(`Could not load run ${entry.run_id}: ${errorMessage(err)}`, "error");
      } finally {
        setLoadingRunId(null);
      }
    },
    [notify],
  );

  const undoEntry = useCallback(
    async (entry: HistoryEntry) => {
      try {
        const res = await api.undoHistory(entry.id);
        notify(res.message ?? `Undid history #${entry.seq}`, "ok");
        await refreshHistory();
      } catch (err) {
        notify(`Undo failed: ${errorMessage(err)}`, "error");
      }
    },
    [notify, refreshHistory],
  );

  const restoreEntry = useCallback(
    async (entry: HistoryEntry) => {
      try {
        const res = await api.restoreHistory(entry.id);
        notify(res.message ?? `Restored history #${entry.seq}`, "ok");
        await refreshHistory();
      } catch (err) {
        notify(`Restore failed: ${errorMessage(err)}`, "error");
      }
    },
    [notify, refreshHistory],
  );

  // ---------- derived view state ----------
  const chatMessages: ChatMsg[] = useMemo(() => {
    if (pendingPrompt) {
      const local: ChatMsg = {
        role: "user",
        content: pendingPrompt.prompt,
        ts: pendingPrompt.ts,
      };
      const base = currentRun ? currentRun.messages : [];
      const already = base.some(
        (m) => m.role === "user" && m.content === pendingPrompt.prompt,
      );
      return already ? base : [...base, local];
    }
    return currentRun ? currentRun.messages : [];
  }, [pendingPrompt, currentRun]);

  const fallbackScreenshot = useMemo(() => {
    for (const entry of history) {
      if (entry.screenshot_url) return entry.screenshot_url;
    }
    return null;
  }, [history]);

  return (
    <div className="app">
      <StatusBar
        status={status}
        sceneRefreshing={sceneRefreshing}
        onRefreshScene={() => void refreshScene()}
        onOpenTools={() => void openTools()}
      />

      <main className="app-main">
        <div className="left-col">
          <ChatPanel
            messages={chatMessages}
            run={currentRun}
            loadingRun={loadingRunId !== null}
            running={running}
            onSend={(p) => void startRun(p)}
            onStop={() => void stopRun()}
          />

          <div className="panel drawer">
            <div className="panel-head drawer-head">
              <div className="tabs" role="tablist" aria-label="Activity">
                <button
                  type="button"
                  role="tab"
                  aria-selected={bottomTab === "log"}
                  className={`tab ${bottomTab === "log" ? "tab-on" : ""}`}
                  onClick={() => setBottomTab("log")}
                >
                  Tool log
                  <span className="count-badge mono">
                    {currentRun?.tool_log.length ?? 0}
                  </span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={bottomTab === "history"}
                  className={`tab ${bottomTab === "history" ? "tab-on" : ""}`}
                  onClick={() => setBottomTab("history")}
                >
                  History
                  <span className="count-badge mono">{history.length}</span>
                </button>
              </div>
              <span className="head-spacer" />
              {bottomTab === "log" ? (
                <span className="muted small mono">live stream</span>
              ) : (
                <span className="muted small mono">poll · 3s</span>
              )}
            </div>

            {bottomTab === "log" ? (
              <div className="pane">
                <ToolLogPanel
                  toolLog={currentRun?.tool_log ?? []}
                  runStatus={currentRun?.status ?? null}
                />
              </div>
            ) : (
              <div className="pane">
                <div className="panel pane-panel">
                  <div className="panel-head">
                    <span className="panel-title">History</span>
                    <span className="muted small">
                      click a row to load its run detail
                    </span>
                    <span className="head-spacer" />
                    {running ? (
                      <span className="muted small mono">paused while running</span>
                    ) : (
                      <span className="ok-text small mono">live</span>
                    )}
                  </div>
                  <HistoryPanel
                    history={history}
                    busy={running || pendingPrompt !== null}
                    loadingRunId={loadingRunId}
                    onSelect={(entry) => void openHistoryRun(entry)}
                    onUndo={(entry) => void undoEntry(entry)}
                    onRestore={(entry) => void restoreEntry(entry)}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="right-col">
          <ScreenshotPanel run={currentRun} fallbackUrl={fallbackScreenshot} />
          <ScenePanel
            scene={scene}
            refreshing={sceneRefreshing}
            onRefresh={() => void refreshScene()}
          />
        </div>
      </main>

      <ToolSpecModal open={toolsOpen} tools={tools} onClose={closeTools} />
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
