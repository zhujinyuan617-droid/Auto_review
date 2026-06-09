# Desktop App M1 — Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a double-clickable desktop skeleton: a local FastAPI service on `127.0.0.1` (random free port) exposing `/health` and `/library` (empty list when the library is empty), wrapped in a pywebview window that loads a minimal page showing the library count — proving the "脸 ↔ 插头 ↔ 引擎" link end to end.

**Architecture:** A new top-level Python package `desktop_app/` (sibling of `Document_Decomposer/` and `paper_pool/`). The FastAPI app is built by a `create_app(config)` factory so tests can inject a temp library directory. The pywebview GUI is isolated in `main.py` and imports `webview` lazily, so all logic is unit-testable headless. No engine (`docdecomp`) import in M1 — `/library` just lists subdirectories of the configured library dir.

**Tech Stack:** Python 3.11+ (`py` launcher on Windows), FastAPI, uvicorn, pywebview, httpx (for FastAPI `TestClient`), pytest. Vanilla HTML/JS frontend (no framework).

**Git:** This milestone is a substantial change → work on a branch `feat/desktop-app-m1` (per repo `CLAUDE.md`). Commit after each task. Do **not** push; the user merges after review.

**Source-of-truth note:** Per repo `CLAUDE.md`, generated dirs (`data/ library/ reports/`) and `.venv/` are git-ignored at the repo root already — only source under `desktop_app/src`, `desktop_app/tests`, `desktop_app/frontend`, and config files get committed.

---

## File Structure

Created in this milestone:

