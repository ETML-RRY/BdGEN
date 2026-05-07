# BdGEN - Project Reference

Operational reference for future work on BdGEN. Keep this file concise and update it after every code, configuration, documentation, or workflow change.

Last updated: 2026-05-07 (3)

## Update Rule

- Before changing files, read this document and the files relevant to the task.
- After every modification, update "Change Log" with the date, files touched, and useful context for the next operation.
- Prefer current architecture, commands, conventions, risks, and recent decisions over long historical detail.

## Project Map

- Main Python app: `bdgen/`
- Backend package: `bdgen/bdgen/`
- Frontend app: `bdgen/web/`
- Electron app: `bdgen/desktop/`
- Static frontend served by backend: `bdgen/bdgen/server/static/`
- Build outputs: `build/backend/`, `build/portable/`, `build/mac/`, `build/linux/`
- Main docs: `README.md`, `doc/project_reference.md`, `next_steps.md`
- Root assets: `bd_gen_logo.png`, `bd_gen_logo.svg`, `bd_gen_logo.ico`

## Application Overview

BdGEN generates comic books from a JSON project description.

Pipeline:

1. `script`: expands the user configuration into `bdgen-script.json` with an LLM.
2. `references`: generates visual sheets for characters, locations, and objects.
3. `compose`: generates pages, cover/back cover, and assembles the PDF.
4. `upscale`: optional local or Replicate-backed upscale for composed images.

Projects are stored under `output/<project>/` by convention. A complete project generally contains `bdgen.json`, `bdgen-script.json`, `references/`, `pages/`, `pages_upscaled/`, the final PDF, thumbnails, and telemetry files.

## Backend

- CLI entry point: `bdgen/bdgen/cli.py`
- Models and path rules: `bdgen/bdgen/models.py`
- Pipeline modules: `script.py`, `references.py`, `compose.py`, `upscale.py`, `wizard.py`
- Service layer: `bdgen/bdgen/service.py`
- FastAPI app: `bdgen/bdgen/server/app.py`
- Job manager and SSE state: `bdgen/bdgen/server/jobs.py`
- Stats module: `bdgen/bdgen/stats.py`
- Secret vault: `bdgen/bdgen/secret_store.py`

Backend conventions:

- `BdGenInput.load()` fills default output paths from `project` and `output_root`.
- `BdGenScript.load()` keeps generated paths relative to the script project directory.
- The web server uses `BDGEN_OUTPUT_ROOT` when set, otherwise `./output`.
- Per-project stats are stored in `bdgen-stats.json`.
- Script integrity/coherence metadata is stored next to project files and should remain non-blocking when LLM checks fail.
- Synchronous image or provider calls in FastAPI routes should run off the async event loop.
- Avoid exposing or editing `.env` unless explicitly requested.

## Frontend

- Framework: Vite + React 18
- App and routes: `bdgen/web/src/App.jsx`
- Pages: `Home.jsx`, `NewProject.jsx`, `Wizard.jsx`, `SecretsPage.jsx`, `ProjectStats.jsx`
- API client: `bdgen/web/src/api.js`
- Wizard and step UI: `bdgen/web/src/components/`
- Main script editor/browser: `bdgen/web/src/components/ScriptBrowser.jsx`
- Image generation/retouch UI: `bdgen/web/src/components/ImageStep.jsx`

Frontend conventions:

- Rebuild `bdgen/bdgen/server/static/` after user-visible frontend changes.
- Onboarding wizard dismissal is session-only unless the user checks "Ne plus afficher ce guide au lancement".
- The script browser owns manual edit, add/delete, coherence, and integrity UI.
- Generated static assets are hashed; do not hand-edit bundled JS/CSS except for emergency investigation.

## Desktop And Packaging

- Electron shell: `bdgen/desktop/main.js`
- Preload bridge: `bdgen/desktop/preload.js`
- PyInstaller spec: `bdgen/bdgen-server.spec`
- Electron embeds the PyInstaller FastAPI backend as an internal resource.
- User-facing portable Windows executable is under `build/portable/`.
- `make macos` creates an unsigned DMG under `build/mac/`.
- `make linux` creates an AppImage under `build/linux/`.
- macOS/Linux backend binaries are named `bdgen-server`; Windows uses `bdgen-server.exe`.
- Windows unsigned builds disable Electron Builder code signing to avoid `winCodeSign` extraction issues.

## Commands

From workspace root:

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

From `bdgen/`:

