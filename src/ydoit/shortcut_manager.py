"""Shortcut manager — GNOME custom keybinding registration and sync."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ydoit import constants
from ydoit.exceptions import GioNotAvailableError

if TYPE_CHECKING:
    from ydoit.models import Config, Entry


@dataclass
class GnomeShortcut:
    """Represents a single GNOME custom keybinding."""

    path: str
    name: str
    command: str
    binding: str

    @property
    def is_ydoit(self) -> bool:
        """Whether this shortcut is owned by ydoit."""
        return self.name.startswith(constants.YDOIT_SHORTCUT_PREFIX)

    @property
    def entry_trigger(self) -> str | None:
        """Extract the ydoit entry trigger from the command, if this is a ydoit shortcut."""
        if not self.is_ydoit:
            return None
        # command is "ydoit type <trigger>"
        parts = self.command.split()
        if len(parts) >= 3 and parts[0] == "ydoit" and parts[1] == "type":
            return parts[2]
        return None


@dataclass
class ConflictInfo:
    """Information about a keybinding conflict."""

    keycombo: str
    existing_name: str
    existing_source: str  # "ydoit", "custom", or "builtin"
    existing_path: str | None = None


@dataclass
class ConflictDetail:
    """A pre-flight conflict between one of our entries and an existing shortcut."""

    our_trigger: str
    our_category: str
    our_label: str
    our_keycombo: str
    conflict: ConflictInfo

    def existing_source_label(self) -> str:
        """Human-readable description of where the conflicting shortcut lives."""
        src = self.conflict.existing_source
        if src == "ydoit":
            return "another ydoit entry"
        if src == "custom":
            return "GNOME custom shortcut"
        if src == "builtin":
            return "GNOME built-in shortcut"
        return src


@dataclass
class SyncResult:
    """Result of a shortcut sync operation."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)
    conflicts: list[ConflictDetail] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return self.added + self.updated + self.removed

    @property
    def success(self) -> bool:
        """True if sync produced no conflicts and no errors."""
        return not self.errors and not self.conflicts

    def __str__(self) -> str:
        parts = []
        if self.added:
            parts.append(f"{self.added} added")
        if self.updated:
            parts.append(f"{self.updated} updated")
        if self.removed:
            parts.append(f"{self.removed} removed")
        if self.conflicts:
            parts.append(f"{len(self.conflicts)} conflicts")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts) if parts else "no changes"


