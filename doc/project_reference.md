# BdGEN - Project Reference

This file is the working reference for future operations in this project.
Update it on every code, configuration, documentation, or workflow change.

Last updated: 2026-05-05 (5)

## Update Rule

- Before changing files, read this document and the files relevant to the task.
- After every modification, update the "Change Log" section with the date, files touched, and the useful context for the next operation.
- Keep this file concise and operational: architecture, commands, conventions, risks, and recent decisions.

## Workspace Map

- Root workspace: `C:\Users\ps88cre\LAB\BdGen`
- Main application: `bdgen/`
- Existing planning note: `next_steps.md`
- Root image asset: `bd_gen_logo.png`
- Project reference docs: `doc/`

## Application Overview

BdGEN generates comic books from a JSON project description.

Main pipeline:

1. `script`: expands the user configuration into `bdgen-script.json` with an LLM.
2. `references`: generates visual reference sheets for characters, locations, and objects.
3. `compose`: generates final pages, cover/back cover, and assembles the PDF.
4. `upscale`: optional local/Replicate-backed upscale step for composed images.

Generated projects are stored under `output/<project>/` by convention.

## Backend

- Package root: `bdgen/bdgen/`
- CLI entry point: `bdgen/bdgen/cli.py`
- Pydantic models and path conventions: `bdgen/bdgen/models.py`
- Pipeline modules:
  - `script.py`
  - `references.py`
  - `compose.py`
  - `upscale.py`
  - `wizard.py`
- Service layer for web/API workflows: `bdgen/bdgen/service.py`
- FastAPI app: `bdgen/bdgen/server/app.py`
- Job manager/SSE state: `bdgen/bdgen/server/jobs.py`

Important backend conventions:

- `BdGenInput.load()` fills default output paths from `project` and `output_root`.
- `BdGenScript.load()` enforces generated paths relative to the script's project directory.
- Project files are expected to live together: `bdgen.json`, `bdgen-script.json`, `references/`, `pages/`, `pages_upscaled/`, and the final PDF.
- Per-project generation telemetry is stored in `bdgen-stats.json`.
- The web server uses `BDGEN_OUTPUT_ROOT` when set, otherwise `./output`.

## Frontend

- Frontend root: `bdgen/web/`
- Framework: Vite + React 18
- Main routes: `bdgen/web/src/App.jsx`
- Pages:
  - `Home.jsx`
  - `NewProject.jsx`
  - `Wizard.jsx`
- API client: `bdgen/web/src/api.js`
- Wizard components and step UIs live under `bdgen/web/src/components/`.
- Project statistics page: `bdgen/web/src/pages/ProjectStats.jsx`, routed at `/projects/:name/stats`.

## Statistics

- Stats module: `bdgen/bdgen/stats.py`
- Project stats file: `output/<project>/bdgen-stats.json`
- API endpoint: `GET /api/projects/{name}/statistics`
- Captured events include step, target id/kind, operation, provider, model, elapsed time, prompt size, input image count, token usage when exposed by the provider, and approximate USD cost when a local price table can estimate it.
- Structural stats are computed from `bdgen-script.json`: pages, panels, dialogs/bubbles, generated words, characters, locations, objects, expected/generated references, references used, composed images, and upscaled images.
- Cost estimates are approximate and depend on provider usage data. Image calls that do not expose token usage still record duration and metadata but may have no cost estimate.

## Commands

From the workspace root:

```bash
make build
make portable
make macos
make linux
make frontend
make backend
make desktop
make lint
make format
make format-check
make test
make dev-desktop
make clean
```

Desktop builds are platform-specific. `make build`, `make portable`, and
`make desktop` still produce the portable Windows executable under
`build/portable/`. `make macos` produces an unsigned DMG under `build/mac/`.
`make linux` produces a Linux AppImage under `build/linux/`.
macOS and Linux backend binaries are named `bdgen-server` without the Windows
`.exe` extension.

From `bdgen/`:

```bash
uv sync
uv run main.py wizard <project.json>
uv run main.py run <project.json>
uv run main.py script <project.json>
uv run main.py references ./output/<project>/bdgen-script.json
uv run main.py compose ./output/<project>/bdgen-script.json
uv run main.py upscale ./output/<project>/bdgen-script.json
uv run python -m unittest
uv run python -m bdgen.server
```

Frontend:

```bash
cd bdgen/web
npm install
npm run build
npm run dev
npm run lint
npm run format
npm run format:check
```

Desktop:

```bash
cd bdgen/desktop
npm run lint
npm run format
npm run format:check
```

