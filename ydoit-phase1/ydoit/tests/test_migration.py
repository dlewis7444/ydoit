"""Tests for ydoit.migration."""

from __future__ import annotations

from ydoit.migration import detect_version, migrate_v1_to_v2, parse_v1_options
from ydoit.models import Config


class TestDetectVersion:
    """Tests for version detection."""

    def test_v1_no_version_key(self, v1_data: dict) -> None:
        assert detect_version(v1_data) == 1

    def test_v2_with_version_key(self) -> None:
        assert detect_version({"version": 2, "entries": {}}) == 2

    def test_future_version(self) -> None:
        assert detect_version({"version": 3, "entries": {}}) == 3

    def test_empty_dict_is_v1(self) -> None:
        assert detect_version({}) == 1


class TestParseV1Options:
    """Tests for xdotool options parsing."""

    def test_standard_options(self) -> None:
        assert parse_v1_options("-d 5 -H 5") == (5, 5)

    def test_different_values(self) -> None:
        assert parse_v1_options("-d 10 -H 20") == (10, 20)

    def test_only_delay(self) -> None:
        typing, hold = parse_v1_options("-d 10")
        assert typing == 10
        assert hold == 5  # default

    def test_only_hold(self) -> None:
        typing, hold = parse_v1_options("-H 10")
        assert typing == 5  # default
        assert hold == 10

    def test_empty_string(self) -> None:
        assert parse_v1_options("") == (5, 5)

    def test_none_like_empty(self) -> None:
        assert parse_v1_options("   ") == (5, 5)

    def test_extra_flags_ignored(self) -> None:
        typing, hold = parse_v1_options("-d 5 -H 5 --clearmodifiers")
        assert typing == 5
        assert hold == 5


class TestMigrateV1ToV2:
    """Tests for v1 → v2 migration."""

    def test_migrate_sample_data(self, v1_data: dict) -> None:
        result = migrate_v1_to_v2(v1_data)
        assert result["version"] == 2
        assert "entries" in result
        assert "settings" in result
        assert set(result["entries"].keys()) == {"home1", "setnet", "tmpfile"}

    def test_entry_fields_migrated(self, v1_data: dict) -> None:
        result = migrate_v1_to_v2(v1_data)
        home1 = result["entries"]["home1"]
        assert home1["keycombo"] == "Super+F11"
        assert home1["string"] == "supersecretpassword!\\n"
        assert home1["filename"] == ""
        assert home1["label"] == "home1"

    def test_categories_assigned(self, v1_data: dict) -> None:
        result = migrate_v1_to_v2(v1_data)
        # home1 has a string → passwords
        assert result["entries"]["home1"]["category"] == "passwords"
        # setnet has a filename → scripts
        assert result["entries"]["setnet"]["category"] == "scripts"

    def test_options_parsed_into_global_settings(self, v1_data: dict) -> None:
        result = migrate_v1_to_v2(v1_data)
        settings = result["settings"]
        assert settings["typing_delay_ms"] == 5
        assert settings["hold_delay_ms"] == 5

    def test_per_entry_delays_cleared_when_matching_global(self, v1_data: dict) -> None:
        """If all entries have the same delay, it becomes the global default
        and per-entry overrides are removed."""
        result = migrate_v1_to_v2(v1_data)
        for entry in result["entries"].values():
            assert "typing_delay_ms" not in entry
            assert "hold_delay_ms" not in entry

    def test_per_entry_delays_kept_when_different(self) -> None:
        """Entries with different delays keep per-entry overrides."""
        data = {
            "fast": {
                "keycombo": "Super+F1", "options": "-d 1 -H 1",
                "string": "x", "filename": "",
            },
            "slow": {
                "keycombo": "Super+F2", "options": "-d 50 -H 50",
                "string": "y", "filename": "",
            },
            "normal": {
                "keycombo": "Super+F3", "options": "-d 1 -H 1",
                "string": "z", "filename": "",
            },
        }
        result = migrate_v1_to_v2(data)
        # "1" is most common → becomes global default
        assert result["settings"]["typing_delay_ms"] == 1
        # "slow" should keep its override
        assert result["entries"]["slow"]["typing_delay_ms"] == 50

    def test_settings_include_keyring_defaults(self, v1_data: dict) -> None:
        result = migrate_v1_to_v2(v1_data)
        assert result["settings"]["use_keyring_cache"] is True
        assert result["settings"]["keyring_timeout_min"] == 15

    def test_migration_notes(self, v1_data: dict) -> None:
        result = migrate_v1_to_v2(v1_data)
        assert "Migrated from v1" in result["entries"]["home1"]["notes"]

    def test_result_parseable_as_config(self, v1_data: dict) -> None:
        """Migrated data can be loaded as a Config object."""
        result = migrate_v1_to_v2(v1_data)
        config = Config.from_dict(result)
        assert len(config.entries) == 3
        assert config.version == 2
        assert config.entries["home1"].keycombo == "Super+F11"

    def test_empty_data(self) -> None:
        result = migrate_v1_to_v2({})
        assert result["version"] == 2
        assert result["entries"] == {}

    def test_non_dict_values_skipped(self) -> None:
        """Non-dict values in v1 data are ignored."""
        data = {
            "valid": {"keycombo": "Super+F1", "options": "", "string": "x", "filename": ""},
            "invalid": "not a dict",
        }
        result = migrate_v1_to_v2(data)
        assert "valid" in result["entries"]
        assert "invalid" not in result["entries"]
