# BdGEN - Project Reference

Operational reference for future work on BdGEN. Keep this file concise and update it after every code, configuration, documentation, or workflow change.

Last updated: 2026-06-04

## Update Rule

- Before changing files, read this document and the files relevant to the task.
- After every modification, update "Change Log" with the date, files touched, and useful context for the next operation.
- Prefer current architecture, commands, conventions, risks, and recent decisions over long historical detail.

## Project Map

- Main Python app: `bdgen/`
- Backend package: `bdgen/bdgen/`
- Frontend app: `bdgen/web/`
- Electron app: `bdgen/desktop/`
- Generated static frontend served by backend: `bdgen/bdgen/server/static/`
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

- Rebuild `bdgen/bdgen/server/static/` locally after user-visible frontend changes when you need to run the backend-served UI; the generated folder is ignored by Git.
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

### 2026-06-04

- `Makefile`: made `make dev-desktop` Windows-compatible by setting `BDGEN_BACKEND_CMD` and `BDGEN_BACKEND_ARGS` with `cmd.exe` `set "VAR=value"` syntax while keeping the POSIX inline environment form for Unix shells; it now runs `npm rebuild electron` after install so a missing Electron binary from skipped postinstall scripts is repaired before launch.
- `.github/workflows/release-portable.yml`, `bdgen/desktop/package.json`, `bdgen/desktop/package-lock.json`: tightened npm security gates by running full `npm audit` for both frontend and Electron desktop dependencies, upgraded the workflow to Node 22 for current Electron tooling, and updated desktop Electron tooling to `electron@41.7.1` plus `electron-builder@26.8.1` to clear audit findings.
- `bdgen/web/package.json`, `bdgen/web/package-lock.json`: upgraded frontend tooling to Vite 7 (`vite@7.3.5`) with matching Vitest 4 coverage tooling (`vitest@4.1.8`, `@vitest/coverage-v8@4.1.8`); `npm audit` now reports 0 vulnerabilities.
- `bdgen/web/vite.config.js`: made the ESM config compatible with Vite 7 by deriving `__dirname` from `import.meta.url`.
- `bdgen/web/src/api.test.js`: updated mocked JSON responses to include `Headers`, matching the API client's content-type check under Vitest 4.
- `.gitignore`: ignores both the legacy generated static path (`bdgen/server/static/`) and the current backend-served static path (`bdgen/bdgen/server/static/`).
- Verification: frontend `npm run lint`, `npm test`, `npm run test:coverage`, `npm run build`, and `npm audit` OK. Vitest commands needed outside-sandbox execution on Windows due config-load read restrictions; production build still emits the existing chunk-size warning.

### 2026-05-20

- `.github/workflows/release-portable.yml`: hardened release workflow after `zizmor` audit by reducing default permissions to `contents: read`, granting `contents: write` only to tag/release jobs, disabling checkout credential persistence, pinning all GitHub Actions to immutable SHAs, and moving version/tag outputs into environment variables before shell use. Verification: `./zizmor ./.github/workflows/release-portable.yml` reports no findings.
- `bdgen/bdgen/models.py`, `bdgen/bdgen/script.py`, `bdgen/web/src/components/ProjectForm.jsx`: script model configs now persist per-project `effort` for compatible Claude adaptive-thinking models. The project form's generation-model section is split into Scénario, Images finales, Références visuelles, Sortie, and Upscale subsections; image quality variants use French labels and the dedicated references model no longer visually blends with the output-format selector.
- `bdgen/bdgen/script.py`, `bdgen/tests/test_anthropic_rate_limit.py`: Anthropic script generation now uses a configurable 30-minute timeout (`BDGEN_ANTHROPIC_TIMEOUT_SECONDS`) and defaults adaptive-thinking effort to `medium` (`BDGEN_ANTHROPIC_EFFORT`) for lower-latency Sonnet 4.6 page generation. Adaptive thinking is only enabled for documented adaptive-capable models. Targeted tests cover timeout, effort, model gating, and stream kwargs.
- `.gitignore`, `bdgen/bdgen/server/static/`: stopped tracking generated backend-served frontend assets and corrected the ignored path from `bdgen/server/static/` to `bdgen/bdgen/server/static/`. Local generated files remain on disk.
- `bdgen/desktop/main.js`, `bdgen/desktop/preload.js`: added a small Electron preferences bridge stored in `userData/preferences.json` for stable app-level preferences.
- `bdgen/web/src/App.jsx`, `bdgen/web/src/components/OnboardingWizard.jsx`: onboarding dismissal now reads Electron preferences before rendering and writes both Electron preferences and `localStorage`; this fixes desktop launches where the random localhost port changes the browser storage origin.
- `bdgen/web/src/components/OnboardingWizard.test.jsx`: added coverage for localStorage fallback, Electron preference reads, and dismissal writes.
- `bdgen/bdgen/server/static/`: rebuilt after the frontend change.
- Verification: targeted onboarding and Anthropic tests OK; frontend lint OK; desktop lint OK; targeted Prettier/Ruff OK; `npm run build` OK.