## Configuration And Dependencies

- Python metadata: `bdgen/pyproject.toml`
- Python lockfile: `bdgen/uv.lock`
- Environment template: `bdgen/.env.sample`
- Local environment: `bdgen/.env` (do not expose secrets)
- Frontend package metadata: `bdgen/web/package.json`

Python dependencies currently include Pydantic, OpenAI, Anthropic, Pillow, Replicate, python-dotenv, FastAPI, Uvicorn, and python-multipart.

Frontend dependencies currently include React, React Router, React Icons, Tailwind/Vite tooling.

Lint/format tooling:

- Backend: Ruff via `uv run ruff check .` and `uv run ruff format .`; initial lint profile is intentionally limited to critical checks while existing style debt remains.
- Frontend: ESLint flat config and Prettier via `bdgen/web/package.json` scripts.
- Desktop: ESLint flat config and Prettier via `bdgen/desktop/package.json` scripts.

## Tests

- Current visible test file: `bdgen/tests/test_upscale.py`
- Existing test style uses `unittest`, `tempfile`, and `unittest.mock`.
- The upscale test mocks `replicate` and validates output file creation plus Replicate call parameters.

## Known Notes

- The terminal output currently shows mojibake for accented French text in some files. Treat this as an encoding/display issue unless file inspection proves the file bytes are actually corrupted.
- Running PowerShell commands emits an oh-my-posh init warning about access to `AppData\Local\oh-my-posh`; it appears unrelated to project behavior.
- Git repository root: workspace root `C:\Users\ps88cre\LAB\BdGen`.
- Avoid changing `.env` unless the user explicitly asks.

## Change Log

### 2026-05-05 (5)

- `bdgen/desktop/main.js`: added a macOS runtime Dock icon assignment via `app.dock.setIcon()` using the packaged PNG asset, so the running app uses the BdGEN icon in the Dock/App Switcher/Alt-Tab UI instead of Electron's default icon.
- Verification: `npm run lint` and `node --check main.js` passed from `bdgen/desktop`; the existing macOS bundle `Info.plist` still declares `CFBundleIconFile` as `icon.icns`.

### 2026-05-05 (4)

- `bdgen/desktop/main.js` and `bdgen/desktop/preload.js`: added a safe desktop bridge for opening HTTPS external links with the system default browser, and routed Electron new-window attempts through the same handler.
- `bdgen/web/src/pages/SecretsPage.jsx`: provider documentation/token links now call the desktop external-link bridge when available, while preserving normal browser behavior on web.
- `bdgen/bdgen/server/static/`: refreshed built frontend assets with `npm run build`.
- Verification: `npm run lint` passed from `bdgen/desktop` and `bdgen/web`; `npm run build` passed from `bdgen/web`.

### 2026-05-05 (3)

- `bdgen/web/src/pages/SecretsPage.jsx`: added provider-specific external links on the API key setup/management screen, with one documentation link and one token/API key creation link for OpenAI, Anthropic, xAI, and Replicate; also restored French accents in visible secrets/setup labels touched by this screen.
- `bdgen/bdgen/server/static/`: refreshed built frontend assets with `npm run build`.
- Verification: `npm run build` and `npm run lint` passed from `bdgen/web`.

### 2026-05-05 (2)

- `bdgen/web/src/components/OnboardingWizard.jsx`: restored French accents and typographic apostrophes in the onboarding copy.
- `bdgen/bdgen/server/static/`: refreshed built frontend assets with `npm run build` after the copy update.
- Verification: `npm run build` passed. An initial parallel `npm run lint` collided with Vite temporary config cleanup during the build; rerunning `npm run lint` alone passed.

### 2026-05-05 (1)

- `bdgen/web/src/components/OnboardingWizard.jsx`: added a reusable two-mode onboarding wizard with localStorage dismissal state. The initial mode explains the master password, API key setup, and cost expectations; the app mode explains the BdGEN creation flow from preparation to compose/upscale.
- `bdgen/web/src/App.jsx`: wired the initial wizard before first secrets vault setup and the app guide after the application becomes accessible.
- `bdgen/bdgen/server/static/`: refreshed built frontend assets with `npm run build` so the packaged backend serves the onboarding UI.
- Verification: `npm run lint` and `npm run build` passed from `bdgen/web`.

### 2026-05-04 (7)

