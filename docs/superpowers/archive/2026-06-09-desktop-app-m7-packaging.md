# Desktop App M7 — Packaging, settings/keychain, install scaffolding

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app installable and configurable, and provide the packaging scaffolding for a distributable build. Deliver the verifiable pieces fully (an installable package via `pyproject.toml`; API-key storage in the OS keychain with settings endpoints; a consent/dependency manifest), and the parts that need a real machine (PyInstaller build, GUI launch, macOS signing) as clearly-marked, unverified scaffolding + a run-on-your-machine checklist.

**Architecture:** `pyproject.toml` makes `autoreview_app` a real installable package (so `python -m autoreview_app.main` works without the M1 `PYTHONPATH` hack). `settings.py` wraps `keyring` to store the user's API key in the OS credential store (never logged, never returned over HTTP — only presence is exposed). `packaging/installer_manifest.py` is the data + consent gate for the "install lightweight deps at setup" flow. The PyInstaller spec + build scripts + `PACKAGING.md` describe producing the installer; **they cannot be verified in this sandbox** (no display, no installer test harness, no macOS) and are labeled as such.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), `keyring` (new dep), PyInstaller (build-time only), setuptools, FastAPI, pytest.

**Git:** branch `feat/desktop-app-m7`; commit per task; no push; user merges after review.

**Depends on:** all prior milestones (M1–M6). Run from `desktop_app/` with `.venv\Scripts\python`.

**Honesty note (per repo CLAUDE.md):** Tasks 1–3 are fully test-verified. Task 4 (PyInstaller/build/sign) is scaffolding that is **not verified** in this environment; its done-criteria are "files present + internally consistent", and `PACKAGING.md` states the verification must happen on the user's Windows/macOS machine.

---

## File Structure (all under `desktop_app/`)

- `pyproject.toml` — installable package config (setuptools, package in `src/`)
- `src/autoreview_app/settings.py` — `set_api_key`, `get_api_key`, `has_api_key`, `clear_api_key` (keyring)
- `src/autoreview_app/api.py` — MODIFY: `GET /settings/apikey` (presence), `POST /settings/apikey`, `DELETE /settings/apikey`
- `src/autoreview_app/packaging/__init__.py`, `src/autoreview_app/packaging/installer_manifest.py` — bundled-deps list + consent gate
- `packaging/autoreview.spec`, `packaging/build.ps1`, `PACKAGING.md` — build scaffolding (unverified)
- `requirements.txt` — add `keyring`
- Tests: `tests/test_settings.py`, `tests/test_api_settings.py`, `tests/test_installer_manifest.py`, `tests/test_packaging_present.py`

---

### Task 1: Installable package (`pyproject.toml`)

**Files:**
- Create: `desktop_app/pyproject.toml`
- Test: `desktop_app/tests/test_packaging_install.py`

- [ ] **Step 1: Write the failing test** — `desktop_app/tests/test_packaging_install.py`:

```python
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def test_module_importable_without_pythonpath_hack():
    # With the package installed (editable), autoreview_app must import using the
    # bare interpreter — no sys.path injection, no PYTHONPATH, run from a neutral cwd.
    result = subprocess.run(
        [sys.executable, "-c", "import autoreview_app; import autoreview_app.config; print('ok')"],
        cwd=PROJECT.parent,  # repo root, NOT desktop_app
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
```

- [ ] **Step 2: Run to verify it fails** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_packaging_install.py -v
```

Expected: FAIL — `autoreview_app` is not importable by the bare interpreter from the repo root (no editable install yet).

- [ ] **Step 3: Create `pyproject.toml`** — `desktop_app/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "autoreview-app"
version = "0.1.0"
description = "Auto Review desktop app (local FastAPI + pywebview over the Document Decomposer engine)"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pywebview>=5.0",
    "pymupdf>=1.24",
    "keyring>=24.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]

[project.scripts]
autoreview = "autoreview_app.main:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 4: Editable-install the package** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pip install -e .
```

Expected: installs `autoreview-app` in editable mode without error.

- [ ] **Step 5: Run to verify it passes** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_packaging_install.py -v
```

Expected: PASS (1 passed). Then run the FULL suite to confirm the editable install didn't break the existing path-based imports: `.venv\Scripts\python -m pytest -q` → all green (the existing `conftest.py` sys.path insert is now redundant but harmless). Report the summary line. If the full suite breaks (e.g. a duplicate-module import error), STOP and report.

- [ ] **Step 6: Commit.**

```powershell
git checkout -b feat/desktop-app-m7
git add desktop_app/pyproject.toml desktop_app/tests/test_packaging_install.py
git commit -m "feat(desktop): installable package via pyproject (no PYTHONPATH hack)"
```

---

