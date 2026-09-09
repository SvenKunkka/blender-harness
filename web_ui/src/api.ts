// Typed fetch helpers for the Blender Harness API.
// All endpoints are same-origin: /api and /media are proxied by the Vite dev
// server to 127.0.0.1:9876 (see vite.config.ts).

import type {
  HistoryEntry,
  RunDetail,
  SceneInfo,
  Status,
  ToolSpec,
} from "./types";

export interface ReferenceImage {
  name: string;
  data_url: string;
}

export interface RunStarted {
  run_id: string;
}

export interface OkResult {
  ok: boolean;
  message?: string;
}

export interface LogsResponse {
  lines: string[];
}

/** Error carrying HTTP/timeout/network context for the UI toasts. */
export class ApiError extends Error {
  readonly status: number | null;
  readonly timeout: boolean;

  constructor(
    message: string,
    options: { status?: number | null; timeout?: boolean } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status ?? null;
    this.timeout = options.timeout ?? false;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 10000,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const headers = new Headers(init.headers);
  if (init.body !== undefined && init.body !== null) {
    headers.set("Content-Type", "application/json");
  }
  try {
    const response = await fetch(path, {
      ...init,
      headers,
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.text()).slice(0, 400);
      } catch {
        // ignore body read errors
      }
      throw new ApiError(
        `HTTP ${response.status} ${response.statusText}${detail ? ` — ${detail}` : ""}`,
        { status: response.status },
      );
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(`Request timed out after ${timeoutMs} ms (${path})`, {
        timeout: true,
      });
    }
    const msg = err instanceof Error ? err.message : String(err);
    throw new ApiError(`Network error requesting ${path}: ${msg}`);
  } finally {
    window.clearTimeout(timer);
  }
}

export const api = {
  getStatus: () => request<Status>("/api/status", {}, 5000),
  getTools: () => request<ToolSpec[]>("/api/tools"),

  startRun: (prompt: string, reference_images?: ReferenceImage[]) =>
    request<RunStarted>(
      "/api/run",
      {
        method: "POST",
        body: JSON.stringify(
          reference_images && reference_images.length > 0
            ? { prompt, reference_images }
            : { prompt },
        ),
      },
      15000,
    ),

  getRun: (runId: string) =>
    request<RunDetail>(
      `/api/runs/${encodeURIComponent(runId)}`,
      {},
      15000,
    ),

  stopRun: (runId: string) =>
    request<OkResult>(`/api/runs/${encodeURIComponent(runId)}/stop`, {
      method: "POST",
    }),

  getHistory: () => request<HistoryEntry[]>("/api/history"),

  undoHistory: (id: number) =>
    request<OkResult>(`/api/history/${id}/undo`, { method: "POST" }),

  restoreHistory: (id: number) =>
    request<OkResult>(`/api/history/${id}/restore`, { method: "POST" }),

  getScene: () => request<SceneInfo>("/api/scene"),

  // Triggers the server to ask Blender; may take a few seconds.
  refreshScene: () =>
    request<SceneInfo>("/api/scene/refresh", { method: "POST" }, 30000),

  getLogs: (n = 200) =>
    request<LogsResponse>(`/api/logs/latest?n=${n}`),
};

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError || err instanceof Error) {
    return err.message;
  }
  return String(err);
}

export function isTerminalRunStatus(status: string): boolean {
  return status === "finished" || status === "failed" || status === "stopped";
}

export function isRunningStatus(status: string): boolean {
  return status === "queued" || status === "running";
}