- `bdgen/desktop/assets/icon.icns`: added a macOS application icon generated from the vector `bd_gen_logo.svg` asset so packaged `.app`/DMG builds do not fall back to Electron's default icon.
- `bdgen/desktop/package.json`: configured the macOS Electron Builder target to use `assets/icon.icns` explicitly.
- `bdgen/desktop/main.js`: updated runtime icon resolution to prefer `icon.icns` on macOS, while keeping `icon.ico` on Windows and `icon.png` on Linux/fallback paths.

### 2026-05-04 (6)

- `bdgen/web/src/App.jsx`: made the custom desktop title bar platform-aware; on macOS it reserves space for the native traffic-light controls and hides the duplicate right-side custom window buttons.
- `bdgen/web/src/index.css`: added reusable title bar layout classes, including a macOS left inset so the native controls no longer overlap the BdGEN logo.
- `bdgen/bdgen/server/static/`: refreshed the built frontend assets with `npm run build` so the packaged desktop app picks up the title bar fix.

### 2026-05-04 (5)

- `bdgen/desktop/package.json`: registered an Electron Builder `afterPack` hook for packaged backend resources.
- `bdgen/desktop/scripts/prepare-backend-resource.js`: added packaging-time preparation for the embedded backend executable; Unix builds get `chmod 755`, and macOS builds also receive an ad-hoc `codesign --sign -` signature.
- `bdgen/desktop/main.js`: surfaced backend `spawn` failures directly so macOS permission/missing-binary errors are shown instead of only timing out while waiting for `/api/health`.
- `Makefile` and `.github/workflows/release-portable.yml`: ad-hoc sign the PyInstaller `bdgen-server` executable on macOS immediately after build, before Electron packaging.
- Verification: `python3 -m json.tool bdgen/desktop/package.json` passed. A full `make macos` test could not run on this machine yet because `uv`, `node`, and `npm` are not installed in the available shell environment.

### 2026-05-04 (4)

- `.github/workflows/release-portable.yml`: added Linux to the desktop build matrix on `ubuntu-latest`, uploading and publishing `build/linux/*.AppImage` release assets.
- `README.md`: documented Linux AppImage support as an active build/release target instead of a planned target.
- `doc/project_reference.md`: updated the desktop build notes and recorded the Linux release addition.

### 2026-05-04 (3)

- `README.md`: translated the full user-facing documentation from French to English while preserving commands, package outputs, and CI/CD behavior.
- `doc/project_reference.md`: recorded the README translation.

### 2026-05-04 (2)

- `README.md`: added GitHub badges for the desktop CI workflow, latest release, license, Python, Electron, and current platform packaging status.
- `doc/project_reference.md`: recorded the README badge update.

### 2026-05-04 (1)

- Added the first unsigned macOS DMG packaging path while keeping the structure ready for Linux.
- Root `Makefile`: added `make macos`, `make linux`, Unix backend verification for `build/backend/bdgen-server`, and platform-specific desktop targets.
- `bdgen/desktop/package.json`: split Electron Builder scripts into Windows, macOS, and Linux targets; Windows embeds `bdgen-server.exe`, macOS/Linux embed `bdgen-server`; macOS builds an unsigned DMG with signing disabled.
- `.github/workflows/release-portable.yml`: refactored release flow into quality, version, early tag creation, a desktop build matrix, and publish jobs. Releases now attach both the Windows portable `.exe` and the unsigned macOS `.dmg`.
- `README.md`: documented desktop package outputs, the unsigned macOS DMG caveat, and the future Linux packaging direction.

### 2026-05-01 (12)

- Fixed image provider changes made after script generation not being honored by references/compose.
- Backend: `service._resolve_options()` now prefers the current `bdgen.json` generation options when available instead of the stale copy embedded in `bdgen-script.json`.
- Backend: `detect_and_mark_stale()` now syncs `bdgen-script.json` generation options from the saved project config and marks generated references/pages stale when the image model/provider changes; page stale detection now uses the zero-padded page filenames.
- Tests: added `bdgen/tests/test_generation_options_sync.py` to cover switching OpenAI image models after the script already exists.
- Verification: `make lint` passed; `uv run python -m unittest tests.test_generation_options_sync` passed; `uv run python -m unittest discover -s tests` passed.

### 2026-05-01 (11)

