"""Application state controller for the GUI.

AppState wraps Phase 1 managers (ConfigManager, ShortcutManager, KeyringManager)
and provides CRUD operations with auto-save and GObject signal emission.
All GUI widgets talk to AppState, never directly to Phase 1 modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from ydoit.config_manager import ConfigManager
from ydoit.exceptions import (
    DecryptionError,
    ShortcutConflictError,
    YdoitError,
)
from ydoit.models import Config, Entry, Settings
from ydoit.shortcut_manager import ConflictInfo, ShortcutManager

try:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import GObject

    _GObjectBase = GObject.Object
    _HAS_GOBJECT = True
except (ImportError, ValueError):
    _GObjectBase = object
    _HAS_GOBJECT = False


# Sentinel for distinguishing "not provided" from None in update_entry
class _SentinelType:
    _instance = None

    def __new__(cls) -> _SentinelType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<SENTINEL>"

    def __bool__(self) -> bool:
        return False


_SENTINEL = _SentinelType()


class AppState(_GObjectBase):
    """Central state controller for the ydoit GUI.

    Signals (when GObject is available):
        entries-changed: Emitted when any entry is added, removed, or updated.
        settings-changed: Emitted when global settings change.
        unlocked: Emitted when the config is successfully decrypted.
        locked: Emitted when the state is locked (config cleared).
    """

    if _HAS_GOBJECT:
        __gsignals__ = {
            "entries-changed": (GObject.SignalFlags.RUN_LAST, None, ()),
            "settings-changed": (GObject.SignalFlags.RUN_LAST, None, ()),
            "unlocked": (GObject.SignalFlags.RUN_LAST, None, ()),
            "locked": (GObject.SignalFlags.RUN_LAST, None, ()),
        }

    def __init__(
        self,
        config_manager: ConfigManager | None = None,
        shortcut_manager: ShortcutManager | None = None,
    ) -> None:
        super().__init__()
        self._config_manager = config_manager or ConfigManager()
        self._shortcut_manager = shortcut_manager or ShortcutManager()
        self._config: Config | None = None
        self._passphrase: str | None = None
        self._signal_handlers: dict[str, list] = {}

    def emit(self, signal_name: str) -> None:
        """Emit a signal. Uses GObject if available, otherwise calls registered handlers."""
        if _HAS_GOBJECT:
            super().emit(signal_name)
        else:
            for handler in self._signal_handlers.get(signal_name, []):
                handler(self)

    def connect(self, signal_name: str, handler: object) -> int:
        """Connect a signal handler. Uses GObject if available, otherwise stores locally."""
        if _HAS_GOBJECT:
            return super().connect(signal_name, handler)
        self._signal_handlers.setdefault(signal_name, []).append(handler)
        return len(self._signal_handlers[signal_name]) - 1

    # --- Properties ---

    @property
    def is_unlocked(self) -> bool:
        """Whether the config has been decrypted and is available."""
        return self._config is not None

    @property
    def config(self) -> Config:
        """The current decrypted config. Raises if locked."""
        if self._config is None:
            raise YdoitError("Config is locked")
        return self._config

    @property
    def entries(self) -> dict[str, Entry]:
        """All entries. Raises if locked."""
        return self.config.entries

    @property
    def settings(self) -> Settings:
        """Global settings. Raises if locked."""
        return self.config.settings

    @property
    def config_exists(self) -> bool:
        """Whether the encrypted config file exists on disk."""
        return self._config_manager.exists()

    # --- Unlock / Lock ---

    def unlock(self, passphrase: str) -> None:
        """Decrypt the config file and enter unlocked state.

        Caches the passphrase in the keyring (if enabled) so that
        shortcut commands (ydoit type) can decrypt without a terminal.

        Args:
            passphrase: GPG passphrase.

        Raises:
            DecryptionError: Wrong passphrase or corrupt file.
        """
        self._config = self._config_manager.load(passphrase)
        self._passphrase = passphrase

        # Cache in keyring so CLI shortcuts work without a terminal
        try:
            from ydoit.keyring_manager import KeyringManager

            km = KeyringManager()
            if km.is_available():
                km.store_passphrase(passphrase)
        except Exception:
            pass

        self.emit("unlocked")
        self.emit("entries-changed")

    def try_keyring_unlock(self) -> bool:
        """Attempt to unlock using a cached keyring passphrase.

        Returns:
            True if successfully unlocked, False if no cached passphrase
            or decryption failed.
        """
        if not self.config_exists:
            return False

        try:
            from ydoit.keyring_manager import KeyringManager

            km = KeyringManager()
            if not km.is_available():
                return False
            cached = km.retrieve_passphrase()
            if cached is None:
                return False
            self.unlock(cached)
            return True
        except Exception:
            return False

    def lock(self) -> None:
        """Clear the decrypted config and passphrase."""
        self._config = None
        self._passphrase = None
        self.emit("locked")

    # --- CRUD: Entries ---

    def add_entry(self, entry: Entry, force_shortcut: bool = False) -> None:
        """Add a new entry, save, and sync its shortcut.

        Args:
            entry: The entry to add.
            force_shortcut: If True, reassign conflicting shortcuts.

        Raises:
            DuplicateEntryError: If an entry with this name already exists.
            ShortcutConflictError: If the keycombo conflicts and force is False.
            InvalidEntryNameError: If the entry name is invalid.
        """
        config = self.config

        # Check shortcut conflict
        if entry.keycombo and not force_shortcut:
            conflict = self.find_shortcut_conflict(entry.keycombo)
            if conflict:
                raise ShortcutConflictError(
                    conflict.keycombo,
                    conflict.existing_name,
                    conflict.existing_source,
                )

        config.add_entry(entry)
        self._save()

        if entry.keycombo:
            self._shortcut_manager.register_shortcut(entry)

        self.emit("entries-changed")

    def update_entry(
        self,
        name: str,
        *,
        keycombo: str | None = None,
        string: str | None = None,
        filename: str | None = None,
        label: str | None = None,
        category: str | None = None,
        notes: str | None = None,
        typing_delay_ms: int | None = _SENTINEL,
        hold_delay_ms: int | None = _SENTINEL,
        force_shortcut: bool = False,
    ) -> Entry:
        """Update an existing entry's fields, save, and sync shortcut.

        Only non-None arguments are applied. Pass explicit None for
        typing_delay_ms/hold_delay_ms to clear per-entry overrides
        (use _SENTINEL default to distinguish "not provided" from None).

        Args:
            name: Entry name to update.

        Returns:
            The updated Entry.

        Raises:
            EntryNotFoundError: If entry doesn't exist.
            ShortcutConflictError: If new keycombo conflicts and force is False.
        """
        entry = self.config.get_entry(name)

        # Check shortcut conflict if keycombo is changing
        if keycombo is not None and keycombo != entry.keycombo and not force_shortcut:
            conflict = self.find_shortcut_conflict(keycombo, exclude_entry=name)
            if conflict:
                raise ShortcutConflictError(
                    conflict.keycombo,
                    conflict.existing_name,
                    conflict.existing_source,
                )

        if keycombo is not None:
            entry.keycombo = keycombo
        if string is not None:
            entry.string = string
        if filename is not None:
            entry.filename = filename
        if label is not None:
            entry.label = label
        if category is not None:
            entry.category = category
        if notes is not None:
            entry.notes = notes
        if typing_delay_ms is not _SENTINEL:
            entry.typing_delay_ms = typing_delay_ms
        if hold_delay_ms is not _SENTINEL:
            entry.hold_delay_ms = hold_delay_ms

        self._save()
        self._shortcut_manager.register_shortcut(entry)
        self.emit("entries-changed")
        return entry

    def remove_entry(self, name: str) -> Entry:
        """Remove an entry, save, and unregister its shortcut.

        Args:
            name: Entry name to remove.

        Returns:
            The removed Entry.

        Raises:
            EntryNotFoundError: If entry doesn't exist.
        """
        entry = self.config.remove_entry(name)
        self._save()
        self._shortcut_manager.unregister_shortcut(name)
        self.emit("entries-changed")
        return entry

    def get_entry(self, name: str) -> Entry:
        """Get an entry by name.

        Raises:
            EntryNotFoundError: If entry doesn't exist.
        """
        return self.config.get_entry(name)

    def get_entries_by_category(self) -> dict[str, list[Entry]]:
        """Return entries grouped by category, sorted."""
        categories: dict[str, list[Entry]] = {}
        for entry in self.config.entries.values():
            cat = entry.category or "general"
            categories.setdefault(cat, []).append(entry)

        for cat in categories:
            categories[cat].sort(key=lambda e: e.name)

        return dict(sorted(categories.items()))

    # --- CRUD: Settings ---

    def update_settings(
        self,
        *,
        typing_delay_ms: int | None = None,
        hold_delay_ms: int | None = None,
        use_keyring_cache: bool | None = None,
        keyring_timeout_min: int | None = None,
    ) -> Settings:
        """Update global settings and save.

        Only non-None arguments are applied.

        Returns:
            The updated Settings.
        """
        settings = self.config.settings
        if typing_delay_ms is not None:
            settings.typing_delay_ms = typing_delay_ms
        if hold_delay_ms is not None:
            settings.hold_delay_ms = hold_delay_ms
        if use_keyring_cache is not None:
            settings.use_keyring_cache = use_keyring_cache
        if keyring_timeout_min is not None:
            settings.keyring_timeout_min = keyring_timeout_min

        self._save()
        self.emit("settings-changed")
        return settings

    # --- Shortcuts ---

    def find_shortcut_conflict(
        self, keycombo: str, exclude_entry: str | None = None
    ) -> ConflictInfo | None:
        """Check if a key combo conflicts with any existing shortcut."""
        return self._shortcut_manager.find_conflict(keycombo, exclude_entry)

    def sync_shortcuts(self) -> None:
        """Sync all GNOME shortcuts to match the current config."""
        self._shortcut_manager.sync(self.config)

    # --- Passphrase ---

    def change_passphrase(self, old_passphrase: str, new_passphrase: str) -> None:
        """Change the GPG passphrase.

        Re-encrypts the config with the new passphrase and updates keyring cache.

        Raises:
            DecryptionError: If old_passphrase is wrong.
        """
        # Verify old passphrase by attempting to load
        self._config_manager.load(old_passphrase)

        # Re-save with new passphrase
        self._passphrase = new_passphrase
        self._save()

        # Update keyring
        try:
            from ydoit.keyring_manager import KeyringManager

            km = KeyringManager()
            if km.is_available():
                km.store_passphrase(new_passphrase)
        except Exception:
            pass

    # --- Import / Export ---

    def export_plain(self, path: Path) -> int:
        """Export config as unencrypted JSON.

        Returns:
            Number of entries exported.
        """
        config = self.config
        path.write_text(config.to_json(), encoding="utf-8")
        return len(config.entries)

    def import_config(self, path: Path, passphrase: str | None = None) -> int:
        """Import and merge entries from a file.

        Returns:
            Number of entries imported.

        Raises:
            DecryptionError: If encrypted and passphrase is wrong.
        """
        import json

        try:
            raw = path.read_text(encoding="utf-8")
            import_config = Config.from_json(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            if passphrase is None:
                raise DecryptionError(
                    "Encrypted file requires a passphrase"
                ) from None
            import_cm = ConfigManager(config_dir=path.parent)
            import_cm.data_file = path
            import_config = import_cm.load(passphrase)

        config = self.config
        count = len(import_config.entries)
        for name, entry in import_config.entries.items():
            config.entries[name] = entry

        self._save()
        self._shortcut_manager.sync(config)
        self.emit("entries-changed")
        return count

    # --- Private ---

    def _save(self) -> None:
        """Save the current config to disk."""
        if self._config is None or self._passphrase is None:
            raise YdoitError("Cannot save: config is locked")
        self._config_manager.save(self._config, self._passphrase)
