"""Custom exceptions for ydoit."""


class YdoitError(Exception):
    """Base exception for all ydoit errors."""


class DecryptionError(YdoitError):
    """Failed to decrypt the config file (wrong passphrase or corrupt file)."""


class EncryptionError(YdoitError):
    """Failed to encrypt the config file."""


class EntryNotFoundError(YdoitError):
    """Requested entry does not exist in the config."""

    def __init__(self, trigger: str) -> None:
        self.trigger = trigger
        super().__init__(f"Entry not found: {trigger!r}")


class DuplicateEntryError(YdoitError):
    """An entry with this trigger already exists."""

    def __init__(self, trigger: str) -> None:
        self.trigger = trigger
        super().__init__(f"Entry already exists: {trigger!r}")


class ShortcutConflictError(YdoitError):
    """The requested key combo is already in use."""

    def __init__(
        self,
        keycombo: str,
        existing_name: str,
        existing_source: str,
    ) -> None:
        self.keycombo = keycombo
        self.existing_name = existing_name
        self.existing_source = existing_source
        super().__init__(
            f"Shortcut {keycombo!r} is already used by "
            f"{existing_source} shortcut {existing_name!r}"
        )


class YdotoolError(YdoitError):
    """Error communicating with ydotool/ydotoold."""


class InvalidEntryTriggerError(YdoitError):
    """Entry trigger contains invalid characters."""

    def __init__(self, trigger: str, reason: str = "") -> None:
        self.trigger = trigger
        msg = f"Invalid entry trigger: {trigger!r}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class ConfigDirError(YdoitError):
    """Cannot create or access the config directory."""


class GpgNotFoundError(YdoitError):
    """GnuPG is not installed or not found in PATH."""

    def __init__(self) -> None:
        super().__init__(
            "GnuPG (gpg) is not installed or not found in PATH. "
            "Install it with: sudo dnf install gnupg2  (Fedora) or "
            "sudo apt install gnupg  (Ubuntu)"
        )


class GioNotAvailableError(YdoitError):
    """Gio.Settings is not available (python3-gobject not installed)."""

    def __init__(self) -> None:
        super().__init__(
            "Gio.Settings not available — install python3-gobject (system package). "
            "Fedora: sudo dnf install python3-gobject  "
            "Ubuntu: sudo apt install python3-gi"
        )
