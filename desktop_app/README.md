# Auto Review Desktop (M1 skeleton)

Local FastAPI service + pywebview window. M1 only proves the link:
window opens, calls `/library`, shows the library count.

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

The package lives under `src/`, so put it on `PYTHONPATH` when launching
(tests already get this from `conftest.py`; a proper installable entry point
is deferred to the packaging milestone):

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python -m autoreview_app.main
```

A window titled "Auto Review" opens and shows the library status (the default
library dir `./library` does not exist yet, so it shows the empty message).

To point at a real library directory, set `AUTOREVIEW_LIBRARY_DIR` before launching:

```powershell
$env:AUTOREVIEW_LIBRARY_DIR = "D:\path\to\library"
$env:PYTHONPATH = "src"
.venv\Scripts\python -m autoreview_app.main
```
