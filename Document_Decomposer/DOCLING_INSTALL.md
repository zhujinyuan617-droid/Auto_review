# Docling Install

Document Decomposer uses Docling to convert staged PDFs into JSON and Markdown.

The active Docling environment is:

```text
envs\docling
```

The runner looks for Docling in this order:

1. `--docling-cmd`
2. `docling` on `PATH`
3. `envs\docling\Scripts\docling.exe`

`tool_bakeoff` is historical and should not provide the mainline Docling runtime.

## Install

From the `Document_Decomposer` project root:

```powershell
py -m venv envs\docling
.\envs\docling\Scripts\python.exe -m pip install --upgrade pip
.\envs\docling\Scripts\python.exe -m pip install docling
.\envs\docling\Scripts\docling.exe --version
```

This follows the official Docling installation guide:

```text
https://docling.site/installation/
```

The guide recommends installing Docling with pip, preferably inside a virtual
environment, and then verifying the installation with `docling --version`.

Current local install:

```text
Docling version: 2.97.0
Docling Core version: 2.78.1
Docling IBM Models version: 3.13.3
Docling Parse version: 6.2.0
Python: cpython-312 (3.12.10)
Platform: Windows-11-10.0.26200-SP0
```

## Verify Runner Wiring

Dry-run a known paper:

```powershell
py .\scripts\run_from_paper_downloads.py --paper-id S14 --skip-ingest --dry-run
```

The printed Docling command should use:

```text
envs\docling\Scripts\docling.exe
```

## Reinstall

If the environment breaks:

```powershell
Remove-Item -Recurse -Force .\envs\docling
py -m venv envs\docling
.\envs\docling\Scripts\python.exe -m pip install --upgrade pip
.\envs\docling\Scripts\python.exe -m pip install docling
.\envs\docling\Scripts\docling.exe --version
```

Do not restore Docling from `tool_bakeoff`; rebuild this dedicated environment
instead.