```bash
uv sync
uv run main.py wizard <project.json>
uv run main.py run <project.json>
uv run main.py script <project.json>
uv run main.py references ./output/<project>/bdgen-script.json
uv run main.py compose ./output/<project>/bdgen-script.json
uv run main.py upscale ./output/<project>/bdgen-script.json
uv run python -m unittest discover -s tests
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

## Dependencies And Tooling

- Python metadata: `bdgen/pyproject.toml`
- Python lockfile: `bdgen/uv.lock`
- Frontend package metadata: `bdgen/web/package.json`
- Desktop package metadata: `bdgen/desktop/package.json`
- Environment template: `bdgen/.env.sample`
- Local environment: `bdgen/.env`
- License metadata: root `LICENSE`, README license section, Python/web/desktop package metadata.

Key dependency families:

- Backend: Pydantic, OpenAI, Anthropic, Pillow, Replicate, python-dotenv, FastAPI, Uvicorn, python-multipart, cryptography, PyInstaller.
- Frontend: React, React Router, React Icons, Tailwind/Vite tooling.
- Desktop: Electron and Electron Builder.

Lint/format:

- Backend: Ruff via `uv run ruff check .` and `uv run ruff format .`.
- Frontend: ESLint flat config and Prettier through `bdgen/web/package.json`.
- Desktop: ESLint flat config and Prettier through `bdgen/desktop/package.json`.

## Tests

- Current Python tests live under `bdgen/tests/`.
- Test style uses `unittest`, `tempfile`, and `unittest.mock`.
- Relevant coverage includes upscale, duplicate references, secret vault, and manual script edits/integrity.
- For frontend changes, run targeted Prettier/ESLint and rebuild when static assets must be refreshed.

## Known Notes

- Some terminal output may show mojibake for accented French text. Treat it as display/encoding noise unless file bytes prove corruption.
- `uv` cache, `.venv` cleanup, Vite/esbuild, Electron Builder, and PyInstaller may need outside-sandbox execution on Windows.
- If a frontend build fails with esbuild `spawn EPERM` on Windows, rerun the build outside the sandbox.

## Recent Change Log

### 2026-05-07 (3)

- `doc/project_reference.md`: compacted from a long historical log into an operational reference with concise architecture, commands, conventions, risks, and recent changes.
- Historical details were summarized instead of preserved line by line to keep this file useful for future turns.

### 2026-05-07 (2)

- `LICENSE`: added MIT license with copyright `2026 ETML-RRY`.
- `README.md`: added a "License" section pointing to `LICENSE`.
- `bdgen/pyproject.toml`, `bdgen/web/package.json`, `bdgen/desktop/package.json`: declared `MIT` license metadata.
- Verification: JSON/TOML parsing OK, `git diff --check` OK, local Prettier OK on README and both package files.

### 2026-05-07 (1)

- `bdgen/web/src/components/OnboardingWizard.jsx`: added "Ne plus afficher ce guide au lancement" checkbox.
- `bdgen/web/src/App.jsx`: wizard dismissal persists in `localStorage` only when the checkbox is checked; otherwise it stays hidden for the current session.
- `bdgen/bdgen/server/static/`: frontend rebuilt after the wizard change.
- Verification: frontend lint OK with one preexisting `ScriptBrowser.jsx` warning, targeted Prettier OK, build OK outside sandbox after the known esbuild `spawn EPERM`.

### 2026-05-06 Summary

- Improved image reader behavior during live generation, including target-specific overlays and direct image navigation.
- Integrated scenario coherence into `ScriptBrowser` tabs and made applied suggestions disappear from coherence files.
- Added and refined LLM-backed scenario integrity checks, dirty tracking after manual edits, and integrity UI/actions.
- Added manual CRUD/editing for pages, characters, locations, objects, cover, and back cover.
- Reworked manual edit popups and compact edit pencil styling.
- Expanded stats logging for retouching and integrity operations.
- Rebuilt static frontend assets after major UI changes when possible.

### 2026-04-30 To 2026-05-01 Summary

- Added project telemetry/statistics backend and frontend page.
- Added thumbnails and improved duplicate-project reference reuse.
- Added inline brush retouching/inpainting and moved synchronous image work off the async event loop.
- Added secret vault, Electron desktop shell, PyInstaller backend packaging, custom title bar, and app icons.
- Centralized build outputs under root `build/`; kept portable Windows executable as the main desktop artifact.
- Fixed packaged backend static asset resolution and several Makefile/build path issues.
- Added lint/format commands across backend, frontend, desktop, and root Makefile.
- Rewrote README around web and portable workflows.
