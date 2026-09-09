import { useEffect, useMemo, useState } from "react";
import type { ToolRisk, ToolSpec } from "../types";

export interface ToolSpecModalProps {
  open: boolean;
  tools: ToolSpec[];
  onClose: () => void;
}

const KNOWN_CATEGORY_ORDER = [
  "scene",
  "transform",
  "mesh",
  "modifier",
  "material",
  "camera",
  "render",
  "file",
  "history",
  "product",
  "python",
];

const RISK_CLASS: Record<ToolRisk, string> = {
  safe: "risk-safe",
  mutating: "risk-mutating",
  destructive: "risk-destructive",
  exec: "risk-exec",
};

export function ToolSpecModal({ open, tools, onClose }: ToolSpecModalProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Reset local filters each time the modal opens.
  useEffect(() => {
    if (open) {
      setQuery("");
      setCategory(null);
      setExpanded(null);
    }
  }, [open]);

  const categories = useMemo(() => {
    const present = new Set(tools.map((t) => t.category));
    const known = KNOWN_CATEGORY_ORDER.filter((c) => present.has(c));
    const rest = [...present]
      .filter((c) => !KNOWN_CATEGORY_ORDER.includes(c))
      .sort();
    return [...known, ...rest];
  }, [tools]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tools.filter((t) => {
      if (category !== null && t.category !== category) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.category.toLowerCase().includes(q)
      );
    });
  }, [tools, query, category]);

  if (!open) return null;

  return (
    <div className="modal-back" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Agent tools"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <span className="panel-title">Agent tools</span>
          <span className="muted small mono">{tools.length} registered</span>
          <span className="head-spacer" />
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label="Close"
            title="Close"
          >
            ✕
          </button>
        </div>

        <div className="modal-toolbar">
          <input
            className="tool-search"
            type="search"
            placeholder="Filter tools by name, description or category…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <div className="cat-badges">
            <button
              type="button"
              className={`cat-badge ${category === null ? "cat-on" : ""}`}
              onClick={() => setCategory(null)}
            >
              all <span className="count-badge mono">{tools.length}</span>
            </button>
            {categories.map((cat) => {
              const count = tools.filter((t) => t.category === cat).length;
              return (
                <button
                  type="button"
                  key={cat}
                  className={`cat-badge ${category === cat ? "cat-on" : ""}`}
                  onClick={() => setCategory(category === cat ? null : cat)}
                >
                  {cat} <span className="count-badge mono">{count}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="modal-body">
          {filtered.length === 0 ? (
            <div className="panel-hint">
              No tools match “{query}”. Try clearing the filter.
            </div>
          ) : (
            filtered.map((tool) => {
              const isOpen = expanded === tool.name;
              return (
                <div key={tool.name} className="tool-row">
                  <button
                    type="button"
                    className="tool-row-head"
                    onClick={() => setExpanded(isOpen ? null : tool.name)}
                  >
                    <span className="tool-caret mono" aria-hidden="true">
                      {isOpen ? "▾" : "▸"}
                    </span>
                    <span className="tool-name mono">{tool.name}</span>
                    <span className={`risk ${RISK_CLASS[tool.risk]}`}>
                      {tool.risk}
                    </span>
                    <span className="tool-cat muted">{tool.category}</span>
                    <span className="tool-desc">{tool.description}</span>
                  </button>
                  {isOpen ? (
                    <div className="tool-detail">
                      <div className="tool-detail-label mono">
                        parameters (JSON schema)
                      </div>
                      <pre className="tool-json">{JSON.stringify(tool.parameters, null, 2)}</pre>
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </div>

        <div className="modal-foot muted small">
          {filtered.length} / {tools.length} shown · risk:{" "}
          <span className="risk risk-safe">safe</span>{" "}
          <span className="risk risk-mutating">mutating</span>{" "}
          <span className="risk risk-destructive">destructive</span>{" "}
          <span className="risk risk-exec">exec</span>
        </div>
      </div>
    </div>
  );
}
