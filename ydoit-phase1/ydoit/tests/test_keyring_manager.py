"""Tests for ydoit.keyring_manager."""

from __future__ import annotations

import sys
import time
import unittest.mock as mock

import pytest

from ydoit import constants

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_secret() -> mock.MagicMock:
    """Build a fully-configured MagicMock that stands in for gi.repository.Secret."""
    secret_mod = mock.MagicMock()
    secret_mod.Schema.new.return_value = mock.MagicMock(name="schema")
    secret_mod.SchemaFlags.NONE = 0
    secret_mod.SchemaAttributeType.STRING = 0
    secret_mod.COLLECTION_DEFAULT = "default"
    secret_mod.ServiceFlags.NONE = 0
    secret_mod.ServiceFlags.LOAD_COLLECTIONS = 1
    secret_mod.SearchFlags.ALL = 0
    mock_service = mock.MagicMock(name="service")
    secret_mod.Service.get_sync.return_value = mock_service
    return secret_mod


def _install_secret_mock(monkeypatch: pytest.MonkeyPatch, secret_mod: mock.MagicMock) -> None:
    """Patch sys.modules so that `import gi` and `from gi.repository import Secret` work."""
    gi_mod = mock.MagicMock(name="gi")
    gi_mod.repository.Secret = secret_mod
    monkeypatch.setitem(sys.modules, "gi", gi_mod)
    monkeypatch.setitem(sys.modules, "gi.repository", gi_mod.repository)
    monkeypatch.setitem(sys.modules, "gi.repository.Secret", secret_mod)


