// Shared API types — mirror the frozen Blender Harness backend contract exactly.

export type ToolRisk = "safe" | "mutating" | "destructive" | "exec";

export interface ToolSpec {
  name: string;
  description: string;
  category: string;
  risk: ToolRisk;
  parameters: Record<string, unknown>;
}

export interface Status {
  server: { version: string; uptime_s: number; started_at: string };
  blender: { connected: boolean; last_seen: string | null; file_path: string | null };
  llm: {
    chat: { configured: boolean; model: string; base_url: string };
    vision: { configured: boolean; model: string; base_url: string };
  };
  limits: { max_agent_steps: number; max_vision_refinements: number };
  debug: boolean;
}

export type PlanStatus = "pending" | "active" | "done" | "failed";

export interface PlanStep {
  label: string;
  status: PlanStatus;
}

export interface ToolLogEntry {
  ts: string;
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  error: string | null;
  duration_ms: number | null;
}

export type ChatRole = "user" | "assistant" | "system";

export interface ChatMsg {
  role: ChatRole;
  content: string;
  ts: string;
}

export type VisionVerdict = "PASS" | "REFINE" | "SKIPPED";

export interface VisionReview {
  round: number;
  verdict: VisionVerdict;
  issues: string[];
  comment: string;
  image_urls: string[];
}

export type RunStatus = "queued" | "running" | "finished" | "failed" | "stopped";

export interface RunDetail {
  run_id: string;
  status: RunStatus;
  prompt: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  summary: string | null;
  plan: PlanStep[];
  tool_log: ToolLogEntry[];
  messages: ChatMsg[];
  screenshot_url: string | null;
  vision: VisionReview[];
  checkpoint_id: string | null;
  objects_affected: string[];
}

export type HistoryStatus = "done" | "undone" | "failed";

export interface HistoryEntry {
  id: number;
  seq: number;
  run_id: string | null;
  prompt: string;
  timestamp: string;
  status: HistoryStatus;
  summary: string | null;
  tool_count: number;
  screenshot_url: string | null;
  objects_affected: string[];
}

export interface SceneNode {
  id: string;
  name: string;
  type: string;
  collection: string;
  visible: boolean;
  selectable: boolean;
}

export interface SceneInfo {
  summary: {
    object_count: number;
    active_object: string | null;
    selected: string[];
    collections: string[];
    camera: string | null;
    lights: number;
    file_path: string | null;
    unit: { system: string; scale: number };
  } | null;
  objects: SceneNode[];
  fetched_at: string | null;
}

export type LogLine = string;