- `desktop_app/requirements.txt` — runtime + dev dependencies
- `desktop_app/conftest.py` — puts `src/` on `sys.path` for tests (mirrors the repo's existing `sys.path.insert` pattern)
- `desktop_app/README.md` — one-screen dev/run instructions
- `desktop_app/src/autoreview_app/__init__.py` — package marker + version
- `desktop_app/src/autoreview_app/config.py` — `AppConfig` (resolves the library directory)
- `desktop_app/src/autoreview_app/library_index.py` — `list_papers(library_dir)` (empty when missing/empty)
- `desktop_app/src/autoreview_app/api.py` — `create_app(config)` → FastAPI with `/health`, `/library`, `/`
- `desktop_app/src/autoreview_app/server.py` — `find_free_port`, `build_window_url`, `wait_until_serving`, `HOST`
- `desktop_app/src/autoreview_app/main.py` — `run_server`, `main` (starts server thread + opens pywebview window)
- `desktop_app/frontend/index.html` — minimal page that fetches `/library` and shows the count
- `desktop_app/tests/__init__.py` — empty
- `desktop_app/tests/test_library_index.py`
- `desktop_app/tests/test_config.py`
- `desktop_app/tests/test_api.py`
- `desktop_app/tests/test_server.py`

Each module has one responsibility: `config` resolves paths, `library_index` reads the library dir, `api` defines HTTP routes, `server` holds network helpers, `main` wires the GUI. They depend inward only (`api`→`config`+`library_index`; `main`→`api`+`config`+`server`).

All commands below assume the working directory is `desktop_app/` and use the milestone's own virtualenv at `desktop_app/.venv`.

---

### Task 1: Project scaffold + dependencies + smoke import

**Files:**
- Create: `desktop_app/requirements.txt`
- Create: `desktop_app/conftest.py`
- Create: `desktop_app/src/autoreview_app/__init__.py`
- Create: `desktop_app/tests/__init__.py`
- Test: `desktop_app/tests/test_smoke.py`

- [ ] **Step 1: Create the dependency list**

Create `desktop_app/requirements.txt`:

```text
fastapi>=0.110
uvicorn>=0.29
pywebview>=5.0
httpx>=0.27
pytest>=8.0
```

- [ ] **Step 2: Create the package marker**

Create `desktop_app/src/autoreview_app/__init__.py`:

```python
"""Auto Review desktop application (local FastAPI service + pywebview shell)."""

__version__ = "0.1.0"
```

Create `desktop_app/tests/__init__.py` as an empty file.

- [ ] **Step 3: Make `src/` importable in tests**

Create `desktop_app/conftest.py`:

```python
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

- [ ] **Step 4: Write the failing smoke test**

Create `desktop_app/tests/test_smoke.py`:

```python
def test_package_imports_and_has_version():
    import autoreview_app

    assert autoreview_app.__version__ == "0.1.0"
```

- [ ] **Step 5: Create the virtualenv and install dependencies**

Run (from `desktop_app/`):

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
```

Expected: pip installs fastapi, uvicorn, pywebview, httpx, pytest without error.

- [ ] **Step 6: Run the smoke test**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_smoke.py -v
```

Expected: PASS (1 passed).

- [ ] **Step 7: Commit**

```powershell
git checkout -b feat/desktop-app-m1
git add desktop_app/requirements.txt desktop_app/conftest.py desktop_app/src/autoreview_app/__init__.py desktop_app/tests/__init__.py desktop_app/tests/test_smoke.py
git commit -m "feat(desktop): scaffold autoreview_app package"
```

---

### Task 2: `list_papers` — read the library directory

**Files:**
- Create: `desktop_app/src/autoreview_app/library_index.py`
- Test: `desktop_app/tests/test_library_index.py`

- [ ] **Step 1: Write the failing tests**

Create `desktop_app/tests/test_library_index.py`:

```python
from pathlib import Path

from autoreview_app.library_index import list_papers


def test_missing_dir_returns_empty(tmp_path: Path):
    assert list_papers(tmp_path / "does_not_exist") == []


def test_empty_dir_returns_empty(tmp_path: Path):
    assert list_papers(tmp_path) == []


def test_lists_paper_subdirs_sorted_ignoring_files_and_hidden(tmp_path: Path):
    (tmp_path / "S02").mkdir()
    (tmp_path / "S01").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "index.json").write_text("{}", encoding="utf-8")

    assert list_papers(tmp_path) == ["S01", "S02"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_library_index.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.library_index'`.

- [ ] **Step 3: Write the minimal implementation**

Create `desktop_app/src/autoreview_app/library_index.py`:

```python
from __future__ import annotations

from pathlib import Path


def list_papers(library_dir: Path) -> list[str]:
    """Return sorted paper ids = names of visible subdirectories in the library.

    A paper id is one subdirectory of the library (e.g. ``S01``). Returns an
    empty list if the directory is missing or has no paper subdirectories.
    """
    if not library_dir.is_dir():
        return []
    return sorted(
        child.name
        for child in library_dir.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_library_index.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```powershell
git add desktop_app/src/autoreview_app/library_index.py desktop_app/tests/test_library_index.py
git commit -m "feat(desktop): list_papers reads library subdirectories"
```

---

### Task 3: `AppConfig` — resolve the library directory

**Files:**
- Create: `desktop_app/src/autoreview_app/config.py`
- Test: `desktop_app/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `desktop_app/tests/test_config.py`:

```python
from pathlib import Path

from autoreview_app.config import AppConfig


def test_from_env_uses_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AUTOREVIEW_LIBRARY_DIR", str(tmp_path / "mylib"))
    config = AppConfig.from_env()
    assert config.library_dir == tmp_path / "mylib"


def test_from_env_default_is_cwd_library(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AUTOREVIEW_LIBRARY_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    config = AppConfig.from_env()
    assert config.library_dir == tmp_path / "library"
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.config'`.

- [ ] **Step 3: Write the minimal implementation**

Create `desktop_app/src/autoreview_app/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_LIBRARY_DIR = "AUTOREVIEW_LIBRARY_DIR"
DEFAULT_LIBRARY_DIRNAME = "library"


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the desktop app."""

    library_dir: Path

    @classmethod
    def from_env(cls) -> "AppConfig":
        raw = os.environ.get(ENV_LIBRARY_DIR)
        if raw:
            return cls(library_dir=Path(raw))
        return cls(library_dir=Path.cwd() / DEFAULT_LIBRARY_DIRNAME)
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_config.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```powershell
git add desktop_app/src/autoreview_app/config.py desktop_app/tests/test_config.py
git commit -m "feat(desktop): AppConfig resolves library dir from env or cwd"
```

---

### Task 4: `create_app` — FastAPI with `/health` and `/library`

**Files:**
- Create: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Create `desktop_app/tests/test_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library_dir: Path) -> TestClient:
    return TestClient(create_app(AppConfig(library_dir=library_dir)))


