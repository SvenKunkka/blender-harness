#!/usr/bin/env bash
# Blender Harness — one-shot setup.
# Creates a virtualenv, installs python deps and web UI deps.
set -euo pipefail
cd "$(dirname "$0")"

SKIP_WEB="${SKIP_WEB:-0}"
PYTHON="${PYTHON:-python3}"

echo "==> Creating virtualenv (.venv)"
"$PYTHON" -m venv .venv

echo "==> Installing python dependencies"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt

if [ "$SKIP_WEB" != "1" ]; then
  echo "==> Installing web UI dependencies (web_ui)"
  (cd web_ui && npm install)
else
  echo "==> SKIP_WEB=1, skipping web UI install"
fi

mkdir -p data logs
echo ""
echo "Setup complete."
echo "  Server:  .venv/bin/python -m harness_server"
echo "  Tests:   .venv/bin/python -m pytest"
echo "  Web UI:  cd web_ui && npm run dev   (or open http://127.0.0.1:9876)"
