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