### 2026-05-12

- `bdgen/bdgen/references.py`, `bdgen/tests/test_references_xai_prompt.py`: Grok/xAI reference prompts now use compact input-image instructions and are trimmed below xAI's 8000-character prompt limit while preserving the subject opening and final style/negative constraints.
- `bdgen/bdgen/references.py`, `bdgen/tests/test_references_xai_prompt.py`: reinforced Grok input-image instructions so user photos/style refs are treated as required visual anchors; added coverage that xAI image inputs use `/images/edits` with base64 data URIs.
- Verification: `uv run pytest tests/test_references_xai_prompt.py tests/test_generation_options_sync.py` OK; latest targeted check `uv run pytest tests/test_references_xai_prompt.py` OK; Ruff check/format OK for touched backend files.

- `bdgen/bdgen/references.py`: added xAI/Grok reference image generation via the JSON image generation/edit endpoints, including style/photo input support with data URIs and PNG normalization.
- `bdgen/bdgen/service/_helpers.py`: compose image model remains OpenAI-only, while dedicated reference image models now preserve `provider: "xai"`.
- `bdgen/web/src/components/ProjectForm.jsx`: dedicated reference image model selector now offers xAI/Grok with `grok-imagine-image-quality` and `grok-imagine-image`; rebuilt `bdgen/bdgen/server/static/`.
- `bdgen/tests/test_generation_options_sync.py`: added coverage that xAI dedicated reference image config survives config load/save.
- Verification: `uv run pytest tests/test_generation_options_sync.py` OK; Ruff check/format OK; frontend lint OK; targeted Prettier OK; `npm run build` OK.

- `bdgen/bdgen/models.py`: added optional `generation_options.references.image_model` plus `GenerationOptions.reference_image_model()` fallback to the main image model.
- `bdgen/bdgen/cli.py`, `bdgen/bdgen/wizard.py`, `bdgen/bdgen/service/pipeline.py`: references generation now uses the dedicated references image model when configured; compose still uses `generation_options.image_model`.
- `bdgen/bdgen/service/_helpers.py`, `config.py`, `stale_detection.py`: main compose image config is coerced to OpenAI when needed; stale references/compose images are marked independently when their respective model changes.
- `bdgen/web/src/components/ProjectForm.jsx`: added a form toggle and fields for a dedicated references image model and quality.
- `bdgen/bdgen/server/static/`: rebuilt after the frontend change.
- Verification: `uv run pytest tests/test_generation_options_sync.py` OK; frontend lint OK; targeted Prettier OK for `ProjectForm.jsx`; `npm run build` OK outside sandbox after the known Windows/esbuild permission issue.

### 2026-05-07 (4)

- `bdgen/web/src/components/projectFormPresets.js`: new file with preset lists for genre, tone, setting, target audience, and the seven style fields used by the project form.
- `bdgen/web/src/components/ProjectForm.jsx`: replaced free-text inputs with a `ComboBox` helper that exposes the preset list plus a "Saisir manuellement…" entry. Pre-existing custom values are preserved (shown as custom on edit). Affected fields: `story.genre`, `story.tone`, `story.setting`, `story.target_audience`, and all of `style.*`.
- `bdgen/bdgen/server/static/`: rebuilt after the form change.
- Verification: frontend lint OK, Prettier OK, `npm run build` OK.

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
