import type { Status } from "../types";
import { basenameOf, fmtUptime } from "../format";

export interface StatusBarProps {
  status: Status | null;
  sceneRefreshing: boolean;
  onRefreshScene: () => void;
  onOpenTools: () => void;
}

export function StatusBar({
  status,
  sceneRefreshing,
  onRefreshScene,
  onOpenTools,
}: StatusBarProps) {
  const blenderOn = status?.blender.connected ?? false;
  const blenderFile = status?.blender.file_path ?? null;

  return (
    <header className="header">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          BH
        </div>
        <div className="brand-text">
          <div className="brand-name">Blender Harness</div>
          <div className="brand-sub">AI agent · viewport automation</div>
        </div>
      </div>

      <div className="stats" role="status">
        {status === null ? (
          <span className="stat stat-offline">server unreachable…</span>
        ) : (
          <>
            <span
              className="stat"
              title={`server started ${status.server.started_at}`}
            >
              <span className="muted">srv</span>
              <span className="mono">
                v{status.server.version} · up {fmtUptime(status.server.uptime_s)}
              </span>
            </span>

            <span
              className="stat"
              title={
                blenderOn
                  ? `connected · last seen ${status.blender.last_seen ?? "now"}`
                  : `last seen ${status.blender.last_seen ?? "never"}`
              }
            >
              <span className={`dot ${blenderOn ? "on" : ""}`} aria-hidden="true" />
              {blenderOn ? "Blender" : "Blender offline"}
              {blenderOn && blenderFile ? (
                <span className="stat-file mono" title={blenderFile}>
                  {basenameOf(blenderFile)}
                </span>
              ) : null}
            </span>

            <span
              className="stat"
              title={status.llm.chat.base_url || "chat LLM: no base URL"}
            >
              {status.llm.chat.configured ? (
                <>
                  <span className="ok-text">chat</span>
                  <span className="mono ellipsis">{status.llm.chat.model}</span>
                </>
              ) : (
                <>
                  <span className="err-text">chat</span>
                  <span className="muted">unconfigured</span>
                </>
              )}
            </span>

            <span
              className="stat"
              title={status.llm.vision.base_url || "vision LLM: no base URL"}
            >
              {status.llm.vision.configured ? (
                <>
                  <span className="ok-text">vision</span>
                  <span className="mono ellipsis">{status.llm.vision.model}</span>
                </>
              ) : (
                <>
                  <span className="err-text">vision</span>
                  <span className="muted">unconfigured</span>
                </>
              )}
            </span>

            <span
              className="stat"
              title="Agent run limits (server-enforced)"
            >
              <span className="muted">limits</span>
              <span className="mono">
                steps {status.limits.max_agent_steps} · vision{" "}
                {status.limits.max_vision_refinements}
              </span>
            </span>

            {status.debug ? (
              <span className="stat stat-debug">debug</span>
            ) : null}
          </>
        )}
      </div>

      <div className="header-actions">
        <button
          type="button"
          className="btn"
          onClick={onOpenTools}
          title="Browse the tool schemas the agent can call"
        >
          Tools
        </button>
        <button
          type="button"
          className="btn"
          onClick={onRefreshScene}
          disabled={sceneRefreshing}
          title="Ask Blender to refresh the scene snapshot"
        >
          <span className={sceneRefreshing ? "spin" : ""} aria-hidden="true">
            ↻
          </span>
          Scene
        </button>
      </div>
    </header>
  );
}
