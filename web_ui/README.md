# Blender Harness — Web UI

React + TypeScript + Vite single-page app for the **Blender Harness** agent:
an AI agent that drives Blender from natural-language prompts and streams its
plan, tool calls, chat messages and viewport screenshots back to this UI.

The UI is a pure client: it talks to the harness API server over `/api` and
`/media`, which the Vite dev server proxies to `http://127.0.0.1:9876`.

## Run

```bash
npm install        # once
npm run dev        # start Vite dev server on http://localhost:5173
```

Start the harness API server first (port 9876), otherwise the header shows
"server unreachable".

## Build (type-check + production bundle)

```bash
npm run build      # tsc -b && vite build  →  dist/
npm run preview    # serve the production build
```

## Layout

- **Header / status bar** — server version + uptime, Blender connection,
  chat/vision LLM config, agent limits, scene refresh, Tools browser.
- **Left column** — run chat (streams messages, plan chips, result card) above
  a bottom drawer with **Tool log** / **History** tabs.
- **Right column** — viewport screenshot + vision reviews, and the scene
  inspector (**Scene** tree / **Selection** details).

## Project structure

```
index.html            Vite entry, dark base
src/main.tsx          React root
src/App.tsx           state + polling drivers (status 2s, run 700ms, history 3s)
src/App.css           hand-written dark theme (no UI framework)
src/types.ts          frozen API contract types
src/api.ts            typed fetch helpers with timeouts
src/format.ts         time/duration helpers
src/components/…      StatusBar, ChatPanel, ToolLogPanel, HistoryPanel,
                      ScreenshotPanel, ScenePanel, ToolSpecModal, Toast
```
