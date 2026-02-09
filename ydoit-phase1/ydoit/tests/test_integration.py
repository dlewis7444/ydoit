"""Integration tests for ydoit — end-to-end workflows."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest

from ydoit.config_manager import ConfigManager
from ydoit.exceptions import DecryptionError
from ydoit.models import Config, Entry

if TYPE_CHECKING:
    from pathlib import Path

# Skip all tests if gpg is not available
pytestmark = pytest.mark.skipif(
    shutil.which("gpg2") is None and shutil.which("gpg") is None,
    reason="GnuPG not installed",
)


PASSPHRASE = "integration-test-passphrase"


@pytest.fixture
def cm(tmp_path: Path) -> ConfigManager:
    """ConfigManager with a fresh temp directory."""
    config_dir = tmp_path / "ydoit-config"
    return ConfigManager(
        config_dir=config_dir,
        passphrase_provider=lambda: PASSPHRASE,
    )


class TestFullLifecycle:
    """End-to-end: create → add → save → load → modify → remove."""

    def test_fresh_start_add_entries(self, cm: ConfigManager) -> None:
        """Start with no config, add entries, verify persistence."""
        # No config exists yet
        assert not cm.exists()

        # Create config and add entries
        config = cm.load()  # returns empty Config
        config.add_entry(
            Entry(name="pass1", keycombo="Super+F1", string="secret123")
        )
        config.add_entry(
            Entry(name="script1", keycombo="Super+F2", filename="/usr/bin/env")
        )

        cm.save(config, PASSPHRASE)
        assert cm.exists()

        # Reload and verify
        loaded = cm.load(PASSPHRASE)
        assert len(loaded.entries) == 2
        assert loaded.entries["pass1"].string == "secret123"
        assert loaded.entries["script1"].filename == "/usr/bin/env"

    def test_modify_and_remove(self, cm: ConfigManager) -> None:
        """Modify an entry's keycombo, then remove it."""
        config = Config()
        config.add_entry(Entry(name="test", keycombo="Super+F5", string="hello"))
        cm.save(config, PASSPHRASE)

        # Modify
        loaded = cm.load(PASSPHRASE)
        loaded.entries["test"].keycombo = "Super+F6"
        loaded.entries["test"].string = "updated"
        cm.save(loaded, PASSPHRASE)

        # Verify modification
        reloaded = cm.load(PASSPHRASE)
        assert reloaded.entries["test"].keycombo == "Super+F6"
        assert reloaded.entries["test"].string == "updated"

        # Remove
        reloaded.remove_entry("test")
        cm.save(reloaded, PASSPHRASE)

        # Verify removal
        final = cm.load(PASSPHRASE)
        assert len(final.entries) == 0


class TestV1Migration:
    """End-to-end v1 migration."""

    def test_v1_file_auto_migrates(self, cm: ConfigManager) -> None:
        """Place a v1-format encrypted file, load it, verify v2 structure."""
        v1_data = {
            "home1": {
                "keycombo": "Super+F11",
                "options": "-d 5 -H 5",
                "string": "supersecretpassword!\\n",
                "filename": "",
            },
            "setnet": {
                "keycombo": "Super+F8",
                "options": "-d 10 -H 10",
                "string": "",
                "filename": "/home/user/setnet.sh",
            },
        }

        # Manually encrypt v1 data
        cm._ensure_dir()
        cm._encrypt(json.dumps(v1_data), PASSPHRASE)

        # Load triggers migration
        config = cm.load(PASSPHRASE)

        assert config.version == 2
        assert len(config.entries) == 2
        assert config.entries["home1"].keycombo == "Super+F11"
        assert config.entries["setnet"].filename == "/home/user/setnet.sh"

        # Backup should exist
        backup_path = cm.data_file.with_name(cm.data_file.name + ".v1.bak")
        assert backup_path.exists()

        # Re-loading should return v2 directly (no re-migration)
        config2 = cm.load(PASSPHRASE)
        assert config2.version == 2


class TestExportImport:
    """End-to-end export and import."""

    def test_plain_export_import_round_trip(
        self, cm: ConfigManager, tmp_path: Path
    ) -> None:
        # Create and save
        config = Config()
        config.add_entry(
            Entry(name="entry1", keycombo="Super+F1", string="secret1")
        )
        config.add_entry(
            Entry(name="entry2", keycombo="Super+F2", filename="/tmp/file")
        )
        cm.save(config, PASSPHRASE)

        # Export as plain JSON
        export_path = tmp_path / "export.json"
        loaded = cm.load(PASSPHRASE)
        export_path.write_text(loaded.to_json(), encoding="utf-8")

        # Create a new ConfigManager (fresh directory)
        new_dir = tmp_path / "new-config"
        cm2 = ConfigManager(config_dir=new_dir)

        # Import
        raw = export_path.read_text(encoding="utf-8")
        imported = Config.from_json(raw)
        cm2.save(imported, PASSPHRASE)

        # Verify
        result = cm2.load(PASSPHRASE)
        assert set(result.entries.keys()) == {"entry1", "entry2"}
        assert result.entries["entry1"].string == "secret1"


class TestErrorRecovery:
    """Tests for error handling and edge cases."""

    def test_corrupt_file_gives_clear_error(self, cm: ConfigManager) -> None:
        """A corrupt GPG file gives a DecryptionError, not a crash."""
        cm._ensure_dir()
        cm.data_file.write_bytes(b"this is not a gpg file")

        with pytest.raises(DecryptionError):
            cm.load(PASSPHRASE)

    def test_passphrase_change(self, cm: ConfigManager) -> None:
        """Re-encrypt with a new passphrase."""
        config = Config()
        config.add_entry(Entry(name="test", keycombo="Super+F1", string="data"))
        cm.save(config, PASSPHRASE)

        # Load with old passphrase
        loaded = cm.load(PASSPHRASE)

        # Save with new passphrase
        new_passphrase = "new-passphrase-xyz"
        cm.save(loaded, new_passphrase)

        # Old passphrase should fail
        with pytest.raises(DecryptionError):
            cm.load(PASSPHRASE)

        # New passphrase should work
        result = cm.load(new_passphrase)
        assert result.entries["test"].string == "data"
