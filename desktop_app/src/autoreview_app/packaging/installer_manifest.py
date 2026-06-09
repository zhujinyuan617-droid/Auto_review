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