- Added GitHub Actions CI/CD workflow `.github/workflows/release-portable.yml`.
- Workflow runs on every push to `main`: installs backend/frontend/desktop dependencies, runs all linters, runs `npm audit --audit-level=critical` for frontend and desktop, then builds the Windows portable executable only if quality gates pass.
- Release job computes the next SemVer tag from commit messages since the latest `vX.Y.Z` tag, or from the desktop package version when no release tag exists yet: `BREAKING CHANGE` or `type!` => major, `feat` => minor, otherwise patch; it updates the desktop package version for packaging, uploads a workflow artifact, creates the git tag, and publishes/updates the GitHub Release with the portable `.exe`.
- `README.md` now documents the CI/CD flow and the commit message conventions for major/minor/patch releases.
- Verification: `make lint` passed locally; `npm audit --audit-level=critical` passed locally for frontend and desktop (frontend still reports moderate Vite/esbuild advisories, desktop still reports high Electron/electron-builder transitive advisories, but no critical advisories); full workflow execution requires GitHub Actions because it depends on hosted Windows runners and GitHub release permissions.

### 2026-05-01 (10)

- Removed the optional xAI image-generation path; image generation is OpenAI-only again.
- Backend: removed the xAI image adapter and the `references.py` / `compose.py` branches for `image_model.provider = "xai"`. xAI remains available for script/text generation.
- Frontend: `ProjectForm.jsx` no longer offers xAI as an image provider; legacy xAI image configs are coerced back to OpenAI.
- Verification: `uv run python -m unittest discover -s tests` passed; `uv run ruff check bdgen tests` passed.

### 2026-05-01 (9)

- Added xAI/Grok as a script-generation provider.
- Backend: `secret_store.py` now supports `XAI_API_KEY` and an OpenAI-compatible xAI client; `script.py` dispatches `script_model.provider = "xai"` through the Grok chat-completions structured-output path.
- Frontend: `ProjectForm.jsx` now offers provider-specific model dropdowns with a custom manual model entry, and includes recent OpenAI, Anthropic, and xAI script models; `SecretsPage.jsx` exposes the xAI key in the local vault UI.
- Docs/config samples: added `XAI_API_KEY` to `.env.sample` and README, refreshed sample script model IDs, and rebuilt frontend static assets.
- Verification: `make lint` passed; `npm run build` passed outside the sandbox after the known Windows/esbuild `spawn EPERM` sandbox failure.

### 2026-05-01 (8)

- Cleaned up the lint warnings reported by `make lint`.
- Frontend: added `eslint-plugin-react` so JSX component usage is recognized, removed unused props/imports, fixed hook dependency warnings, and disabled the React Fast Refresh export warning for the current file structure.
- Verification: `make lint` now passes with no warnings across backend, frontend, and desktop.

### 2026-05-01 (7)

- Added lint/format tooling for all app parts.
- Backend: `bdgen/pyproject.toml` now defines Ruff as a dev dependency plus Ruff lint/format configuration; `bdgen/uv.lock` was refreshed.
- Frontend: added ESLint flat config, Prettier config/ignore, npm scripts, and refreshed `bdgen/web/package-lock.json`.
- Desktop: added ESLint flat config, Prettier config/ignore, npm scripts, and refreshed `bdgen/desktop/package-lock.json`.
- Root `Makefile`: added aggregate and per-part `lint`, `format`, and `format-check` targets.
- `README.md`: documented the new quality commands; `doc/next_steps.md` no longer lists the completed linter/formatter task.
- Verification: backend Ruff check passed, desktop ESLint/Prettier checks passed, and frontend ESLint passed with existing warnings only.

### 2026-05-01 (6)

- `README.md`: rewrote the usage documentation around two distinct workflows: web mode and portable exe mode.
- The README now explains installation, launch commands, data locations, build output, and when to use each mode.
- `doc/next_steps.md`: removed the completed README task from the remaining next steps.

### 2026-05-01 (5)

- Removed the baked white background from `bd_gen_logo.svg`, `bdgen/web/public/bd_gen_logo.svg`, and the built server copy so the in-app/header logo can render transparently.
- Regenerated transparent PNG/ICO icon assets from the transparent root `bd_gen_logo.png`: web public logo/favicon, server static logo/favicon, `bdgen/desktop/assets/icon.png`, `bdgen/desktop/assets/icon.ico`, and root `bd_gen_logo.ico`.
- `bdgen/desktop/main.js`: `BrowserWindow` now prefers `assets/icon.ico` on Windows, falling back to `icon.png` for other platforms or missing ICO files.
- Verified icon alpha with Pillow, ran `node --check bdgen/desktop/main.js`, rebuilt the frontend with `npm run build`, and rebuilt the portable desktop executable at `build/portable/BdGEN 0.1.0.exe`.
- Frontend esbuild and Electron Builder still require running outside the sandbox after `spawn EPERM`.

### 2026-05-01 (4)

