import keyring
import pytest


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    # In-memory keyring so tests never touch the real OS credential store.
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: store.__setitem__((s, u), p))
    monkeypatch.setattr(keyring, "get_password", lambda s, u: store.get((s, u)))
    monkeypatch.setattr(keyring, "delete_password", lambda s, u: store.pop((s, u), None))
    return store


def test_set_and_has_and_clear():
    from autoreview_app import settings

    assert settings.has_api_key() is False
    settings.set_api_key("secret-key-123")
    assert settings.has_api_key() is True
    assert settings.get_api_key() == "secret-key-123"
    settings.clear_api_key()
    assert settings.has_api_key() is False
    assert settings.get_api_key() is None


def test_blank_key_is_rejected():
    from autoreview_app import settings

    with pytest.raises(ValueError):
        settings.set_api_key("   ")
