import keyring
import keyring.errors
import pytest


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    # In-memory keyring so tests never touch the real OS credential store. delete
    # mirrors real backends: raises PasswordDeleteError when the key is absent.
    store: dict[tuple[str, str], str] = {}

    def _delete(s, u):
        if (s, u) not in store:
            raise keyring.errors.PasswordDeleteError("not set")
        del store[(s, u)]

    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: store.__setitem__((s, u), p))
    monkeypatch.setattr(keyring, "get_password", lambda s, u: store.get((s, u)))
    monkeypatch.setattr(keyring, "delete_password", _delete)
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


def test_clear_when_empty_does_not_raise():
    from autoreview_app import settings

    # No key set: real backends raise PasswordDeleteError; clear must swallow it.
    settings.clear_api_key()
    assert settings.has_api_key() is False
