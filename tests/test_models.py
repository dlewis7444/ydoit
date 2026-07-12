"""Tests for ydoit.models."""

from __future__ import annotations

import json

import pytest

from ydoit.exceptions import (
    DuplicateEntryError,
    EntryNotFoundError,
    InvalidEntryTriggerError,
)
from ydoit.models import Config, Entry, EntryType, Settings


class TestEntry:
    """Tests for the Entry dataclass."""

    def test_string_entry_type(self) -> None:
        entry = Entry(trigger="test", keycombo="Super+F1", string="hello")
        assert entry.entry_type == EntryType.STRING

    def test_file_entry_type(self) -> None:
        entry = Entry(trigger="test", keycombo="Super+F1", filename="/tmp/file.txt")
        assert entry.entry_type == EntryType.FILE

    def test_file_takes_precedence(self) -> None:
        """If both string and filename are set, filename wins."""
        entry = Entry(
            trigger="test", keycombo="Super+F1", string="hello", filename="/tmp/f"
        )
        assert entry.entry_type == EntryType.FILE

    def test_display_label_with_label(self) -> None:
        entry = Entry(trigger="test", keycombo="Super+F1", label="My Label")
        assert entry.display_label == "My Label"

    def test_display_label_fallback_to_name(self) -> None:
        entry = Entry(trigger="test", keycombo="Super+F1")
        assert entry.display_label == "test"

    def test_validate_trigger_valid(self) -> None:
        for name in ["test", "my_entry", "entry-1", "ABC123", "a"]:
            Entry.validate_trigger(name)  # Should not raise

    def test_validate_trigger_empty(self) -> None:
        with pytest.raises(InvalidEntryTriggerError, match="empty"):
            Entry.validate_trigger("")

    def test_validate_trigger_too_long(self) -> None:
        with pytest.raises(InvalidEntryTriggerError, match="exceeds"):
            Entry.validate_trigger("x" * 100)

    def test_validate_trigger_invalid_chars(self) -> None:
        for name in ["has space", "has.dot", "has/slash", "has@at", "café"]:
            with pytest.raises(InvalidEntryTriggerError, match="must contain only"):
                Entry.validate_trigger(name)

    def test_to_dict_minimal(self) -> None:
        entry = Entry(trigger="test", keycombo="Super+F1")
        d = entry.to_dict()
        assert d["keycombo"] == "Super+F1"
        assert d["string"] == ""
        assert d["filename"] == ""
        assert "typing_delay_ms" not in d  # None values excluded
        assert "trigger" not in d  # trigger is the dict key, not a value

    def test_to_dict_with_overrides(self) -> None:
        entry = Entry(
            trigger="test",
            keycombo="Ctrl+Alt+P",
            string="secret",
            typing_delay_ms=10,
            hold_delay_ms=20,
        )
        d = entry.to_dict()
        assert d["typing_delay_ms"] == 10
        assert d["hold_delay_ms"] == 20

    def test_from_dict_round_trip(self) -> None:
        original = Entry(
            trigger="test",
            keycombo="Super+F11",
            string="hello\nworld",
            label="Test Entry",
            category="passwords",
            notes="a note",
            typing_delay_ms=10,
        )
        d = original.to_dict()
        restored = Entry.from_dict("test", d)
        assert restored.trigger == original.trigger
        assert restored.keycombo == original.keycombo
        assert restored.string == original.string
        assert restored.label == original.label
        assert restored.category == original.category
        assert restored.notes == original.notes
        assert restored.typing_delay_ms == original.typing_delay_ms
        assert restored.hold_delay_ms is None

    def test_from_dict_missing_fields(self) -> None:
        """Gracefully handle missing optional fields."""
        entry = Entry.from_dict("test", {"keycombo": "Super+F1"})
        assert entry.string == ""
        assert entry.filename == ""
        assert entry.label == ""
        assert entry.category == "general"

    def test_special_characters_in_string(self) -> None:
        """Strings with newlines, tabs, unicode survive round-trip."""
        text = "line1\nline2\ttab\u00e9\u00e8\\"
        entry = Entry(trigger="test", keycombo="Super+F1", string=text)
        d = entry.to_dict()
        restored = Entry.from_dict("test", d)
        assert restored.string == text