- `bdgen/web/src/App.jsx` and `bdgen/web/src/pages/SecretsPage.jsx`: fixed the locked startup screen showing a vertical scrollbar after adding the custom Electron title bar.
- The locked app wrapper now uses the available remaining height below the title bar, and the secrets gate shell uses `h-full` instead of `min-h-screen`.
- Rebuilt the frontend with `npm run build`; esbuild still requires running outside the sandbox after `spawn EPERM`.

### 2026-05-01 (3)

- `bdgen/desktop/main.js`: fixed the erroneous "Le serveur local s'est arrete (code null)" dialog shown when closing the app normally.
- The Electron process now tracks normal shutdown with `isQuitting` and suppresses backend exit alerts when the backend was intentionally killed during app quit.
- Verified with `node --check bdgen/desktop/main.js`.

### 2026-05-01 (2)

- `bdgen/web/src/App.jsx`: when the app is locked by the secrets gate in Electron, the custom title bar now remains visible but hides app navigation.
- Rebuilt the frontend with `npm run build`; as before, esbuild hit `spawn EPERM` in the sandbox and the build passed outside the sandbox.

### 2026-05-01 (1)

- Modernized the Electron shell by removing the native menu/frame and replacing it with an in-app custom title bar.
- `bdgen/desktop/main.js`: added `Menu.setApplicationMenu(null)`, frameless `BrowserWindow` options, hidden title bar, custom background color, and IPC handlers for minimize/maximize/close/window state.
- `bdgen/desktop/preload.js`: exposes safe `bdgenDesktop` window-control methods to the React app.
- `bdgen/web/src/App.jsx`: uses the custom desktop title bar only when running under Electron, while preserving the standard web header for browser mode.
- `bdgen/web/src/index.css`: added draggable/no-drag title bar regions and modern hover states for window controls.
- Ran `node --check` for Electron files and `npm run build`; the build required running outside the sandbox after esbuild hit `spawn EPERM`.

### 2026-04-30 (18)

- Updated the web and Electron app icons to use the root `bd_gen_logo.svg` as the visual source of truth.
- `bdgen/web/public/bd_gen_logo.svg`: replaced the previous simplified icon with a square, centered SVG derived from the root logo so the favicon and in-app header match the official artwork.
- `bdgen/web/public/favicon.png`, `bdgen/web/public/bd_gen_logo.png`, `bdgen/desktop/assets/icon.png`, and `bdgen/desktop/assets/icon.ico` are generated from that SVG for browser fallback and Windows desktop packaging.
- `bdgen/desktop/package.json`: Electron Builder now embeds `assets/icon.ico`, and `files` includes `assets/**/*` so the packaged app keeps the same branding.
- `bdgen/desktop/main.js`: `BrowserWindow` now uses `assets/icon.png` at runtime so the development window and packaged app show the BdGEN icon consistently.
- Verification target: rebuild the frontend and run an Electron pack/build to confirm the previous "no app icon configured" warning is gone.

- Fixed the packaged desktop app showing a blank page / `{"detail":"Not Found"}`.
- Root cause: in the PyInstaller one-file backend, `bdgen/bdgen/server/__main__.py` is executed as a top-level script, so `Path(__file__).parent / "static"` does not point to the bundled frontend assets.
- `bdgen/bdgen/server/__main__.py`: added `_static_dir()` to resolve static assets from both normal package execution and PyInstaller's `sys._MEIPASS/bdgen/server/static` extraction directory.
- Verification: rebuilt `build/backend/bdgen-server.exe` directly with PyInstaller and confirmed `GET /api/health`, `GET /`, and `GET /assets/index-B_BOE8Hu.js` all return 200.
- Note: full `make portable` rebuild was blocked in the sandbox by `uv` cache permissions and then Electron Builder `spawn EPERM`; rerun `make portable` from a normal terminal after closing any running BdGEN executable.

### 2026-04-30 (17)

- Removed the installer build path and kept the portable executable as the only desktop artifact.
- Root `Makefile`: removed `INSTALLER_DIST` and `desktop-portable`; `make portable` and `make desktop` both build the portable Electron executable, and `make build` is now an alias to `make portable`.
- `bdgen/desktop/package.json`: `npm run build` now delegates to `npm run build:portable`; Electron Builder's default Windows target is now `portable` instead of `nsis`.
- User-facing desktop output remains `build/portable/BdGEN 0.1.0.exe`; `build/installer` is no longer produced.

### 2026-04-30 (16)

