PYTHON ?= python3
VENV    = .venv
PIP     = $(VENV)/bin/pip
PY      = $(VENV)/bin/python

.PHONY: help install dev test lint addon-zip web-install web-dev run clean

help:
	@echo "Blender Harness — make targets"
	@echo "  make install     create .venv and install python + web deps"
	@echo "  make dev         run harness server with auto-reload"
	@echo "  make run         run harness server (no reload)"
	@echo "  make test        run the pytest suite"
	@echo "  make web-install install web_ui npm dependencies"
	@echo "  make web-dev     run Vite dev server (http://127.0.0.1:5173)"
	@echo "  make addon-zip   package the Blender add-on into dist/"
	@echo "  make clean       remove venv/build artifacts"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	@cd web_ui && npm install

dev: $(VENV)
	$(PY) -m harness_server --reload

run: $(VENV)
	$(PY) -m harness_server

test: $(VENV)
	$(PY) -m pytest -q

web-install:
	@cd web_ui && npm install

web-dev:
	@cd web_ui && npm run dev

addon-zip:
	@mkdir -p dist && rm -f dist/blender_harness_addon.zip
	@cd . && zip -r dist/blender_harness_addon.zip blender_addon -x "*__pycache__*" "*.pyc"
	@echo "Created dist/blender_harness_addon.zip"

clean:
	rm -rf $(VENV) .pytest_cache
	rm -rf web_ui/node_modules web_ui/dist
	rm -rf data logs dist
