# PyInstaller spec for the Mudranalaya ERP-MIS Windows executable.
#
# Build (on a Windows machine, or in a Windows CI runner - PyInstaller
# produces a native executable for whatever OS it's RUN on, so a Windows
# .exe must be built on Windows):
#
#   pip install -r backend/requirements.txt pyinstaller
#   pyinstaller mudranalaya.spec
#
# Output: dist/Mudranalaya/Mudranalaya.exe (onedir build - recommended over
# onefile for a server-style app: faster startup, easier to inspect logs).

import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH)

a = Analysis(
    ['desktop_entry.py'],
    pathex=[str(project_root), str(project_root / 'backend')],
    binaries=[],
    datas=[
        (str(project_root / 'backend' / 'app'), 'backend/app'),
        (str(project_root / 'frontend'), 'frontend'),
    ],
    hiddenimports=[
        'app.main', 'app.models', 'app.api.routers.auth', 'app.api.routers.materials',
        'app.api.routers.requests', 'app.api.routers.purchasing', 'app.api.routers.production',
        'app.api.routers.accounts', 'app.api.routers.costing', 'app.api.routers.users',
        'app.api.routers.audit', 'app.api.routers.notifications', 'app.api.routers.reports',
        'app.api.routers.forecasting', 'app.api.routers.dashboard', 'app.api.routers.licensing',
        'app.api.routers.ws_routes', 'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on', 'argon2',
        # psycopg2 is optional at build time - only required if the office deploys against
        # PostgreSQL rather than SQLite. Installed and bundled automatically if present;
        # a PostgreSQL deployment must `pip install psycopg2-binary` before building the exe.
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Mudranalaya',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep a console window so office IT can see server logs/errors
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='Mudranalaya',
)
