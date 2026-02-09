"""Data model for ydoit configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ydoit import constants
from ydoit.exceptions import InvalidEntryNameError


class EntryType(Enum):
    """Whether an entry types a literal string or the contents of a file."""

    STRING = "string"
    FILE = "file"


@dataclass
class Entry:
    """A single auto-type entry."""

    name: str
    keycombo: str
    string: str = ""
    filename: str = ""
    label: str = ""
    category: str = constants.DEFAULT_CATEGORY
    notes: str = ""
    typing_delay_ms: int | None = None
    hold_delay_ms: int | None = None

    def __post_init__(self) -> None:
        self.validate_name(self.name)

    @property
    def entry_type(self) -> EntryType:
        """Determine whether this entry types a string or file contents."""
        return EntryType.FILE if self.filename else EntryType.STRING

    @property
    def display_label(self) -> str:
        """Return the label for display, falling back to name."""
        return self.label or self.name

    @staticmethod
    def validate_name(name: str) -> None:
        """Validate an entry name. Raises InvalidEntryNameError if invalid."""
        if not name:
            raise InvalidEntryNameError(name, "name cannot be empty")
        if len(name) > constants.MAX_ENTRY_NAME_LENGTH:
            raise InvalidEntryNameError(
                name, f"name exceeds {constants.MAX_ENTRY_NAME_LENGTH} characters"
            )
        if not re.match(constants.ENTRY_NAME_PATTERN, name):
            raise InvalidEntryNameError(
                name, "name must contain only letters, digits, underscores, and hyphens"
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
    def from_dict(cls, name: str, data: dict[str, Any]) -> Entry:
        """Deserialize from a dictionary."""
        return cls(
            name=name,
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
        """Add an entry. Raises DuplicateEntryError if name exists."""
        from ydoit.exceptions import DuplicateEntryError

        if entry.name in self.entries:
            raise DuplicateEntryError(entry.name)
        self.entries[entry.name] = entry

    def remove_entry(self, name: str) -> Entry:
        """Remove and return an entry. Raises EntryNotFoundError if missing."""
        from ydoit.exceptions import EntryNotFoundError

        if name not in self.entries:
            raise EntryNotFoundError(name)
        return self.entries.pop(name)

    def get_entry(self, name: str) -> Entry:
        """Get an entry by name. Raises EntryNotFoundError if missing."""
        from ydoit.exceptions import EntryNotFoundError

        if name not in self.entries:
            raise EntryNotFoundError(name)
        return self.entries[name]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire config to a dictionary."""
        return {
            "version": self.version,
            "entries": {name: entry.to_dict() for name, entry in self.entries.items()},
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
        for name, entry_data in data.get("entries", {}).items():
            entries[name] = Entry.from_dict(name, entry_data)

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
