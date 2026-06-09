# Build the Auto Review desktop app installer (Windows). Run from desktop_app/.
# NOT verified in CI — run on a real Windows machine with a display.
$ErrorActionPreference = "Stop"
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\pyinstaller packaging\autoreview.spec --noconfirm
Write-Host "Build output in dist\AutoReview. Launch dist\AutoReview\AutoReview.exe to smoke-test."
