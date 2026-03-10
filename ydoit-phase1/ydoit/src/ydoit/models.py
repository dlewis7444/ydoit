"""Data model for ydoit configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ydoit import constants
from ydoit.exceptions import InvalidEntryTriggerError


class EntryType(Enum):
    """Whether an entry types a literal string or the contents of a file."""

    STRING = "string"
    FILE = "file"


@dataclass
class Entry:
    """A single auto-type entry."""

    trigger: str
    keycombo: str
    string: str = ""
    filename: str = ""
    label: str = ""
    category: str = constants.DEFAULT_CATEGORY
    notes: str = ""
    typing_delay_ms: int | None = None
    hold_delay_ms: int | None = None

    def __post_init__(self) -> None:
        self.validate_trigger(self.trigger)

    @property
    def entry_type(self) -> EntryType:
        """Determine whether this entry types a string or file contents."""
        return EntryType.FILE if self.filename else EntryType.STRING

    @property
    def display_label(self) -> str:
        """Return the label for display, falling back to trigger."""
        return self.label or self.trigger

    @staticmethod
    def validate_trigger(trigger: str) -> None:
        """Validate an entry trigger. Raises InvalidEntryTriggerError if invalid."""
        if not trigger:
            raise InvalidEntryTriggerError(trigger, "trigger cannot be empty")
        if len(trigger) > constants.MAX_ENTRY_TRIGGER_LENGTH:
            raise InvalidEntryTriggerError(
                trigger, f"trigger exceeds {constants.MAX_ENTRY_TRIGGER_LENGTH} characters"
            )
        if not re.match(constants.ENTRY_TRIGGER_PATTERN, trigger):
            raise InvalidEntryTriggerError(
                trigger, "trigger must contain only letters, digits, underscores, and hyphens"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage."""
        d: dict[str, Any] = {
            "keycombo": self.keycombo,
            "string": self.string,
            "filename": self.filename,
            "label": self.label,
            "category": self.category,
            "notes": self.notes,
        }
        if self.typing_delay_ms is not None:
            d["typing_delay_ms"] = self.typing_delay_ms
        if self.hold_delay_ms is not None:
            d["hold_delay_ms"] = self.hold_delay_ms
        return d

    @classmethod
    def from_dict(cls, trigger: str, data: dict[str, Any]) -> Entry:
        """Deserialize from a dictionary."""
        return cls(
            trigger=trigger,
            keycombo=data.get("keycombo", ""),
            string=data.get("string", ""),
            filename=data.get("filename", ""),
            label=data.get("label", ""),
            category=data.get("category", constants.DEFAULT_CATEGORY),
            notes=data.get("notes", ""),
            typing_delay_ms=data.get("typing_delay_ms"),
            hold_delay_ms=data.get("hold_delay_ms"),
        )


@dataclass
class Settings:
    """Global application settings."""

    typing_delay_ms: int = constants.DEFAULT_TYPING_DELAY_MS
    hold_delay_ms: int = constants.DEFAULT_HOLD_DELAY_MS
    use_keyring_cache: bool = True
    keyring_timeout_min: int = constants.DEFAULT_KEYRING_TIMEOUT_MIN

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "typing_delay_ms": self.typing_delay_ms,
            "hold_delay_ms": self.hold_delay_ms,
            "use_keyring_cache": self.use_keyring_cache,
            "keyring_timeout_min": self.keyring_timeout_min,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        """Deserialize from a dictionary."""
        return cls(
            typing_delay_ms=data.get("typing_delay_ms", constants.DEFAULT_TYPING_DELAY_MS),
            hold_delay_ms=data.get("hold_delay_ms", constants.DEFAULT_HOLD_DELAY_MS),
            use_keyring_cache=data.get("use_keyring_cache", True),
            keyring_timeout_min=data.get(
                "keyring_timeout_min", constants.DEFAULT_KEYRING_TIMEOUT_MIN
            ),
        )


@dataclass
class Config:
    """Top-level configuration container."""

    version: int = 2
    entries: dict[str, Entry] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)

    def add_entry(self, entry: Entry) -> None:
        """Add an entry. Raises DuplicateEntryError if trigger exists."""
        from ydoit.exceptions import DuplicateEntryError

        if entry.trigger in self.entries:
            raise DuplicateEntryError(entry.trigger)
        self.entries[entry.trigger] = entry

    def remove_entry(self, trigger: str) -> Entry:
        """Remove and return an entry. Raises EntryNotFoundError if missing."""
        from ydoit.exceptions import EntryNotFoundError

        if trigger not in self.entries:
            raise EntryNotFoundError(trigger)
        return self.entries.pop(trigger)

    def get_entry(self, trigger: str) -> Entry:
        """Get an entry by trigger. Raises EntryNotFoundError if missing."""
        from ydoit.exceptions import EntryNotFoundError

        if trigger not in self.entries:
            raise EntryNotFoundError(trigger)
        return self.entries[trigger]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire config to a dictionary."""
        return {
            "version": self.version,
            "entries": {trigger: entry.to_dict() for trigger, entry in self.entries.items()},
            "settings": self.settings.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Deserialize from a dictionary."""
        entries = {}
        for trigger, entry_data in data.get("entries", {}).items():
            entries[trigger] = Entry.from_dict(trigger, entry_data)

        settings = Settings.from_dict(data.get("settings", {}))

        return cls(
            version=data.get("version", 2),
            entries=entries,
            settings=settings,
        )

    @classmethod
    def from_json(cls, json_str: str) -> Config:
        """Deserialize from a JSON string."""
        import json

        return cls.from_dict(json.loads(json_str))