class TestSettings:
    """Tests for the Settings dataclass."""

    def test_defaults(self) -> None:
        s = Settings()
        assert s.typing_delay_ms == 5
        assert s.hold_delay_ms == 5
        assert s.use_keyring_cache is True
        assert s.keyring_timeout_min == 15
        assert s.input_backend == "auto"

    def test_round_trip(self) -> None:
        s = Settings(
            typing_delay_ms=10,
            hold_delay_ms=20,
            use_keyring_cache=False,
            keyring_timeout_min=0,
            input_backend="mutter",
        )
        d = s.to_dict()
        restored = Settings.from_dict(d)
        assert restored.typing_delay_ms == 10
        assert restored.hold_delay_ms == 20
        assert restored.use_keyring_cache is False
        assert restored.keyring_timeout_min == 0
        assert restored.input_backend == "mutter"

    def test_from_dict_defaults(self) -> None:
        s = Settings.from_dict({})
        assert s.typing_delay_ms == 5
        assert s.use_keyring_cache is True
        assert s.input_backend == "auto"

    def test_unknown_input_backend_becomes_auto(self) -> None:
        s = Settings.from_dict({"input_backend": "libei"})
        assert s.input_backend == "auto"


class TestConfig:
    """Tests for the Config dataclass."""

    def test_empty_config(self) -> None:
        config = Config()
        assert config.version == 2
        assert config.entries == {}
        assert isinstance(config.settings, Settings)

    def test_add_entry(self) -> None:
        config = Config()
        entry = Entry(trigger="test", keycombo="Super+F1", string="hello")
        config.add_entry(entry)
        assert "test" in config.entries
        assert config.entries["test"] is entry

    def test_add_duplicate_raises(self) -> None:
        config = Config()
        config.add_entry(Entry(trigger="test", keycombo="Super+F1"))
        with pytest.raises(DuplicateEntryError, match="test"):
            config.add_entry(Entry(trigger="test", keycombo="Super+F2"))

    def test_remove_entry(self) -> None:
        config = Config()
        config.add_entry(Entry(trigger="test", keycombo="Super+F1"))
        removed = config.remove_entry("test")
        assert removed.trigger == "test"
        assert "test" not in config.entries

    def test_remove_nonexistent_raises(self) -> None:
        config = Config()
        with pytest.raises(EntryNotFoundError, match="nope"):
            config.remove_entry("nope")

    def test_get_entry(self) -> None:
        config = Config()
        config.add_entry(Entry(trigger="test", keycombo="Super+F1"))
        assert config.get_entry("test").trigger == "test"

    def test_get_nonexistent_raises(self) -> None:
        config = Config()
        with pytest.raises(EntryNotFoundError):
            config.get_entry("nope")

    def test_json_round_trip(self, sample_config: Config) -> None:
        json_str = sample_config.to_json()
        restored = Config.from_json(json_str)
        assert restored.version == sample_config.version
        assert set(restored.entries.keys()) == set(sample_config.entries.keys())
        for name in sample_config.entries:
            orig = sample_config.entries[name]
            rest = restored.entries[name]
            assert rest.keycombo == orig.keycombo
            assert rest.string == orig.string
            assert rest.filename == orig.filename
            assert rest.label == orig.label
            assert rest.category == orig.category

    def test_json_round_trip_empty(self) -> None:
        config = Config()
        restored = Config.from_json(config.to_json())
        assert restored.version == 2
        assert restored.entries == {}

    def test_to_json_produces_valid_json(self, sample_config: Config) -> None:
        json_str = sample_config.to_json()
        parsed = json.loads(json_str)
        assert parsed["version"] == 2
        assert "entries" in parsed
        assert "settings" in parsed

    def test_large_config(self) -> None:
        """100+ entries round-trip correctly."""
        config = Config()
        for i in range(150):
            config.add_entry(
                Entry(trigger=f"entry_{i}", keycombo=f"Super+F{i}", string=f"text_{i}")
            )
        restored = Config.from_json(config.to_json())
        assert len(restored.entries) == 150
        assert restored.entries["entry_99"].string == "text_99"
