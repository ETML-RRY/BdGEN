APP_DIR := bdgen
WEB_DIR := $(APP_DIR)/web
DESKTOP_DIR := $(APP_DIR)/desktop
BUILD_DIR := build
BACKEND_DIST := $(BUILD_DIR)/backend
BACKEND_EXE := $(BACKEND_DIST)/bdgen-server.exe
BACKEND_BIN := $(BACKEND_DIST)/bdgen-server
PORTABLE_DIST := $(BUILD_DIR)/portable
MAC_DIST := $(BUILD_DIR)/mac
LINUX_DIST := $(BUILD_DIR)/linux
ROOT_DIR := $(CURDIR)

# Keep Python dependencies in the workspace-level virtual environment.
# This avoids uv trying to repair/remove the stale bdgen/.venv environment while
# the IDE has the root .venv active.
export UV_PROJECT_ENVIRONMENT := $(ROOT_DIR)/.venv

.PHONY: help build portable macos linux sync frontend backend backend-windows backend-unix desktop desktop-windows desktop-macos desktop-linux lint lint-backend lint-frontend lint-desktop format format-backend format-frontend format-desktop format-check format-check-backend format-check-frontend format-check-desktop test test-backend test-frontend test-cov dev-desktop clean

help:
	@echo "BdGEN build targets"
	@echo "  make build        Build the portable Windows exe"
	@echo "  make portable     Build the portable Windows exe"
	@echo "  make macos        Build the unsigned macOS DMG"
	@echo "  make linux        Build the Linux desktop artifact"
	@echo "  make frontend     Build the React frontend into FastAPI static assets"
	@echo "  make backend      Build the local FastAPI server executable with PyInstaller"
	@echo "  make desktop      Build the portable Electron executable"
	@echo "  make lint         Run backend, frontend, and desktop linters"
	@echo "  make format       Format backend, frontend, and desktop code"
	@echo "  make format-check Check backend, frontend, and desktop formatting"
	@echo "  make test         Run backend and frontend tests"
	@echo "  make test-backend Run pytest"
	@echo "  make test-frontend Run vitest"
	@echo "  make test-cov     Run pytest with coverage report"
	@echo "  make dev-desktop  Start Electron in development mode"
	@echo "  make clean        Remove build outputs"

build: portable

portable: sync frontend backend desktop
	@echo "Portable build complete. Check $(PORTABLE_DIST) for the portable executable."

macos: sync frontend backend-unix desktop-macos
	@echo "macOS build complete. Check $(MAC_DIST) for the DMG."

linux: sync frontend backend-unix desktop-linux
	@echo "Linux build complete. Check $(LINUX_DIST) for the desktop artifact."

sync:
	cd $(APP_DIR) && uv sync

frontend:
	cd $(WEB_DIR) && npm install && npm run build

backend: backend-windows

backend-windows: frontend
	cd $(APP_DIR) && uv run pyinstaller --distpath ../$(BACKEND_DIST) --workpath ../$(BUILD_DIR)/pyinstaller-work bdgen-server.spec
	powershell -NoProfile -Command "if (!(Test-Path -LiteralPath '$(BACKEND_EXE)')) { Write-Error 'Missing backend executable: $(BACKEND_EXE)'; exit 1 }"

backend-unix: frontend
	cd $(APP_DIR) && uv run pyinstaller --distpath ../$(BACKEND_DIST) --workpath ../$(BUILD_DIR)/pyinstaller-work bdgen-server.spec
	test -f $(BACKEND_BIN)
	chmod +x $(BACKEND_BIN)
	if [ "$$(uname -s)" = "Darwin" ]; then codesign --force --sign - $(BACKEND_BIN); fi

desktop: desktop-windows

desktop-windows: backend-windows
	cd $(DESKTOP_DIR) && npm install && npm run build:windows

desktop-macos: backend-unix
	cd $(DESKTOP_DIR) && npm install && npm run build:mac

desktop-linux: backend-unix
	cd $(DESKTOP_DIR) && npm install && npm run build:linux

lint: lint-backend lint-frontend lint-desktop

lint-backend:
	cd $(APP_DIR) && uv run ruff check .

lint-frontend:
	cd $(WEB_DIR) && npm run lint

lint-desktop:
	cd $(DESKTOP_DIR) && npm run lint

format: format-backend format-frontend format-desktop

format-backend:
	cd $(APP_DIR) && uv run ruff format .

format-frontend:
	cd $(WEB_DIR) && npm run format

format-desktop:
	cd $(DESKTOP_DIR) && npm run format

format-check: format-check-backend format-check-frontend format-check-desktop

format-check-backend:
	cd $(APP_DIR) && uv run ruff format --check .

format-check-frontend:
	cd $(WEB_DIR) && npm run format:check

format-check-desktop:
	cd $(DESKTOP_DIR) && npm run format:check

test: test-backend test-frontend

test-backend:
	cd $(APP_DIR) && uv run pytest

test-frontend:
	cd $(WEB_DIR) && npm test

test-cov:
	cd $(APP_DIR) && uv run pytest --cov --cov-report=term-missing --cov-report=html

dev-desktop: frontend
ifeq ($(OS),Windows_NT)
	cd $(DESKTOP_DIR) && npm install && npm rebuild electron && set "BDGEN_BACKEND_CMD=uv" && set "BDGEN_BACKEND_ARGS=--directory .. run python -m bdgen.server" && npm run dev
else
	cd $(DESKTOP_DIR) && npm install && npm rebuild electron && BDGEN_BACKEND_CMD=uv BDGEN_BACKEND_ARGS="--directory .. run python -m bdgen.server" npm run dev
endif

clean:
	powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue '$(BUILD_DIR)','$(APP_DIR)/build','$(APP_DIR)/dist','$(DESKTOP_DIR)/build','$(DESKTOP_DIR)/dist','dist'"
