from __future__ import annotations

import os
from pathlib import Path

from .. import engine_bridge  # noqa: F401  # ensures engine src is on sys.path
from .. import settings as app_settings

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config


def build_ai_client(config_root: Path, config_path: Path | None = None) -> OpenAICompatibleClient:
    """Build the engine's real AI client from config. The OS-keychain key (if set
    and no explicit env override) is injected so a key entered in Settings reaches
    the engine. Precedence: DOCDECOMP_AI_API_KEY env > keychain > config file."""
    key = app_settings.get_api_key()
    if key and not os.environ.get("DOCDECOMP_AI_API_KEY"):
        os.environ["DOCDECOMP_AI_API_KEY"] = key
    config = load_ai_config(config_root, config_path)
    return OpenAICompatibleClient(config)
