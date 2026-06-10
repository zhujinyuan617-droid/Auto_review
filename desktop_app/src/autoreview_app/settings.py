from __future__ import annotations

import json
from pathlib import Path

import keyring
import keyring.errors

# Where the user's API key lives in the OS credential store. The value is never
# logged and never returned over HTTP — callers can only ask whether it is set.
_SERVICE = "autoreview-app"
_USERNAME = "deepseek-api-key"


def set_api_key(value: str) -> None:
    """Store the API key in the OS keychain. Rejects a blank value."""
    if not value or not value.strip():
        raise ValueError("api key must not be blank")
    keyring.set_password(_SERVICE, _USERNAME, value.strip())


def get_api_key() -> str | None:
    """Return the stored API key (for in-process use only), or None."""
    return keyring.get_password(_SERVICE, _USERNAME)


def has_api_key() -> bool:
    return bool(get_api_key())


def clear_api_key() -> None:
    try:
        keyring.delete_password(_SERVICE, _USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass  # real backends raise when no key is set; clearing is idempotent here


# ---------------------------------------------------------------------------
# AI 并行数设置(普通 JSON,不是机密,不进钥匙串)。
# DeepSeek 账号级并发上限(2026-06 官方):flash 2500 / pro 500;超限只会收 429,
# 不会更快,所以校验直接以官方上限为界(账号扩容后再放宽)。
# ---------------------------------------------------------------------------

PARALLEL_LIMITS = {"flash": 2500, "pro": 500}
DEFAULT_PARALLEL = {"flash": 2500, "pro": 500}


def _read_settings_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get_parallel(path: Path) -> dict[str, int]:
    """Read {'flash': n, 'pro': n}; missing/invalid entries fall back to defaults."""
    raw = _read_settings_file(path).get("parallel")
    if not isinstance(raw, dict):
        raw = {}
    out: dict[str, int] = {}
    for tier, default in DEFAULT_PARALLEL.items():
        value = raw.get(tier)
        valid = (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 1 <= value <= PARALLEL_LIMITS[tier]
        )
        out[tier] = value if valid else default
    return out


def set_parallel(path: Path, flash: int, pro: int) -> dict[str, int]:
    """Validate and persist; returns the stored mapping. Raises ValueError out of range."""
    for tier, value in (("flash", flash), ("pro", pro)):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 1 <= value <= PARALLEL_LIMITS[tier]
        ):
            raise ValueError(f"{tier} parallel must be an int in 1..{PARALLEL_LIMITS[tier]}")
    data = _read_settings_file(path)
    data["parallel"] = {"flash": flash, "pro": pro}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(data["parallel"])


def parallel_for_model(path: Path, model: str) -> int:
    """Pick the configured parallelism for a model name: a name containing
    'pro' uses the pro tier, everything else (incl. unknown) the flash tier."""
    tier = "pro" if "pro" in (model or "").lower() else "flash"
    return get_parallel(path)[tier]
