from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ai_client import AIConfig
from .io_utils import write_json


SCHEMA_VERSION = "0.1.0"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_hash(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(text)


def meta_path_for(output_path: Path) -> Path:
    return output_path.with_suffix(".meta.json")


def build_ai_fingerprint(
    *,
    stage: str,
    paper_id: str,
    messages: list[dict[str, str]],
    schema_hint: str,
    config: AIConfig,
    input_paths: dict[str, Path],
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    input_hashes = {
        name: sha256_file(path) if path.exists() else None
        for name, path in sorted(input_paths.items())
    }
    prompt_hash = stable_json_hash(
        {
            "messages": messages,
            "schema_hint": schema_hint,
        }
    )
    fingerprint = {
        "stage": stage,
        "paper_id": paper_id,
        "prompt_hash": prompt_hash,
        "input_hashes": input_hashes,
        "ai": {
            "provider": config.provider,
            "base_url_hash": sha256_text(config.base_url),
            "model": config.model,
            "temperature": config.temperature,
        },
        "parameters": parameters or {},
    }
    fingerprint["cache_key"] = stable_json_hash(fingerprint)
    return fingerprint


def cache_hit(
    *,
    meta_path: Path,
    required_outputs: list[Path],
    fingerprint: dict[str, Any],
) -> bool:
    if not meta_path.exists():
        return False
    if any(not output.exists() for output in required_outputs):
        return False
    try:
        cached = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return cached.get("fingerprint") == fingerprint


def write_ai_cache_meta(
    *,
    meta_path: Path,
    fingerprint: dict[str, Any],
    outputs: list[Path],
) -> None:
    write_json(
        meta_path,
        {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint": fingerprint,
            "outputs": [str(path) for path in outputs],
        },
    )