- Fixed `make portable` failure on Windows caused by Electron Builder downloading `winCodeSign-2.6.0.7z` and failing to extract macOS symlinks without the Windows symlink privilege.
- `bdgen/desktop/package.json`: set `build.win.signAndEditExecutable` to `false` and `build.win.verifyUpdateCodeSignature` to `false` for local unsigned Windows builds, so portable packaging no longer uses `winCodeSign`.
- Verified `make portable` successfully creates `build/portable/BdGEN 0.1.0.exe`. Electron Builder still warns that no app icon is configured and npm audit reports existing dependency vulnerabilities; neither blocks the portable build.

### 2026-04-30 (15)

- Fixed the broken Python package layout that prevented the app from launching after the desktop migration.
- Moved runtime modules from `bdgen/*.py` into the actual import package `bdgen/bdgen/`.
- Moved FastAPI server files from `bdgen/server/` into `bdgen/bdgen/server/`, preserving the existing `bdgen/bdgen/server/static/` frontend build output.
- `bdgen/bdgen/server/__main__.py` now imports `create_app` with an absolute package import so the same entrypoint works both with `python -m bdgen.server` and when PyInstaller executes the file as a script.
- `bdgen/bdgen-server.spec` no longer calls `collect_data_files("bdgen")`; static frontend assets are added explicitly from `bdgen/bdgen/server/static`, avoiding a misleading PyInstaller package warning.
- Root `bdgen/main.py`, `uv run python -m bdgen.server`, tests, PyInstaller spec, and Electron dev fallback now resolve `bdgen.cli`, `bdgen.models`, `bdgen.server`, etc. correctly from the `bdgen/` project directory.
- Verification: `uv run python -m unittest discover -s tests` passed (4 tests), `uv run main.py --help` passed, `create_app()` import passed, `npm run build` passed, `make backend` passed, `uv run python -m bdgen.server` returned `GET /api/health` OK, and the rebuilt `build/backend/bdgen-server.exe` returned `GET /api/health` OK.

### 2026-04-30 (11)

- Fixed the Makefile/uv virtualenv mismatch that appeared when the workspace root `.venv` was active but `uv` tried to manage `bdgen/.venv`.
- Root `Makefile` now exports `UV_PROJECT_ENVIRONMENT := ../.venv`, so all `uv` commands run from `bdgen/` use the workspace-level `.venv` and ignore the stale `bdgen/.venv` environment.
- Verified `make sync` outside the sandbox: it recreated `../.venv`, installed `cryptography` and `pyinstaller`, and no longer touched `bdgen/.venv`.
- Verified `make test` outside the sandbox: 4 Python tests passed. `make -n portable` still expands to the expected portable build chain.

### 2026-04-30 (12)

- Fixed build output confusion: `bdgen/dist/bdgen-server.exe` was only the PyInstaller server intermediate, not the user-facing Electron executable.
- Root `Makefile`: PyInstaller now writes the embedded backend to `bdgen/build/backend/bdgen-server.exe`; Electron artifacts are expected in root `dist/`.
- `bdgen/desktop/package.json`: Electron Builder output directory is now `../../dist`, and `extraResources` embeds `../build/backend/bdgen-server.exe`.
- Verified `make -n build`, `make -n portable`, and desktop `package.json` parsing. After `make portable`, look in root `dist/` for the portable Electron `.exe`; `bdgen/build/backend/bdgen-server.exe` is internal.

### 2026-04-30 (13)

- Centralized all desktop build outputs under root `build/` to avoid confusing PyInstaller and Electron `dist` directories.
- Root `Makefile`: backend intermediate now goes to `build/backend/bdgen-server.exe`; PyInstaller work files go to `build/pyinstaller-work`; installer output is `build/installer`; portable output is `build/portable`; `clean` removes all root build artifacts plus legacy `dist` folders.
- `bdgen/desktop/package.json`: Electron Builder scripts now explicitly write to `../../build/installer` or `../../build/portable`, and embed `../../build/backend/bdgen-server.exe`.
- Verified `make -n build`, `make -n portable`, and desktop `package.json` parsing. User-facing executables should only be picked from `build/installer` or `build/portable`.

### 2026-04-30 (14)

- Fixed Windows Makefile backend verification: replaced Unix-only `test -f` with `powershell Test-Path`.
- This resolves the `test n'est pas reconnu` failure at the end of `make portable` after PyInstaller successfully created `build/backend/bdgen-server.exe`.
- Verified `make -n portable` and direct `Test-Path` check against `build/backend/bdgen-server.exe`.

### 2026-04-30 (10)

