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

```powershell
.venv\Scripts\python -m autoreview_app.main
```

A window titled "Auto Review" opens and shows the library status (the default
library dir `./library` does not exist yet, so it shows the empty message).

To point at a real library directory, set `AUTOREVIEW_LIBRARY_DIR` before launching.