### Task 2: Settings — API key in the OS keychain

**Files:**
- Modify: `desktop_app/requirements.txt`
- Create: `desktop_app/src/autoreview_app/settings.py`
- Test: `desktop_app/tests/test_settings.py`

- [ ] **Step 1: Add `keyring` to requirements** and install. Append `keyring>=24.0` to `desktop_app/requirements.txt`, then (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

- [ ] **Step 2: Write the failing tests** — `desktop_app/tests/test_settings.py`:

```python
import keyring
from keyring.backends.fail import Keyring as FailKeyring  # placeholder import; replaced below

import pytest


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    # Use an in-memory keyring backend so tests never touch the real OS store.
    store: dict[tuple[str, str], str] = {}

    class MemoryKeyring:
        def set_password(self, service, username, password):
            store[(service, username)] = password

        def get_password(self, service, username):
            return store.get((service, username))

        def delete_password(self, service, username):
            store.pop((service, username), None)

    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: MemoryKeyring().set_password(s, u, p))
    monkeypatch.setattr(keyring, "get_password", lambda s, u: store.get((s, u)))
    monkeypatch.setattr(keyring, "delete_password", lambda s, u: store.pop((s, u), None))
    return store


def test_set_and_has_and_clear():
    from autoreview_app import settings

    assert settings.has_api_key() is False
    settings.set_api_key("secret-key-123")
    assert settings.has_api_key() is True
    assert settings.get_api_key() == "secret-key-123"
    settings.clear_api_key()
    assert settings.has_api_key() is False
    assert settings.get_api_key() is None


def test_blank_key_is_rejected():
    from autoreview_app import settings

    with pytest.raises(ValueError):
        settings.set_api_key("   ")
```

- [ ] **Step 3: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_settings.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.settings'`.

- [ ] **Step 4: Implement** — `desktop_app/src/autoreview_app/settings.py`:

```python
from __future__ import annotations

import keyring

# Where the user's API key lives in the OS credential store. The value is never
# logged and never returned over HTTP — callers can only ask whether it is set.
_SERVICE = "autoreview-app"
_USERNAME = "deepseek-api-key"


def set_api_key(value: str) -> None:
    """Store the API key in the OS keychain. Rejects a blank value."""
    if not value or not value.strip():
        raise ValueError("api key must not be blank")
    keyring.set_password(_SERVICE, _USERNAME, value.strip())


def get_api_key() -> str | None:
    """Return the stored API key (for in-process use only), or None."""
    return keyring.get_password(_SERVICE, _USERNAME)


def has_api_key() -> bool:
    return bool(get_api_key())


def clear_api_key() -> None:
    keyring.delete_password(_SERVICE, _USERNAME)
```

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_settings.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/requirements.txt desktop_app/src/autoreview_app/settings.py desktop_app/tests/test_settings.py
git commit -m "feat(desktop): API key stored in OS keychain via keyring"
```

---

### Task 3: Settings endpoints + dependency/consent manifest

**Files:**
- Create: `desktop_app/src/autoreview_app/packaging/__init__.py`
- Create: `desktop_app/src/autoreview_app/packaging/installer_manifest.py`
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_installer_manifest.py`, `desktop_app/tests/test_api_settings.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_installer_manifest.py`:

```python
from autoreview_app.packaging.installer_manifest import bundled_dependencies, consent_summary


def test_bundled_dependencies_are_lightweight():
    deps = bundled_dependencies()
    names = {d["name"] for d in deps}
    # The lightweight runtime deps are bundled at install; Docling (heavy) is NOT.
    assert {"fastapi", "uvicorn", "pywebview", "pymupdf", "keyring"} <= names
    assert "docling" not in names
    assert all(d.get("purpose") for d in deps)  # every dep explains why it's there


def test_consent_summary_lists_deps_and_requires_consent():
    summary = consent_summary()
    assert summary["consent_required"] is True
    assert len(summary["will_install"]) == len(bundled_dependencies())
    assert "docling" in summary["optional_later"].lower() or summary["optional_later"]
```

And `desktop_app/tests/test_api_settings.py`:

```python
from pathlib import Path

import keyring
import pytest
from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: store.__setitem__((s, u), p))
    monkeypatch.setattr(keyring, "get_password", lambda s, u: store.get((s, u)))
    monkeypatch.setattr(keyring, "delete_password", lambda s, u: store.pop((s, u), None))
    return store


def _client(tmp_path: Path):
    return TestClient(create_app(AppConfig(library_dir=tmp_path / "library")))


def test_apikey_lifecycle_never_leaks_key(tmp_path: Path):
    client = _client(tmp_path)
    assert client.get("/settings/apikey").json() == {"configured": False}

    resp = client.post("/settings/apikey", json={"api_key": "sk-secret-xyz"})
    assert resp.status_code == 200
    # The response must NOT echo the key back.
    assert "sk-secret-xyz" not in resp.text
    assert client.get("/settings/apikey").json() == {"configured": True}

    client.delete("/settings/apikey")
    assert client.get("/settings/apikey").json() == {"configured": False}


def test_setup_manifest_endpoint(tmp_path: Path):
    body = _client(tmp_path).get("/settings/setup-manifest").json()
    assert body["consent_required"] is True
    assert body["will_install"]
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_installer_manifest.py tests/test_api_settings.py -v
```

Expected: FAIL — module + routes don't exist.

- [ ] **Step 3: Implement the manifest** — `desktop_app/src/autoreview_app/packaging/__init__.py`:

```python
"""Packaging support: install-time dependency manifest + consent gate."""
```

`desktop_app/src/autoreview_app/packaging/installer_manifest.py`:

```python
from __future__ import annotations

from typing import Any

# Lightweight runtime deps installed at setup time (after the consent form).
# Heavy/optional components (Docling, Sci-Hub plugin, screenshot plugin) are NOT
# here — they are installed on demand later.
_BUNDLED = [
    {"name": "fastapi", "purpose": "local API server"},
    {"name": "uvicorn", "purpose": "ASGI server runtime"},
    {"name": "pywebview", "purpose": "native desktop window"},
    {"name": "pymupdf", "purpose": "default PDF text extraction"},
    {"name": "keyring", "purpose": "store the API key in the OS keychain"},
]


def bundled_dependencies() -> list[dict[str, str]]:
    """The lightweight deps installed at setup (each with a one-line purpose)."""
    return [dict(d) for d in _BUNDLED]


def consent_summary() -> dict[str, Any]:
    """What the setup consent form should present before installing anything."""
    return {
        "consent_required": True,
        "will_install": bundled_dependencies(),
        "optional_later": "Docling (high-quality extraction) and the Sci-Hub / "
        "screenshot download plugins are heavy/optional and are installed on "
        "demand later, not at setup.",
        "note": "Declining the install means the app cannot run.",
    }
```

- [ ] **Step 4: Add the settings routes.** In `desktop_app/src/autoreview_app/api.py`, add imports near the other local imports:

```python
from . import settings as app_settings
from .packaging.installer_manifest import consent_summary
```

Add a request model near the others:

```python
class ApiKeyRequest(BaseModel):
    api_key: str
```

Inside `create_app`, before `return app`, add:

```python
    @app.get("/settings/apikey")
    def get_apikey() -> dict:
        return {"configured": app_settings.has_api_key()}

    @app.post("/settings/apikey")
    def set_apikey(req: ApiKeyRequest) -> dict:
        try:
            app_settings.set_api_key(req.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"configured": True}

    @app.delete("/settings/apikey")
    def delete_apikey() -> dict:
        if app_settings.has_api_key():
            app_settings.clear_api_key()
        return {"configured": False}

    @app.get("/settings/setup-manifest")
    def setup_manifest() -> dict[str, Any]:
        return consent_summary()
```

(Leave existing routes unchanged.)

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_installer_manifest.py tests/test_api_settings.py -v
```

Expected: PASS (2 + 2 = 4 passed). Then run the FULL suite: `.venv\Scripts\python -m pytest -q` → all green. Report the summary line.

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/packaging/__init__.py desktop_app/src/autoreview_app/packaging/installer_manifest.py desktop_app/src/autoreview_app/api.py desktop_app/tests/test_installer_manifest.py desktop_app/tests/test_api_settings.py
git commit -m "feat(desktop): settings/apikey routes + install consent manifest"
```

---

### Task 4: Build scaffolding (UNVERIFIED — runs on the user's machine)

**Files:**
- Create: `desktop_app/packaging/autoreview.spec`
- Create: `desktop_app/packaging/build.ps1`
- Create: `desktop_app/PACKAGING.md`
- Test: `desktop_app/tests/test_packaging_present.py`

This task delivers the build scaffolding. It is **NOT verified in this environment** (no display, no installer harness, no macOS). The test only asserts the files exist and are non-empty; `PACKAGING.md` documents the on-machine verification the user must run.

- [ ] **Step 1: Write the failing test** — `desktop_app/tests/test_packaging_present.py`:

```python
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "packaging"
ROOT = Path(__file__).resolve().parents[1]


def test_build_scaffolding_present():
    spec = PKG / "autoreview.spec"
    build = PKG / "build.ps1"
    doc = ROOT / "PACKAGING.md"
    for path in (spec, build, doc):
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").strip(), f"{path} is empty"
    # The doc must state that GUI/installer/signing are verified on the user's machine.
    text = doc.read_text(encoding="utf-8").lower()
    assert "not verified" in text or "on your machine" in text
```

- [ ] **Step 2: Run to verify it fails** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_packaging_present.py -v
```

Expected: FAIL — files don't exist.

- [ ] **Step 3: Create the PyInstaller spec** — `desktop_app/packaging/autoreview.spec`:

```python
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
```

- [ ] **Step 4: Create the build script** — `desktop_app/packaging/build.ps1`:

```powershell
# Build the Auto Review desktop app installer (Windows). Run from desktop_app/.
# NOT verified in CI — run on a real Windows machine with a display.
$ErrorActionPreference = "Stop"
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\pyinstaller packaging\autoreview.spec --noconfirm
Write-Host "Build output in dist\AutoReview. Launch dist\AutoReview\AutoReview.exe to smoke-test."
```

- [ ] **Step 5: Create the packaging doc** — `desktop_app/PACKAGING.md`:

```markdown
# Packaging the Auto Review desktop app

> These steps are **NOT verified in CI** — they must be run **on your machine**
> (a real Windows or macOS box with a display). The Python pieces (installable
> package, settings/keychain, the consent manifest) ARE unit-tested; the
> installer, the GUI window, and macOS signing are not.

## Windows
1. From `desktop_app/`: `packaging\build.ps1`
2. Smoke-test: launch `dist\AutoReview\AutoReview.exe`. A window titled
   "Auto Review" should open and show the empty library.

## macOS (outline)
1. `pip install -e . && pip install pyinstaller`
2. `pyinstaller packaging/autoreview.spec --noconfirm`
3. Code-sign + notarize the `.app` (requires an Apple Developer ID):
   `codesign --deep --force --options runtime --sign "Developer ID Application: …" dist/AutoReview.app`
   then `xcrun notarytool submit …` and `xcrun stapler staple`.

## Install consent (both OSes)
At setup, show the user `GET /settings/setup-manifest` (the consent summary):
the lightweight deps that will be installed, and that Docling / the Sci-Hub and
screenshot plugins are heavy/optional and installed on demand later. Declining
means the app can't run.

## What still needs doing before distribution
- Run the GUI smoke test above on a clean machine.
- macOS: real Developer ID signing + notarization.
- Bundle/relocate the Document Decomposer engine (`Document_Decomposer/`), which
  the app imports via `engine_bridge` — currently it expects the monorepo layout.
```

- [ ] **Step 6: Run to verify it passes** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_packaging_present.py -v
```

Expected: PASS (1 passed). Then run the FULL suite `.venv\Scripts\python -m pytest -q` → all green. Report the summary line.

- [ ] **Step 7: Commit.**

```powershell
git add desktop_app/packaging/autoreview.spec desktop_app/packaging/build.ps1 desktop_app/PACKAGING.md desktop_app/tests/test_packaging_present.py
git commit -m "feat(desktop): build scaffolding + packaging doc (unverified, run on machine)"
```

---

## Done criteria for M7

- **Verified:** `pyproject.toml` makes the package installable (`python -m autoreview_app.main` resolves without the PYTHONPATH hack); API key stored in the OS keychain; `/settings/apikey` (GET presence / POST set / DELETE) never leaks the key; `/settings/setup-manifest` returns the consent summary; the consent/dependency manifest module.
- **Unverified scaffolding (clearly labeled):** PyInstaller spec + build script + `PACKAGING.md` with the on-machine verification checklist (GUI smoke, macOS signing, engine bundling).
- Full suite green. Branch `feat/desktop-app-m7`; not pushed.

## Out of scope (the genuine remaining work, documented in PACKAGING.md)

- Running the GUI smoke test on a clean machine; macOS Developer ID signing + notarization; bundling/relocating the engine so the app doesn't depend on the monorepo layout; the Docling on-demand installer; the actual consent-form UI.

---

## Self-review (planner)

- **Coverage vs design §4 (install/consent), §5.7 (packaging), §5.8 (keychain), §10 (signing risk) + roadmap M7:** installable package, keychain API key + endpoints, consent/dependency manifest + endpoint (all verified); PyInstaller spec + build + signing doc (scaffolding, labeled unverified per the repo's "don't claim done without verification" rule). ✓
- **Placeholders:** none — full file content per step. The unverifiable parts are explicitly labeled, not faked as verified. ✓
- **Type/name consistency:** `set_api_key/get_api_key/has_api_key/clear_api_key` (Task 2) used by the settings routes (Task 3); `bundled_dependencies/consent_summary` (Task 3 manifest) used by the manifest test + the setup-manifest route. `create_app` signature unchanged (routes added inside). `ApiKeyRequest` next to existing models. ✓