- Clarified the desktop packaging architecture: Electron remains the user-facing app and embeds the PyInstaller-built FastAPI backend as an internal resource; the user-facing artifacts are single `.exe` outputs.
- `bdgen/desktop/package.json`: `npm run build` now targets the NSIS installer explicitly, and `npm run build:portable` targets Electron Builder's portable Windows executable.
- Root `Makefile`: `make build` creates the installer `.exe`; `make portable` creates the portable `.exe`; added `desktop-portable` target. Verified `make -n build`, `make -n portable`, and desktop `package.json` parsing.
- Public Makefile help intentionally shows `make build` and `make portable` as the user-facing desktop artifact commands; `desktop-portable` remains an internal target and is hidden from `make help`.

### 2026-04-30 (9)

- Added root `Makefile` so `make build` runs the full desktop build chain: `uv sync`, frontend build, PyInstaller backend build, and Electron installer build.
- Make targets include `frontend`, `backend`, `desktop`, `test`, `dev-desktop`, and `clean`; `make -n build` was verified to expand to the expected commands without executing the heavy build.
- Updated `bdgen/desktop/package.json` so Electron packages the PyInstaller one-file output from `../dist/bdgen-server.exe` to `backend/bdgen-server.exe`, matching `bdgen-server.spec` and `desktop/main.js`.

### 2026-04-30 (8)

- Started the Electron/PyInstaller migration path with a secure local API-key vault.
- Added `bdgen/bdgen/secret_store.py`: encrypted `secrets.vault` stored under `BDGEN_CONFIG_ROOT` or the OS app config directory, PBKDF2-SHA256 key derivation, AES-GCM encryption via `cryptography`, in-memory unlock state, `.env` fallback for dev, and provider helpers for OpenAI/Anthropic/Replicate.
- Updated provider clients in `script.py`, `references.py`, `compose.py`, `style_from_image.py`, `service.py`, and `upscale.py` to read API keys through `secret_store` instead of relying directly on process environment defaults.
- Added secrets API endpoints in `bdgen/bdgen/server/app.py`: status, create, unlock, lock, update/delete provider key.
- Added frontend API helpers plus `web/src/pages/SecretsPage.jsx`; `App.jsx` now gates startup when the vault exists but is locked, or when no API provider is configured, and exposes a "Cles API" route.
- Added Electron scaffold under `bdgen/desktop/`: `main.js` starts the local backend on `127.0.0.1`, waits for `/api/health`, opens the bundled frontend, passes `BDGEN_CONFIG_ROOT`/`BDGEN_OUTPUT_ROOT`, and falls back to `python -m bdgen.server` from the repo root in dev; `package.json` uses `electron-builder`; `preload.js` exposes minimal desktop metadata.
- Added `bdgen/bdgen-server.spec` for PyInstaller packaging of `bdgen.server` and static frontend assets.
- Added `bdgen/tests/test_secret_store.py` for vault create/unlock/update/wrong-password coverage.
- Added Python dependencies `cryptography` and `pyinstaller` in `pyproject.toml`; `uv.lock` was updated by `uv sync`, but the sync ended with a Windows access-denied cleanup error in `.venv`, so PyInstaller may still need a clean `uv sync` after closing processes that hold `.venv` files.
- Verification: `python -m py_compile` passed, `.venv\Scripts\python.exe -m unittest discover -s tests` passed outside the sandbox, `npm run build` passed outside the sandbox, and `node --check` passed for `desktop/main.js` and `desktop/preload.js`.

### 2026-04-30 (7)

- Added a waiting overlay to the image reader during targeted brush retouching and item regeneration.
- `bdgen/web/src/components/ImageStep.jsx`: `ImageFlipper` now accepts `busy`/`busyLabel`, greys and disables the full reader while busy, and shows a centered spinner overlay. Inpainting submission uses the same overlay; per-item regeneration now awaits `onRefresh(item)` from the confirmation dialog.

### 2026-04-30 (6)

- Fixed detailed brush retouching so it no longer blocks the FastAPI event loop while the OpenAI/Pillow inpainting call runs.
- `bdgen/bdgen/server/app.py`: `/api/projects/{name}/inpaint/{step}/{target_id}` now calls `service.inpaint_image()` through `asyncio.to_thread(...)`, keeping the server responsive during long retouches.
- Keep future inpainting/image-edit routes off the async event loop when they perform synchronous API calls or CPU/file image processing.

### 2026-04-30 (5)

