"""Keyring manager — GNOME Keyring / libsecret passphrase caching."""

from __future__ import annotations

import time

from ydoit import constants


class KeyringManager:
    """Manages GPG passphrase caching in GNOME Keyring via libsecret.

    Stores the passphrase with a timestamp so we can enforce
    configurable timeouts. A timeout of 0 means never expire.
    """

    def __init__(self) -> None:
        self._schema = self._create_schema()

    @staticmethod
    def _create_schema() -> object | None:
        """Create the libsecret schema. Returns None if libsecret unavailable."""
        try:
            import gi

            gi.require_version("Secret", "1")
            from gi.repository import Secret

            return Secret.Schema.new(
                constants.KEYRING_SCHEMA_NAME,
                Secret.SchemaFlags.NONE,
                {
                    constants.KEYRING_ATTRIBUTE: Secret.SchemaAttributeType.STRING,
                    constants.KEYRING_TIMESTAMP_ATTRIBUTE: Secret.SchemaAttributeType.STRING,
                },
            )
        except (ImportError, ValueError):
            return None

    @staticmethod
    def is_available() -> bool:
        """Check if GNOME Keyring / Secret Service is accessible."""
        try:
            import gi

            gi.require_version("Secret", "1")
            from gi.repository import Secret

            service = Secret.Service.get_sync(Secret.ServiceFlags.NONE, None)
            return service is not None
        except Exception:
            return False

    def store_passphrase(self, passphrase: str) -> bool:
        """Store passphrase in GNOME Keyring with a timestamp.

        Args:
            passphrase: The GPG passphrase to cache.

        Returns:
            True if stored successfully, False otherwise.
        """
        if self._schema is None:
            return False

        try:
            from gi.repository import Secret

            return Secret.password_store_sync(
                self._schema,
                {
                    constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE,
                    constants.KEYRING_TIMESTAMP_ATTRIBUTE: str(int(time.time())),
                },
                Secret.COLLECTION_DEFAULT,
                "ydoit GPG passphrase",
                passphrase,
                None,
            )
        except Exception:
            return False

    def retrieve_passphrase(self, timeout_min: int = 15) -> str | None:
        """Retrieve cached passphrase if it hasn't expired.

        Args:
            timeout_min: Timeout in minutes. 0 means never expire.

        Returns:
            The cached passphrase, or None if not found or expired.
        """
        if self._schema is None:
            return None

        try:
            from gi.repository import Secret

            # Lookup only by the application attribute
            passphrase = Secret.password_lookup_sync(
                self._schema,
                {constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE},
                None,
            )

            if passphrase is None:
                return None

            # Check expiry (if timeout > 0)
            if timeout_min > 0 and self.is_expired(timeout_min):
                self.clear_passphrase()
                return None

            return passphrase
        except Exception:
            return None

    def is_expired(self, timeout_min: int) -> bool:
        """Check if the stored passphrase has expired.

        We retrieve the item to check its stored_at attribute.
        """
        if self._schema is None:
            return True

        try:
            from gi.repository import Secret

            Secret.Service.get_sync(
                Secret.ServiceFlags.LOAD_COLLECTIONS, None
            )
            items = Secret.password_search_sync(
                self._schema,
                {constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE},
                Secret.SearchFlags.ALL,
                None,
            )

            if not items:
                return True

            # Get the timestamp from the first matching item
            item = items[0]
            attrs = item.get_attributes()
            stored_at_str = attrs.get(constants.KEYRING_TIMESTAMP_ATTRIBUTE)

            if stored_at_str is None:
                return True

            stored_at = int(stored_at_str)
            elapsed_min = (time.time() - stored_at) / 60.0
            return elapsed_min >= timeout_min
        except Exception:
            return True

    def clear_passphrase(self) -> bool:
        """Remove the cached passphrase from the keyring.

        Returns:
            True if cleared successfully, False otherwise.
        """
        if self._schema is None:
            return False

        try:
            from gi.repository import Secret

            return Secret.password_clear_sync(
                self._schema,
                {constants.KEYRING_ATTRIBUTE: constants.KEYRING_ATTRIBUTE_VALUE},
                None,
            )
        except Exception:
            return False
