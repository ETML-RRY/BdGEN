APP_DIR := bdgen
WEB_DIR := $(APP_DIR)/web
DESKTOP_DIR := $(APP_DIR)/desktop
BUILD_DIR := build
BACKEND_DIST := $(BUILD_DIR)/backend
BACKEND_EXE := $(BACKEND_DIST)/bdgen-server.exe
PORTABLE_DIST := $(BUILD_DIR)/portable

# Keep Python dependencies in the workspace-level virtual environment.
# This avoids uv trying to repair/remove the stale bdgen/.venv environment while
# the IDE has the root .venv active.
export UV_PROJECT_ENVIRONMENT := ../.venv

.PHONY: help build portable sync frontend backend desktop test dev-desktop clean

help:
	@echo "BdGEN build targets"
	@echo "  make build        Build the portable Windows exe"
	@echo "  make portable     Build the portable Windows exe"
	@echo "  make frontend     Build the React frontend into FastAPI static assets"
	@echo "  make backend      Build the local FastAPI server executable with PyInstaller"
	@echo "  make desktop      Build the portable Electron executable"
	@echo "  make test         Run Python tests"
	@echo "  make dev-desktop  Start Electron in development mode"
	@echo "  make clean        Remove build outputs"

build: portable

portable: sync frontend backend desktop
	@echo "Portable build complete. Check $(PORTABLE_DIST) for the portable executable."

sync:
	cd $(APP_DIR) && uv sync

frontend:
	cd $(WEB_DIR) && npm install && npm run build

backend: frontend
	cd $(APP_DIR) && uv run pyinstaller --distpath ../$(BACKEND_DIST) --workpath ../$(BUILD_DIR)/pyinstaller-work bdgen-server.spec
	powershell -NoProfile -Command "if (!(Test-Path -LiteralPath '$(BACKEND_EXE)')) { Write-Error 'Missing backend executable: $(BACKEND_EXE)'; exit 1 }"

desktop: backend
	cd $(DESKTOP_DIR) && npm install && npm run build:portable

test:
	cd $(APP_DIR) && uv run python -m unittest discover -s tests

dev-desktop: frontend
	cd $(DESKTOP_DIR) && npm install && npm run dev

clean:
	powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue '$(BUILD_DIR)','$(APP_DIR)/build','$(APP_DIR)/dist','$(DESKTOP_DIR)/build','$(DESKTOP_DIR)/dist','dist'"
