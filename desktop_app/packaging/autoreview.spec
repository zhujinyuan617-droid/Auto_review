# PyInstaller spec for the Auto Review desktop app.
# Build on the target OS:  pyinstaller packaging/autoreview.spec
# NOTE: not verified in CI; run on a real Windows/macOS machine with a display.
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ["src/autoreview_app/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[("frontend", "frontend")],  # ship the HTML UI
    hiddenimports=collect_submodules("uvicorn") + ["webview"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["docling", "torch"],  # heavy; installed on demand, never bundled
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="AutoReview",
    console=False,  # GUI app, no console window
)
coll = COLLECT(exe, a.binaries, a.datas, name="AutoReview")