- Moved brush-based inpainting from modal to inline reader.
- `ImageStep.jsx`: removed `InpaintModal` import and `inpainting` state; `onInpaint` prop on `ImageFlipper` now accepts `(item, maskBlob, prompt)` and calls `api.inpaintImage` directly; added `useRef` and brush constants (`MIN_BRUSH`, `MAX_BRUSH`, `DEFAULT_BRUSH`).
- `ImageFlipper` in `ImageStep.jsx`: fully self-contained inpainting — activating "Retouche ciblée" overlays a `<canvas>` directly on the image (same `relative inline-block` technique as the old modal), shows brush slider + clear button + prompt textarea + submit below the image; navigation arrows are disabled while active; cancelling or submitting restores normal view.
- `InpaintModal.jsx` kept as-is but no longer used by `ImageStep`.

### 2026-04-30 (4)

- Added targeted inpainting (brush retouching) feature for references and compose images.
- New frontend component `bdgen/web/src/components/InpaintModal.jsx`: canvas overlay with adjustable brush, exports RGBA mask (painted=transparent, unpainted=white-opaque) then submits via FormData.
- `ImageStep.jsx`: added `inpainting` state, `onInpaint` prop passed to `ImageFlipper`, renders `InpaintModal` when active.
- `ImageFlipper` in `ImageStep.jsx`: new `onInpaint` prop, "🖌 Retouche ciblée" button shown alongside existing action buttons when an image is present.
- `api.js`: added `inpaintImage(name, step, targetId, maskBlob, prompt)` — sends FormData with `mask` + `prompt` to new endpoint.
- `service.py`: added `inpaint_image()` (loads source PNG→RGBA, resizes mask to match, calls `client.images.edit` with mask, saves result atomically) and `_reference_path_for_id()` helper.
- `server/app.py`: added `POST /api/projects/{name}/inpaint/{step}/{target_id}` endpoint (accepts `prompt` Form field + `mask` File upload, blocks if a job is running, calls service and returns updated `image_url`).
- Mask format: user paints over areas to change; frontend inverts alpha so painted=transparent (OpenAI regenerates) and unpainted=white-opaque (OpenAI keeps). Backend resizes mask to source image dimensions before the API call.

### 2026-04-30 (3)

- When a generation is running, steps now show the existing content in read-only mode with a `RunningBanner` at the top instead of replacing the entire UI with a blocked card.
- `ScriptStep.jsx`: removed `BlockedByOtherStep` early return; added `blocked` flag; shows `RunningBanner` + read-only `ScriptBrowser`; disables generation buttons.
- `ImageStep.jsx`: removed early return for `otherStepRunning`; added `blocked` flag; shows `RunningBanner`; disables all generation/upgrade/refine buttons and flipper action callbacks.
- `Wizard.jsx`: `reload()` now fetches `api.currentJob()` in parallel with `getProject()`; auto-redirect to running step when a job is active for this project, otherwise falls back to `project.state`.

### 2026-04-30 (2)

- Replaced high-res thumbnail logic with pre-generated JPEG thumbnails.
- `service._ensure_thumbnail()` generates `output/<project>/thumbnail.jpg` (256×384, JPEG q85) using Pillow on first call after a new cover/page is written; subsequent calls only check mtime and skip generation.
- `service.THUMBNAIL_NAME`, `_THUMB_MAX_W`, `_THUMB_MAX_H` constants added.
- `app.py` unchanged — `thumbnail_rel` is still resolved to a URL via the existing `/api/projects/{name}/files/` endpoint.
- Thumbnails are invalidated automatically: `source.mtime > thumbnail.mtime` triggers regeneration on next `listProjects` call.

### 2026-04-30

- Fixed duplicated-project reference reuse: copied PNGs under `references/` are now reattached to `bdgen-script.json` through `service.attach_existing_reference_images()`, and `compose.py` falls back to canonical reference paths when `reference_image` is missing.
- Added `bdgen/tests/test_duplicate_references.py` to cover copied reference image reattachment and compose reference collection.
- Added per-project generation telemetry through `bdgen/bdgen/stats.py`.
- Instrumented script, reference image, compose image, and upscale generation paths to append events to `bdgen-stats.json`.
- Added `service.project_statistics()` and `GET /api/projects/{name}/statistics`.
- Added frontend statistics route `/projects/:name/stats`, API helper `getProjectStatistics`, a stats button on the project list, and `ProjectStats.jsx`.
- Verified with `uv run python -m unittest discover -s tests` and `npm run build` run outside the sandbox due local permission restrictions.
- Added `doc/project_reference.md`.
- Recorded initial project map, backend/frontend architecture, key commands, test notes, and the rule that this file must be updated after each future modification.