def test_health_ok(tmp_path: Path):
    response = _client(tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_library_empty(tmp_path: Path):
    response = _client(tmp_path).get("/library")
    assert response.status_code == 200
    assert response.json() == {"papers": []}


def test_library_lists_papers(tmp_path: Path):
    (tmp_path / "S01").mkdir()
    response = _client(tmp_path).get("/library")
    assert response.json() == {"papers": ["S01"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.api'`.

- [ ] **Step 3: Write the minimal implementation**

Create `desktop_app/src/autoreview_app/api.py`:

```python
from __future__ import annotations

from fastapi import FastAPI

from .config import AppConfig
from .library_index import list_papers


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="Auto Review Desktop", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/library")
    def library() -> dict:
        return {"papers": list_papers(config.library_dir)}

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api.py
git commit -m "feat(desktop): FastAPI app with /health and /library"
```

---

### Task 5: Serve the minimal frontend at `/`

**Files:**
- Create: `desktop_app/frontend/index.html`
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api.py` (add one test)

- [ ] **Step 1: Add the failing test**

Append to `desktop_app/tests/test_api.py`:

```python
def test_index_html_served(tmp_path: Path):
    response = _client(tmp_path).get("/")
    assert response.status_code == 200
    assert "Auto Review" in response.text
    assert "/library" in response.text  # the page fetches the library endpoint
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_index_html_served -v
```

Expected: FAIL with status 404 (no `/` route yet).

- [ ] **Step 3: Create the frontend page**

Create `desktop_app/frontend/index.html`:

```html
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <title>Auto Review</title>
  </head>
  <body>
    <h1>Auto Review</h1>
    <p id="status">加载中…</p>
    <script>
      fetch("/library")
        .then((r) => r.json())
        .then((d) => {
          const n = (d.papers || []).length;
          document.getElementById("status").textContent =
            n === 0 ? "藏书为空,先去导入论文" : `藏书 ${n} 篇`;
        })
        .catch(() => {
          document.getElementById("status").textContent = "连接后端失败";
        });
    </script>
  </body>
</html>
```

- [ ] **Step 4: Add the `/` route**

In `desktop_app/src/autoreview_app/api.py`, change the imports at the top:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .config import AppConfig
from .library_index import list_papers

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
```

Then add this route inside `create_app`, before `return app`:

```python
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")
```

- [ ] **Step 5: Run the API tests to verify they pass**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api.py -v
```

Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```powershell
git add desktop_app/frontend/index.html desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api.py
git commit -m "feat(desktop): serve minimal frontend at /"
```

---

### Task 6: Network helpers — port, URL, readiness

**Files:**
- Create: `desktop_app/src/autoreview_app/server.py`
- Test: `desktop_app/tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

Create `desktop_app/tests/test_server.py`:

```python
import socket

from autoreview_app.server import (
    HOST,
    build_window_url,
    find_free_port,
    wait_until_serving,
)


def test_host_is_loopback():
    assert HOST == "127.0.0.1"


def test_find_free_port_is_bindable():
    port = find_free_port()
    assert isinstance(port, int)
    # The returned port must be free to bind on the loopback interface.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, port))


def test_build_window_url():
    assert build_window_url(HOST, 8123) == "http://127.0.0.1:8123/"


def test_wait_until_serving_true_when_listening():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((HOST, 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        assert wait_until_serving(HOST, port, timeout=2.0) is True


def test_wait_until_serving_false_on_timeout():
    # find_free_port gives a port nobody is listening on.
    port = find_free_port()
    assert wait_until_serving(HOST, port, timeout=0.5) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_server.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.server'`.

- [ ] **Step 3: Write the minimal implementation**

Create `desktop_app/src/autoreview_app/server.py`:

```python
from __future__ import annotations

import socket
import time

HOST = "127.0.0.1"


def find_free_port() -> int:
    """Ask the OS for a free TCP port on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def build_window_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/"


def wait_until_serving(host: str, port: int, timeout: float = 10.0) -> bool:
    """Poll until something accepts TCP connections at host:port, or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            if s.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_server.py -v
```

Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```powershell
git add desktop_app/src/autoreview_app/server.py desktop_app/tests/test_server.py
git commit -m "feat(desktop): port/url/readiness network helpers"
```

---

### Task 7: Wire the GUI entry point + README + full-suite check

**Files:**
- Create: `desktop_app/src/autoreview_app/main.py`
- Create: `desktop_app/README.md`

- [ ] **Step 1: Write `main.py`**

Create `desktop_app/src/autoreview_app/main.py`:

```python
from __future__ import annotations

import threading

import uvicorn

from .api import create_app
from .config import AppConfig
from .server import HOST, build_window_url, find_free_port, wait_until_serving


def run_server(app, host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    config = AppConfig.from_env()
    app = create_app(config)
    port = find_free_port()

    thread = threading.Thread(
        target=run_server, args=(app, HOST, port), daemon=True
    )
    thread.start()

    if not wait_until_serving(HOST, port, timeout=15.0):
        raise RuntimeError(f"backend did not start on {HOST}:{port}")

    import webview  # local import so headless tests never load a GUI backend

    webview.create_window("Auto Review", build_window_url(HOST, port))
    webview.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the non-GUI logic imports cleanly**

This step confirms `main.py` is importable without launching a window (the `webview` import is inside `main()`, so importing the module must not require a GUI).

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -c "import sys; sys.path.insert(0, 'src'); import autoreview_app.main as m; print('run_server' in dir(m) and 'main' in dir(m))"
```

Expected: prints `True`.

- [ ] **Step 3: Write the README**

Create `desktop_app/README.md`:

```markdown
# Auto Review Desktop (M1 skeleton)

Local FastAPI service + pywebview window. M1 only proves the link:
window opens → calls `/library` → shows the library count.

## Dev setup (Windows PowerShell, from this folder)

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run the tests

```powershell
.venv\Scripts\python -m pytest -v
```

## Launch the app (manual smoke)

```powershell
.venv\Scripts\python -m autoreview_app.main
```

A window titled "Auto Review" opens and shows "藏书为空,先去导入论文"
(the default library dir `./library` does not exist yet).

To point at a real library directory:

```powershell
$env:AUTOREVIEW_LIBRARY_DIR = "D:\path\to\library"
.venv\Scripts\python -m autoreview_app.main
```
```

- [ ] **Step 4: Run the FULL test suite**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -v
```

Expected: PASS — all tests from Tasks 1–6 green (smoke 1 + library_index 3 + config 2 + api 4 + server 5 = 15 passed).

- [ ] **Step 5: Manual GUI smoke test**

Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m autoreview_app.main
```

Expected: a desktop window titled "Auto Review" opens and displays "藏书为空,先去导入论文". Close the window to exit. (This step is manual because pywebview needs a real display; it is not part of the automated suite.)

- [ ] **Step 6: Commit**

```powershell
git add desktop_app/src/autoreview_app/main.py desktop_app/README.md
git commit -m "feat(desktop): pywebview entry point + dev README"
```

---

## Done criteria for M1

- `desktop_app/` package exists with focused modules (`config`, `library_index`, `api`, `server`, `main`).
- `.venv\Scripts\python -m pytest -v` is fully green (15 tests).
- `py -m autoreview_app.main` opens a window that reads `/library` and shows the count.
- All work committed on branch `feat/desktop-app-m1`; nothing pushed; user merges after review.

## Out of scope for M1 (handled by later milestones)

- Engine (`docdecomp`) integration, real extraction, cards, network — M2+.
- Packaging/installer + consent form for dependency install — M7.
- Discovery/download, research-group clustering, single-paper view, writing — M3–M6.
