from __future__ import annotations

from pathlib import Path

from .. import engine_bridge  # noqa: F401  # ensures engine src is on sys.path

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config


def build_ai_client(config_root: Path, config_path: Path | None = None) -> OpenAICompatibleClient:
    """Build the engine's real AI client from config (file or env). No network here."""
    config = load_ai_config(config_root, config_path)
    return OpenAICompatibleClient(config)