def _remove_gi_from_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure gi is absent from sys.modules so that import fails."""
    monkeypatch.delitem(sys.modules, "gi", raising=False)
    monkeypatch.delitem(sys.modules, "gi.repository", raising=False)
    monkeypatch.delitem(sys.modules, "gi.repository.Secret", raising=False)


def _fresh_km(monkeypatch: pytest.MonkeyPatch) -> KeyringManager:  # noqa: F821
    """Remove any cached module import and return a fresh KeyringManager instance."""
    # Remove cached module so __init__ re-runs _create_schema from scratch
    monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
    from ydoit.keyring_manager import KeyringManager
    return KeyringManager()


# ---------------------------------------------------------------------------
# Tests: gi unavailable (ImportError path)
# ---------------------------------------------------------------------------

class TestKeyringUnavailable:
    """All methods must degrade gracefully when gi / libsecret is missing."""

    def test_create_schema_returns_none_when_gi_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _remove_gi_from_modules(monkeypatch)
        monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
        from ydoit.keyring_manager import KeyringManager
        result = KeyringManager._create_schema()
        assert result is None

    def test_is_available_returns_false_when_gi_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _remove_gi_from_modules(monkeypatch)
        monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
        from ydoit.keyring_manager import KeyringManager
        assert KeyringManager.is_available() is False

    def test_store_passphrase_returns_false_when_schema_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _remove_gi_from_modules(monkeypatch)
        km = _fresh_km(monkeypatch)
        assert km._schema is None
        assert km.store_passphrase("secret") is False

    def test_retrieve_passphrase_returns_none_when_schema_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _remove_gi_from_modules(monkeypatch)
        km = _fresh_km(monkeypatch)
        assert km._schema is None
        assert km.retrieve_passphrase() is None

    def test_clear_passphrase_returns_false_when_schema_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _remove_gi_from_modules(monkeypatch)
        km = _fresh_km(monkeypatch)
        assert km._schema is None
        assert km.clear_passphrase() is False

    def test_is_expired_returns_true_when_schema_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _remove_gi_from_modules(monkeypatch)
        km = _fresh_km(monkeypatch)
        assert km._schema is None
        # _is_expired checks self._schema first
        assert km._is_expired(15) is True


# ---------------------------------------------------------------------------
# Fixture: mocked Secret available
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_secret(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    """Provide a fully-mocked gi.repository.Secret and install it into sys.modules."""
    secret_mod = _make_mock_secret()
    _install_secret_mock(monkeypatch, secret_mod)
    return secret_mod


@pytest.fixture
def km(monkeypatch: pytest.MonkeyPatch, mock_secret: mock.MagicMock) -> KeyringManager:  # noqa: F821
    """Return a KeyringManager instantiated after the gi mock is installed."""
    return _fresh_km(monkeypatch)


# ---------------------------------------------------------------------------
# Tests: is_available()
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_returns_true_when_service_get_sync_succeeds(
        self, mock_secret: mock.MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
        from ydoit.keyring_manager import KeyringManager
        assert KeyringManager.is_available() is True

    def test_returns_false_when_service_get_sync_raises(
        self, mock_secret: mock.MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_secret.Service.get_sync.side_effect = Exception("no service")
        monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
        from ydoit.keyring_manager import KeyringManager
        assert KeyringManager.is_available() is False

    def test_returns_false_when_service_is_none(
        self, mock_secret: mock.MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_secret.Service.get_sync.return_value = None
        monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
        from ydoit.keyring_manager import KeyringManager
        assert KeyringManager.is_available() is False


# ---------------------------------------------------------------------------
# Tests: store_passphrase()
# ---------------------------------------------------------------------------

class TestStorePassphrase:
    def test_calls_password_store_sync_with_correct_args(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_store_sync.return_value = True
        result = km.store_passphrase("my-passphrase")
        assert result is True
        mock_secret.password_store_sync.assert_called_once()
        call_args = mock_secret.password_store_sync.call_args
        # First positional arg is the schema
        assert call_args.args[0] is km._schema
        # Second arg is the attributes dict
        attrs = call_args.args[1]
        assert attrs[constants.KEYRING_ATTRIBUTE] == constants.KEYRING_ATTRIBUTE_VALUE
        assert constants.KEYRING_TIMESTAMP_ATTRIBUTE in attrs
        # Third arg is the collection
        assert call_args.args[2] == mock_secret.COLLECTION_DEFAULT
        # Fourth arg is the label
        assert call_args.args[3] == "ydoit GPG passphrase"
        # Fifth arg is the passphrase itself
        assert call_args.args[4] == "my-passphrase"

    def test_returns_false_when_store_raises(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_store_sync.side_effect = Exception("keyring error")
        assert km.store_passphrase("my-passphrase") is False

    def test_returns_false_result_from_store_sync(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_store_sync.return_value = False
        assert km.store_passphrase("my-passphrase") is False

    def test_timestamp_attribute_is_integer_string(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_store_sync.return_value = True
        before = int(time.time())
        km.store_passphrase("pw")
        after = int(time.time())
        call_args = mock_secret.password_store_sync.call_args
        attrs = call_args.args[1]
        ts = int(attrs[constants.KEYRING_TIMESTAMP_ATTRIBUTE])
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# Tests: retrieve_passphrase()
# ---------------------------------------------------------------------------

class TestRetrievePassphrase:
    def test_returns_none_when_lookup_returns_none(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_lookup_sync.return_value = None
        assert km.retrieve_passphrase() is None

    def test_returns_passphrase_when_not_expired(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_lookup_sync.return_value = "cached-pass"
        # Set up a fresh timestamp so it won't be expired
        fresh_ts = str(int(time.time()))
        mock_item = mock.MagicMock()
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
            constants.KEYRING_TIMESTAMP_ATTRIBUTE: fresh_ts,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        result = km.retrieve_passphrase(timeout_min=15)
        assert result == "cached-pass"

    def test_returns_passphrase_when_timeout_is_zero(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        """timeout_min=0 means never expire — _is_expired should not be called."""
        mock_secret.password_lookup_sync.return_value = "never-expire-pass"
        result = km.retrieve_passphrase(timeout_min=0)
        assert result == "never-expire-pass"
        # password_search_sync should NOT be called because timeout_min=0 skips expiry check
        mock_secret.password_search_sync.assert_not_called()

    def test_returns_none_and_clears_when_expired(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_lookup_sync.return_value = "old-pass"
        # Set up an old timestamp (1 hour ago)
        old_ts = str(int(time.time()) - 3600)
        mock_item = mock.MagicMock()
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
            constants.KEYRING_TIMESTAMP_ATTRIBUTE: old_ts,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        mock_secret.password_clear_sync.return_value = True
        result = km.retrieve_passphrase(timeout_min=15)
        assert result is None
        # clear_passphrase should have been called
        mock_secret.password_clear_sync.assert_called_once()

    def test_returns_none_on_exception(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_lookup_sync.side_effect = Exception("lookup failed")
        assert km.retrieve_passphrase() is None

    def test_lookup_called_with_correct_attributes(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_lookup_sync.return_value = None
        km.retrieve_passphrase()
        mock_secret.password_lookup_sync.assert_called_once()
        call_args = mock_secret.password_lookup_sync.call_args
        assert call_args.args[0] is km._schema
        attrs = call_args.args[1]
        assert attrs == {constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE}


# ---------------------------------------------------------------------------
# Tests: _is_expired()
# ---------------------------------------------------------------------------

class TestIsExpired:
    def test_returns_false_for_fresh_timestamp(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        fresh_ts = str(int(time.time()))
        mock_item = mock.MagicMock()
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
            constants.KEYRING_TIMESTAMP_ATTRIBUTE: fresh_ts,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        assert km._is_expired(15) is False

    def test_returns_true_for_old_timestamp(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        old_ts = str(int(time.time()) - 3600)  # 1 hour ago
        mock_item = mock.MagicMock()
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
            constants.KEYRING_TIMESTAMP_ATTRIBUTE: old_ts,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        assert km._is_expired(15) is True

    def test_returns_true_when_no_items_found(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_search_sync.return_value = []
        assert km._is_expired(15) is True

    def test_returns_true_when_stored_at_attribute_missing(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_item = mock.MagicMock()
        # Return attrs dict that does NOT contain the timestamp key
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        assert km._is_expired(15) is True

    def test_returns_true_on_exception(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_search_sync.side_effect = Exception("search failed")
        assert km._is_expired(15) is True

    def test_returns_false_just_before_timeout_boundary(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        """Timestamp just inside the timeout window should not be expired."""
        # 14 minutes ago with a 15-minute timeout — should NOT be expired
        ts = str(int(time.time()) - (14 * 60))
        mock_item = mock.MagicMock()
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
            constants.KEYRING_TIMESTAMP_ATTRIBUTE: ts,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        assert km._is_expired(15) is False

    def test_returns_true_just_past_timeout_boundary(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        """Timestamp just past the timeout window should be expired."""
        # 16 minutes ago with a 15-minute timeout — should be expired
        ts = str(int(time.time()) - (16 * 60))
        mock_item = mock.MagicMock()
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
            constants.KEYRING_TIMESTAMP_ATTRIBUTE: ts,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        assert km._is_expired(15) is True

    def test_calls_service_get_sync_with_load_collections(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        """_is_expired should call Service.get_sync with LOAD_COLLECTIONS flag."""
        fresh_ts = str(int(time.time()))
        mock_item = mock.MagicMock()
        mock_item.get_attributes.return_value = {
            constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
            constants.KEYRING_TIMESTAMP_ATTRIBUTE: fresh_ts,
        }
        mock_secret.password_search_sync.return_value = [mock_item]
        # Reset call history from __init__
        mock_secret.Service.get_sync.reset_mock()
        km._is_expired(15)
        mock_secret.Service.get_sync.assert_called_once_with(
            mock_secret.ServiceFlags.LOAD_COLLECTIONS, None
        )


# ---------------------------------------------------------------------------
# Tests: clear_passphrase()
# ---------------------------------------------------------------------------

class TestClearPassphrase:
    def test_calls_password_clear_sync_and_returns_true(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_clear_sync.return_value = True
        result = km.clear_passphrase()
        assert result is True
        mock_secret.password_clear_sync.assert_called_once()

    def test_calls_password_clear_sync_and_returns_false(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_clear_sync.return_value = False
        assert km.clear_passphrase() is False

    def test_returns_false_on_exception(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_clear_sync.side_effect = Exception("clear failed")
        assert km.clear_passphrase() is False

    def test_called_with_correct_schema_and_attributes(
        self, km: KeyringManager, mock_secret: mock.MagicMock  # noqa: F821
    ) -> None:
        mock_secret.password_clear_sync.return_value = True
        km.clear_passphrase()
        call_args = mock_secret.password_clear_sync.call_args
        assert call_args.args[0] is km._schema
        attrs = call_args.args[1]
        assert attrs == {constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE}
        assert call_args.args[2] is None


# ---------------------------------------------------------------------------
# Tests: schema creation (available path)
# ---------------------------------------------------------------------------

class TestCreateSchema:
    def test_schema_is_not_none_when_gi_available(
        self, km: KeyringManager  # noqa: F821
    ) -> None:
        assert km._schema is not None

    def test_schema_new_called_with_correct_name_and_attributes(
        self, mock_secret: mock.MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
        from ydoit.keyring_manager import KeyringManager
        KeyringManager()
        mock_secret.Schema.new.assert_called_once_with(
            constants.KEYRING_SCHEMA_NAME,
            mock_secret.SchemaFlags.NONE,
            {
                constants.KEYRING_ATTRIBUTE: mock_secret.SchemaAttributeType.STRING,
                constants.KEYRING_TIMESTAMP_ATTRIBUTE: mock_secret.SchemaAttributeType.STRING,
            },
        )

    def test_create_schema_returns_none_on_value_error(
        self, mock_secret: mock.MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_create_schema catches ValueError (e.g. from gi.require_version)."""
        gi_mod = sys.modules.get("gi")
        if gi_mod is not None:
            gi_mod.require_version.side_effect = ValueError("bad version")
        monkeypatch.delitem(sys.modules, "ydoit.keyring_manager", raising=False)
        from ydoit.keyring_manager import KeyringManager
        result = KeyringManager._create_schema()
        assert result is None
