# Blender Harness

**AI-native Blender harness — natural-language 3D editing with structured tools,
scene awareness, visual feedback and full history/undo.**

Blender Harness is not "a ChatGPT panel inside Blender". It is an agent harness:

```
user prompt → read the real Blender scene → plan → structured tool calls → modify → screenshot → vision review → refine → history step → undo/restore
```

A zero-experience user types things like *"make a 75% keyboard base, 325 × 145 ×
18 mm, corner radius 6 mm"* — the agent inspects the current scene, decides what
to build, drives Blender through ~70 structured tools, renders screenshots,
verifies them with a vision model, and records every AI step so it can be undone
with one click.

---

## What's in the box

| Component | Technology | Role |
|---|---|---|
| `blender_addon/` | Python + `bpy` only (stdlib WebSocket client, no deps) | installable add-on: N-panel **AI Harness**, structured tool handlers, mm/degree unit layer, stable object ids, checkpoints |
| `harness_server/` | Python 3.11+, FastAPI, asyncio, Pydantic, SQLite | WebSocket hub for Blender, agent loop, LLM + vision providers, tool registry (JSON Schemas), history store, REST API |
| `web_ui/` | React + TypeScript + Vite | chat / tool log / history / screenshots / scene tree / settings UI |
| `scripts/`, `examples/`, `tests/` | Python, pytest, real headless Blender | smoke + E2E tests, demo prompts, install helpers |

Communication is deliberately decoupled: **Blender connects out** to the harness
server over WebSocket (`ws://127.0.0.1:9876/ws/blender`), with auto-reconnect,
ping/pong and request/response correlation. The server never runs inside Blender.

---

## Features

- **Scene awareness** — the agent reads `get_scene_summary` / `get_objects`
  before touching anything; every object has a *stable id* (`obj_00001`) stored
  on the object, so renames never break references.
- **~70 structured tools with JSON Schemas** across `scene`, `transform`, `mesh`,
  `modifier`, `material`, `camera`, `render`, `file`, `history`, `python`,
  and product-design helpers (rounded box, shell, cutout, holes, wall thickness,
  keyboard case / mouse volume / knob generators, measure/center/align/mirror).
- **One unit system** — the AI always speaks **millimetres and degrees**;
  conversion to Blender metres/radians happens at the tool boundary.
- **Real agent loop** — reads scene → acts → screenshots (`EEVEE` renders from
  several angles) → vision review (PASS / REFINE) → auto-refine up to
  `MAX_VISION_REFINEMENTS` → history step → summary. Hard step budget
  (`MAX_AGENT_STEPS`) prevents infinite loops.
- **History / undo** — every mutating AI run snapshots the scene before and
  after (`.blend` copies). Each run becomes a history row; Undo restores the
  before-checkpoint, Restore reloads the after-checkpoint.
- **Safety rails** — automatic checkpoint before the first destructive change;
  `delete_object`/`apply_modifier` are flagged `destructive`; `execute_blender_python`
  is **off by default** and sandboxed (AST import whitelist, banned builtins,
  no subprocess/os/shell/file access, size + soft-time caps).
- **Provider abstraction** — any OpenAI-compatible endpoint: OpenAI, DeepSeek,
  Qwen, OpenRouter, LM Studio, Ollama, vLLM. Vision model is independently
  configurable and cleanly skipped when absent.
- **Observability** — per-tool log with timings, debug log tail in the panel,
  `logs/harness.log`, history in SQLite (`data/harness.db`).

---

## Architecture

```
┌────────────┐   WebSocket (JSON, auto-reconnect)    ┌──────────────────────┐
│   Blender  │ ─────────────────────────────────────▶ │   Harness Server     │
│  add-on    │   hello / tool_call / tool_result      │  FastAPI :9876       │
│  (client)  │ ◀───────────────────────────────────── │   WS hub (Blender)   │
│            │   hello_ack / ping / tool_call         │   Agent loop         │
└────────────┘                                        │   LLM provider       │
        ▲                                             │   Vision reviewer    │
        │ structured tools only                       │   Tool registry      │
        ▼                                             │   History (SQLite)   │
  bpy scene / renderers / checkpoints                 └──────────┬───────────┘
                                                                 │ REST /api/*
                                                   ┌────────────▼───────────┐
                                                   │   Web UI (React+Vite)  │
                                                   │   chat • tool log      │
                                                   │   history • screenshots│
                                                   └────────────────────────┘
```

Data flow for one request:
1. Web UI (or the add-on panel) → `POST /api/run {prompt}`.
2. The agent builds a system prompt + your prompt, then loops:
   `LLM(tools=registry)` → tool call → the server forwards it over the Blender
   WebSocket → the add-on executes on Blender's main thread → structured result
   → back to the LLM.
3. After mutations the server asks Blender to render screenshots and the vision
   model judges PASS / REFINE; on REFINE the loop continues (max 3 refinements).
4. A history row (before/after checkpoints, tool log, screenshot, summary) is
   written. Undo/Restore call the Blender checkpoint restore tool.

---

## Requirements

- **Blender 4.0+** (tested on Blender 5.1) — macOS / Windows / Linux
- **Python 3.11+**
- **Node.js 18+** (for the Web UI; optional — the server also serves a built UI)
- An OpenAI-compatible API (or a local Ollama / LM Studio)

