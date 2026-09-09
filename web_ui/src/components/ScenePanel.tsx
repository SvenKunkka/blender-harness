import { useState } from "react";
import type { SceneInfo, SceneNode } from "../types";
import { basenameOf, valueToText } from "../format";

export interface ScenePanelProps {
  scene: SceneInfo | null;
  refreshing: boolean;
  onRefresh: () => void;
}

type Tab = "scene" | "selection";

function pickActiveObject(scene: SceneInfo): SceneNode | null {
  const selected = scene.summary?.selected ?? [];
  const objs = scene.objects;
  if (selected.length > 0) {
    const hit = objs.find((o) => o.id === selected[0] || o.name === selected[0]);
    if (hit) return hit;
  }
  const active = scene.summary?.active_object ?? null;
  if (active) {
    const hit = objs.find((o) => o.id === active || o.name === active);
    if (hit) return hit;
  }
  return null;
}

export function ScenePanel({ scene, refreshing, onRefresh }: ScenePanelProps) {
  const [tab, setTab] = useState<Tab>("scene");

  const summary = scene?.summary ?? null;
  const selectedIds = new Set(summary?.selected ?? []);

  const groups = new Map<string, SceneNode[]>();
  for (const obj of scene?.objects ?? []) {
    const col = obj.collection || "(no collection)";
    const list = groups.get(col);
    if (list) list.push(obj);
    else groups.set(col, [obj]);
  }
  // Include collections declared by the summary even when they hold no cached objects.
  for (const col of summary?.collections ?? []) {
    if (!groups.has(col)) groups.set(col, []);
  }

  const activeObject = scene ? pickActiveObject(scene) : null;

  return (
    <section className="panel scene-panel" aria-label="Scene inspector">
      <div className="panel-head">
        <div className="tabs">
          <button
            type="button"
            className={`tab ${tab === "scene" ? "tab-on" : ""}`}
            onClick={() => setTab("scene")}
          >
            Scene
          </button>
          <button
            type="button"
            className={`tab ${tab === "selection" ? "tab-on" : ""}`}
            onClick={() => setTab("selection")}
          >
            Selection
          </button>
        </div>
        <span className="head-spacer" />
        {scene?.fetched_at ? (
          <span className="muted small mono" title={scene.fetched_at}>
            {new Date(scene.fetched_at).toLocaleTimeString([], { hour12: false })}
          </span>
        ) : null}
        <button
          type="button"
          className="btn btn-sm"
          onClick={onRefresh}
          disabled={refreshing}
          title="Ask Blender to refresh the scene snapshot (may take seconds)"
        >
          <span className={refreshing ? "spin" : ""} aria-hidden="true">
            ↻
          </span>
          Refresh
        </button>
      </div>

      {tab === "scene" ? (
        <div className="panel-body scene-body">
          {scene === null ? (
            <div className="panel-hint">
              Loading scene snapshot… (this app talks to the harness server on
              port 9876).
            </div>
          ) : summary === null && scene.objects.length === 0 ? (
            <div className="panel-hint">
              <p>
                No scene snapshot yet — Blender has not been asked for the scene.
              </p>
              <p className="muted small">
                Press <b>Refresh</b> above; the server queries Blender (this can
                take a few seconds) and the object tree will appear here.
              </p>
            </div>
          ) : (
            <>
              {summary ? (
                <div className="scene-summary">
                  <span className="muted">objects</span>
                  <b>{summary.object_count}</b>
                  <span className="muted">camera</span>
                  <span className="mono">{summary.camera ?? "—"}</span>
                  <span className="muted">lights</span>
                  <b>{summary.lights}</b>
                  <span className="muted">unit</span>
                  <span className="mono">
                    {summary.unit.system} ×{summary.unit.scale}
                  </span>
                  {summary.file_path ? (
                    <span className="scene-file mono" title={summary.file_path}>
                      {basenameOf(summary.file_path)}
                    </span>
                  ) : null}
                </div>
              ) : null}

              {groups.size === 0 ? (
                <div className="panel-hint">Scene is empty.</div>
              ) : (
                <div className="scene-tree">
                  {[...groups.entries()].map(([col, objs]) => (
                    <div key={col} className="col-group">
                      <div className="col-head">
                        <span className="col-caret" aria-hidden="true">
                          ▾
                        </span>
                        <span className="col-name">{col}</span>
                        <span className="count-badge mono">{objs.length}</span>
                      </div>
                      {objs.length === 0 ? (
                        <div className="col-empty muted small">no objects listed</div>
                      ) : (
                        objs.map((obj) => {
                          const isSelected = selectedIds.has(obj.id) || selectedIds.has(obj.name);
                          return (
                            <div
                              key={obj.id || obj.name}
                              className={`obj-row ${isSelected ? "selected" : ""} ${obj.visible ? "" : "obj-hidden"}`}
                            >
                              <span className="obj-dot" aria-hidden="true">
                                {isSelected ? "●" : "○"}
                              </span>
                              <span className="obj-name" title={obj.name}>
                                {obj.name}
                              </span>
                              <span className="obj-type mono">{obj.type}</span>
                              <span className="obj-id mono muted" title={obj.id}>
                                {obj.id.length > 24 ? `${obj.id.slice(0, 24)}…` : obj.id}
                              </span>
                              {!obj.selectable ? (
                                <span className="muted small" title="not selectable">
                                  🔒
                                </span>
                              ) : null}
                            </div>
                          );
                        })
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      ) : (
        <div className="panel-body scene-body">
          {activeObject ? (
            <ObjectDetail
              obj={activeObject}
              context={
                (summary?.selected ?? []).length > 0
                  ? `from selection (${summary?.selected.length} selected)`
                  : "active object"
              }
            />
          ) : (
            <div className="panel-hint">
              Nothing selected. Select an object in Blender (or ask the agent to
              select one), then refresh the scene — its details will show here.
            </div>
          )}
        </div>
      )}
    </section>
  );
}

const FIELD_ORDER: { key: keyof SceneNode; label: string }[] = [
  { key: "name", label: "name" },
  { key: "id", label: "id" },
  { key: "type", label: "type" },
  { key: "collection", label: "collection" },
  { key: "visible", label: "visible" },
  { key: "selectable", label: "selectable" },
];

function ObjectDetail({ obj, context }: { obj: SceneNode; context: string }) {
  return (
    <div className="object-detail">
      <div className="od-head">
        <span className="od-name" title={obj.name}>
          {obj.name}
        </span>
        <span className="od-type mono">{obj.type}</span>
        <span className="muted small">{context}</span>
      </div>
      <div className="kv">
        {FIELD_ORDER.map(({ key, label }) => (
          <div className="kv-row" key={key}>
            <span className="kv-key mono">{label}</span>
            <span className="kv-val" title={valueToText(obj[key])}>
              {valueToText(obj[key])}
            </span>
          </div>
        ))}
      </div>
      <p className="muted small kv-note">
        Rendered from the raw scene snapshot cached by the server
        (get_object_details → objects[]).
      </p>
    </div>
  );
}
