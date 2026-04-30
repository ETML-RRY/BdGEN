# PyInstaller spec for the local FastAPI server used by Electron.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path.cwd()
static_dir = root / "bdgen" / "server" / "static"

datas = []
if static_dir.exists():
    datas.append((str(static_dir), "bdgen/server/static"))

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("pydantic")
    + collect_submodules("PIL")
)

a = Analysis(
    ["bdgen/server/__main__.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="bdgen-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
