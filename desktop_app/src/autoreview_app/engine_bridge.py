from __future__ import annotations

import sys
from pathlib import Path

# engine_bridge.py lives at desktop_app/src/autoreview_app/engine_bridge.py.
# parents[3] is the repo root; the engine source is Document_Decomposer/src.
ENGINE_SRC = Path(__file__).resolve().parents[3] / "Document_Decomposer" / "src"
if ENGINE_SRC.is_dir() and str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from docdecomp.package_builder import build_clean_package  # noqa: E402


def build_package_from_pdf():  # placeholder, implemented in Task 5
    raise NotImplementedError
