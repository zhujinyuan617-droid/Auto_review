from __future__ import annotations

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