class ShortcutManager:
    """Manages GNOME custom keybindings for ydoit entries.

    Reads and writes keybindings via Gio.Settings (dconf backend).
    Handles conflict detection, sync, and format translation.
    """

    def __init__(self) -> None:
        self._gio_available: bool | None = None

    def _check_gio(self) -> bool:
        """Check if Gio.Settings is available."""
        if self._gio_available is None:
            try:
                import gi

                gi.require_version("Gio", "2.0")
                from gi.repository import Gio  # noqa: F401

                self._gio_available = True
            except (ImportError, ValueError):
                self._gio_available = False
        return self._gio_available

    def _require_gio(self) -> None:
        """Raise GioNotAvailableError if Gio.Settings is not available."""
        if not self._check_gio():
            raise GioNotAvailableError()

    def _get_media_keys_settings(self) -> Any:
        """Get the Gio.Settings for media-keys."""
        from gi.repository import Gio

        return Gio.Settings.new(constants.MEDIA_KEYS_SCHEMA)

    def _get_keybinding_settings(self, path: str) -> Any:
        """Get the Gio.Settings for a specific custom keybinding path."""
        from gi.repository import Gio

        return Gio.Settings.new_with_path(constants.CUSTOM_KEYBINDING_SCHEMA, path)

    # --- Read operations ---

    def get_all_custom_shortcuts(self) -> list[GnomeShortcut]:
        """Read all GNOME custom keybindings.

        Returns:
            List of all custom shortcuts registered in GNOME.
        """
        if not self._check_gio():
            return []

        settings = self._get_media_keys_settings()
        paths = settings.get_strv(constants.CUSTOM_KEYBINDING_KEY)

        shortcuts = []
        for path in paths:
            try:
                kb_settings = self._get_keybinding_settings(path)
                shortcuts.append(
                    GnomeShortcut(
                        path=path,
                        name=kb_settings.get_string("name"),
                        command=kb_settings.get_string("command"),
                        binding=kb_settings.get_string("binding"),
                    )
                )
            except Exception:
                continue  # Skip malformed entries

        return shortcuts

    def get_ydoit_shortcuts(self) -> list[GnomeShortcut]:
        """Get only ydoit-owned custom shortcuts."""
        return [s for s in self.get_all_custom_shortcuts() if s.is_ydoit]

    def get_non_ydoit_shortcuts(self) -> list[GnomeShortcut]:
        """Get all custom shortcuts NOT owned by ydoit."""
        return [s for s in self.get_all_custom_shortcuts() if not s.is_ydoit]

    # --- Conflict detection ---

    def find_conflict(
        self, keycombo: str, exclude_entry: str | None = None
    ) -> ConflictInfo | None:
        """Check if a key combo conflicts with any existing shortcut.

        Args:
            keycombo: User-facing key combo (e.g. "Super+F11").
            exclude_entry: Entry name to exclude from conflict check (for updates).

        Returns:
            ConflictInfo if a conflict exists, None otherwise.
        """
        self._require_gio()
        gnome_binding = self.to_gnome_binding(keycombo)

        # Check all custom shortcuts
        for shortcut in self.get_all_custom_shortcuts():
            if shortcut.binding.lower() == gnome_binding.lower():
                # Skip if it's the entry being updated
                if (
                    exclude_entry
                    and shortcut.is_ydoit
                    and shortcut.entry_trigger == exclude_entry
                ):
                    continue

                source = "ydoit" if shortcut.is_ydoit else "custom"
                name = shortcut.entry_trigger or shortcut.name
                return ConflictInfo(
                    keycombo=keycombo,
                    existing_name=name,
                    existing_source=source,
                    existing_path=shortcut.path,
                )

        # Check built-in shortcuts
        builtin_conflict = self._check_builtin_conflict(gnome_binding)
        if builtin_conflict:
            return builtin_conflict

        return None

    def _check_builtin_conflict(self, gnome_binding: str) -> ConflictInfo | None:
        """Check against built-in GNOME shortcuts.

        This checks common built-in shortcut schemas for conflicts.
        """
        if not self._check_gio():
            return None

        from gi.repository import Gio

        # Schemas that contain built-in shortcuts
        schemas_to_check = [
            "org.gnome.desktop.wm.keybindings",
            "org.gnome.shell.keybindings",
            "org.gnome.mutter.keybindings",
            "org.gnome.mutter.wayland.keybindings",
            "org.gnome.settings-daemon.plugins.media-keys",
        ]

        schema_source = Gio.SettingsSchemaSource.get_default()
        if schema_source is None:
            return None

        for schema_id in schemas_to_check:
            schema = schema_source.lookup(schema_id, True)
            if schema is None:
                continue

            settings = Gio.Settings.new(schema_id)
            for key_name in schema.list_keys():
                try:
                    value = settings.get_value(key_name)
                    if value.get_type_string() != "as":
                        continue
                    bindings = value.get_strv()
                    for binding in bindings:
                        if binding.lower() == gnome_binding.lower():
                            return ConflictInfo(
                                keycombo=self.from_gnome_binding(gnome_binding),
                                existing_name=key_name.replace("-", " ").title(),
                                existing_source="builtin",
                                existing_path=None,
                            )
                except Exception:
                    continue

        return None

    # --- Write operations ---

    def sync(self, config: Config) -> SyncResult:
        """Sync GNOME shortcuts to match config entries.

        Adds missing shortcuts, updates changed ones, removes stale ones.

        Args:
            config: Current config with entries.

        Returns:
            SyncResult with counts of changes made.
        """
        self._require_gio()

        result = SyncResult()
        current = {s.entry_trigger: s for s in self.get_ydoit_shortcuts() if s.entry_trigger}
        desired = config.entries

        # Pre-flight: check all keyed entries for conflicts before any mutations
        for entry_trigger, entry in desired.items():
            if not entry.keycombo:
                continue
            conflict = self.find_conflict(entry.keycombo, exclude_entry=entry_trigger)
            if conflict:
                result.conflicts.append(
                    ConflictDetail(
                        our_trigger=entry_trigger,
                        our_category=entry.category,
                        our_label=entry.display_label,
                        our_keycombo=entry.keycombo,
                        conflict=conflict,
                    )
                )
        if result.conflicts:
            return result

        # Remove stale shortcuts
        for entry_trigger in set(current) - set(desired):
            try:
                self._remove_shortcut_path(current[entry_trigger].path)
                result.removed += 1
            except Exception as e:
                result.errors.append(f"Failed to remove {entry_trigger}: {e}")

        # Add new shortcuts
        for entry_trigger in set(desired) - set(current):
            entry = desired[entry_trigger]
            if not entry.keycombo:
                continue
            try:
                self._register_new_shortcut(entry)
                result.added += 1
            except Exception as e:
                result.errors.append(f"Failed to add {entry_trigger}: {e}")

        # Update changed shortcuts
        for entry_trigger in set(desired) & set(current):
            entry = desired[entry_trigger]
            existing = current[entry_trigger]
            expected_binding = self.to_gnome_binding(entry.keycombo) if entry.keycombo else ""
            expected_command = self.make_command(entry.trigger)
            expected_name = f"{constants.YDOIT_SHORTCUT_PREFIX}{entry.display_label}"

            if (
                existing.binding != expected_binding
                or existing.command != expected_command
                or existing.name != expected_name
            ):
                try:
                    kb_settings = self._get_keybinding_settings(existing.path)
                    kb_settings.set_string("name", expected_name)
                    kb_settings.set_string("command", expected_command)
                    kb_settings.set_string("binding", expected_binding)
                    result.updated += 1
                except Exception as e:
                    result.errors.append(f"Failed to update {entry_trigger}: {e}")

        return result

    def register_shortcut(self, entry: Entry) -> None:
        """Add or update a single GNOME shortcut for an entry.

        Args:
            entry: The entry to register a shortcut for.
        """
        self._require_gio()

        if not entry.keycombo:
            return

        # Check if already registered
        for shortcut in self.get_ydoit_shortcuts():
            if shortcut.entry_trigger == entry.trigger:
                # Update existing
                kb_settings = self._get_keybinding_settings(shortcut.path)
                kb_settings.set_string(
                    "name", f"{constants.YDOIT_SHORTCUT_PREFIX}{entry.display_label}"
                )
                kb_settings.set_string("command", self.make_command(entry.trigger))
                kb_settings.set_string("binding", self.to_gnome_binding(entry.keycombo))
                return

        # Register new
        self._register_new_shortcut(entry)

    def unregister_shortcut(self, entry_trigger: str) -> None:
        """Remove the GNOME shortcut for a named entry.

        Args:
            entry_trigger: The entry trigger whose shortcut to remove.
        """
        self._require_gio()

        for shortcut in self.get_ydoit_shortcuts():
            if shortcut.entry_trigger == entry_trigger:
                self._remove_shortcut_path(shortcut.path)
                return

    def clear_all_ydoit_shortcuts(self) -> int:
        """Remove all ydoit-owned shortcuts.

        Returns:
            Number of shortcuts removed.
        """
        self._require_gio()

        count = 0
        for shortcut in self.get_ydoit_shortcuts():
            self._remove_shortcut_path(shortcut.path)
            count += 1
        return count

    def _register_new_shortcut(self, entry: Entry) -> None:
        """Create a new custom keybinding slot and register the shortcut."""
        settings = self._get_media_keys_settings()
        paths = list(settings.get_strv(constants.CUSTOM_KEYBINDING_KEY))

        # Find the next free slot
        used_indices = set()
        for p in paths:
            match = re.search(r"custom(\d+)", p)
            if match:
                used_indices.add(int(match.group(1)))

        idx = 0
        while idx in used_indices:
            idx += 1

        new_path = f"{constants.CUSTOM_KEYBINDING_BASE}/custom{idx}/"

        # Write the keybinding
        kb_settings = self._get_keybinding_settings(new_path)
        kb_settings.set_string(
            "name", f"{constants.YDOIT_SHORTCUT_PREFIX}{entry.display_label}"
        )
        kb_settings.set_string("command", self.make_command(entry.trigger))
        kb_settings.set_string("binding", self.to_gnome_binding(entry.keycombo))

        # Add to the master list
        paths.append(new_path)
        settings.set_strv(constants.CUSTOM_KEYBINDING_KEY, paths)

        from gi.repository import Gio
        Gio.Settings.sync()

    def _remove_shortcut_path(self, path: str) -> None:
        """Remove a custom keybinding by its dconf path."""
        settings = self._get_media_keys_settings()
        paths = list(settings.get_strv(constants.CUSTOM_KEYBINDING_KEY))

        # Clear the keybinding values
        kb_settings = self._get_keybinding_settings(path)
        kb_settings.reset("name")
        kb_settings.reset("command")
        kb_settings.reset("binding")

        # Remove from master list
        if path in paths:
            paths.remove(path)
            settings.set_strv(constants.CUSTOM_KEYBINDING_KEY, paths)

            from gi.repository import Gio
            Gio.Settings.sync()

    # --- Format conversion ---

    @staticmethod
    def to_gnome_binding(keycombo: str) -> str:
        """Convert user-facing key combo to GNOME dconf format.

        Examples:
            "Super+F11"      → "<Super>F11"
            "Ctrl+Alt+P"     → "<Primary><Alt>p"
            "Shift+Super+S"  → "<Shift><Super>s"

        Args:
            keycombo: User-facing key combo string.

        Returns:
            GNOME-format binding string.
        """
        if not keycombo:
            return ""

        parts = [p.strip() for p in keycombo.split("+")]
        if not parts:
            return ""

        # The last part is the actual key, everything before is a modifier
        key = parts[-1]
        modifiers = parts[:-1]

        # Convert modifiers
        gnome_mods = []
        for mod in modifiers:
            gnome_mod = constants.MODIFIER_TO_GNOME.get(mod)
            if gnome_mod:
                gnome_mods.append(gnome_mod)
            else:
                gnome_mods.append(f"<{mod}>")

        # Lowercase single alpha keys (F-keys stay uppercase)
        if len(key) == 1 and key.isalpha():
            key = key.lower()

        return "".join(gnome_mods) + key

    @staticmethod
    def from_gnome_binding(binding: str) -> str:
        """Convert GNOME dconf binding to user-facing format.

        Examples:
            "<Super>F11"          → "Super+F11"
            "<Primary><Alt>p"     → "Ctrl+Alt+P"
            "<Shift><Super>s"     → "Shift+Super+S"

        Args:
            binding: GNOME-format binding string.

        Returns:
            User-facing key combo string.
        """
        if not binding:
            return ""

        parts = []
        remaining = binding

        # Extract modifiers
        while remaining.startswith("<"):
            end = remaining.index(">")
            mod_raw = remaining[: end + 1]
            mod = constants.GNOME_TO_MODIFIER.get(mod_raw, mod_raw.strip("<>"))
            parts.append(mod)
            remaining = remaining[end + 1 :]

        # Remaining is the key — uppercase single alpha keys for display
        if remaining:
            if len(remaining) == 1 and remaining.isalpha():
                remaining = remaining.upper()
            parts.append(remaining)

        return "+".join(parts)

    @staticmethod
    def make_command(entry_trigger: str) -> str:
        """Build the shell command for a shortcut.

        Args:
            entry_trigger: Entry trigger.

        Returns:
            Command string like "ydoit type home1".
        """
        return f"ydoit type {entry_trigger}"