## Quick start

```bash
git clone <this repo> && cd blender-harness
./setup.sh                 # venv + python deps + web_ui npm install
cp .env.example .env       # configure AI_* (see below)
```

Start the backend:

```bash
.venv/bin/python -m harness_server        # or: make run
# logs to logs/harness.log; REST on http://127.0.0.1:9876
```

Start the Web UI (development):

```bash
cd web_ui && npm run dev                  # http://127.0.0.1:5173
# (production: npm run build, then just open http://127.0.0.1:9876)
```

### Install the Blender add-on

1. Edit → Preferences → Add-ons → **Install…**
2. Choose `dist/blender_harness_addon.zip`
   (rebuild after changes with `make addon-zip` or `scripts/package_addon.sh`).
3. Enable **Blender Harness** (category *Development*).
4. In the 3D viewport open the N panel (press `N`) → **AI Harness** tab.
5. Keep the default `127.0.0.1 : 9876`, press **Connect** (auto-reconnects).
   Status turns to `connected`.

You can drive everything from the panel (Read Scene, Shot, Ckpt, prompt Run,
history undo) — the full chat UI with screenshots lives in the browser.

## Configure the AI

Everything is environment variables (`.env`). Point it at any OpenAI-compatible
endpoint:

```ini
# DeepSeek
AI_BASE_URL=https://api.deepseek.com/v1
AI_API_KEY=sk-...
AI_MODEL=deepseek-chat

# Qwen (compatible mode)
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_API_KEY=sk-...
AI_MODEL=qwen-plus

# Ollama (local — any key works)
AI_BASE_URL=http://127.0.0.1:11434/v1
AI_API_KEY=ollama
AI_MODEL=llama3.1

# Vision review (optional; falls back to AI_MODEL when it supports images)
AI_VISION_MODEL=qwen-vl-max

# Agent limits
MAX_AGENT_STEPS=20
MAX_VISION_REFINEMENTS=3
ALLOW_EXECUTE_PYTHON=false     # keep false unless you really need raw scripts
```

The API key is never hard-coded and the web UI never sees it — it stays in the
backend environment.

## Example prompts

```
Create a 75% keyboard base: 325 × 145 × 18 mm, corner radius 6 mm.
Create a mouse concept: length 120 mm, width 64 mm, height 39 mm; the highest
  point roughly 45 mm from the rear.
Take the selected enclosure and: increase width by 2 mm, keep length unchanged,
  add a 1.5 mm bevel.
Create three variants of the selected object: A original height, B height -2mm,
  C height +2mm; arrange them side by side.
Round the top corners of the selected part to R3, keep the bottom sharp.
```

More demos live in `examples/demo-prompts.md`.

## Tests

```bash
make test                       # or: .venv/bin/python -m pytest
.venv/bin/python scripts/blender_smoke.py        # real headless Blender check
.venv/bin/python scripts/integration_e2e.py      # Blender ↔ server ↔ agent E2E
```

Unit coverage: unit conversion (mm/deg), tool JSON-Schema validation + LLM
payloads, scene serialization & stable ids (mock bpy), history store &
checkpoints, LLM provider & vision reviewer, full agent loop (fake LLM + fake
Blender session), add-on WebSocket codec, REST + WebSocket endpoints, sandboxed
Python executor, and parity between server tool registry and add-on handlers.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Add-on shows `disconnected` | Is the server running? Check `host:port` in the AI Harness panel, press Connect again (auto-reconnect is on). |
| `BLENDER_NOT_CONNECTED` tool errors | Enable + Connect the add-on first; the agent then re-reads the scene. |
| Web UI can't reach the API | The Vite dev proxy expects the server on `127.0.0.1:9876`. |
| Run fails with "LLM not configured" | Set `AI_MODEL` (and `AI_BASE_URL`/`AI_API_KEY`) in `.env`, restart server. |
| Screenshots are missing/black | EEVEE renders need a GPU/GL context; render from the GUI session, not headless CI. |
| Boolean apply reports a soft failure | Headless contexts sometimes can't run `modifier_apply`; the modifier is kept and reported instead of failing silently. |
| Blender undo appears as a full file reload | Checkpoint restore opens the snapshot `.blend`; large checkpoints are the price of reliable undo. |

## Security notes

- The add-on only talks to the configured local server; no telemetry, no cloud
  Blender data.
- Raw Python execution (`execute_blender_python`) is **disabled by default** and
  sandboxed even when enabled. Prefer the structured tools.
- The harness cannot delete files outside Blender's own save operations, cannot
  run subprocesses, and every destructive scene change goes through a checkpoint.

## Roadmap

- Reference-image upload → view-based 3D modelling (`reference_images` field is
  already plumbed through the run API).
- Per-object diff preview in history (before/after thumbnails).
- Multi-angle turntable renders + configurable product-shot presets.
- Scene-graph streaming updates (no poll) and longer-lived chat memory.
- Multi-user sessions / remote Blender instances (e.g. a farm).
- Modifier-parameter timeline scrubbing ("try bevel 2 / 3 / 4 mm").

## License

MIT — see `LICENSE`.
