"""Tests for ydoit.config_manager."""

from __future__ import annotations

import json
import shutil
import stat
from typing import TYPE_CHECKING

import pytest

from ydoit import constants
from ydoit.config_manager import ConfigManager
from ydoit.exceptions import DecryptionError, EncryptionError
from ydoit.models import Config, Entry

if TYPE_CHECKING:
    from pathlib import Path

# Skip all tests if gpg is not available
pytestmark = pytest.mark.skipif(
    shutil.which("gpg2") is None and shutil.which("gpg") is None,
    reason="GnuPG not installed",
)


@pytest.fixture
def cm(config_dir: Path, sample_passphrase: str) -> ConfigManager:
    """Create a ConfigManager with a temp config directory."""
    return ConfigManager(
        config_dir=config_dir,
        passphrase_provider=lambda: sample_passphrase,
    )


class TestConfigManager:
    """Tests for ConfigManager encrypt/decrypt and file operations."""

    def test_exists_false_when_no_file(self, cm: ConfigManager) -> None:
        assert not cm.exists()

    def test_load_returns_empty_when_no_file(self, cm: ConfigManager) -> None:
        config = cm.load()
        assert isinstance(config, Config)
        assert config.entries == {}
        assert config.version == 2

    def test_save_and_load_round_trip(
        self, cm: ConfigManager, sample_config: Config, sample_passphrase: str
    ) -> None:
        cm.save(sample_config, sample_passphrase)
        assert cm.exists()

        loaded = cm.load(sample_passphrase)
        assert set(loaded.entries.keys()) == set(sample_config.entries.keys())
        for name in sample_config.entries:
            assert loaded.entries[name].keycombo == sample_config.entries[name].keycombo
            assert loaded.entries[name].string == sample_config.entries[name].string
            assert loaded.entries[name].filename == sample_config.entries[name].filename

    def test_wrong_passphrase_raises(
        self, cm: ConfigManager, sample_config: Config, sample_passphrase: str
    ) -> None:
        cm.save(sample_config, sample_passphrase)
        with pytest.raises(DecryptionError):
            cm.load("wrong-passphrase")

    def test_file_permissions(
        self, cm: ConfigManager, sample_config: Config, sample_passphrase: str
    ) -> None:
        cm.save(sample_config, sample_passphrase)
        file_mode = stat.S_IMODE(cm.data_file.stat().st_mode)
        assert file_mode == 0o600

    def test_dir_permissions(
        self, cm: ConfigManager, sample_config: Config, sample_passphrase: str
    ) -> None:
        cm.save(sample_config, sample_passphrase)
        dir_mode = stat.S_IMODE(cm.config_dir.stat().st_mode)
        assert dir_mode == 0o700

    def test_creates_config_dir(
        self, tmp_path: Path, sample_passphrase: str
    ) -> None:
        new_dir = tmp_path / "nonexistent" / "ydoit"
        cm = ConfigManager(
            config_dir=new_dir,
            passphrase_provider=lambda: sample_passphrase,
        )
        cm.save(Config(), sample_passphrase)
        assert new_dir.is_dir()

    def test_atomic_write_no_corruption_on_failure(
        self,
        cm: ConfigManager,
        sample_config: Config,
        sample_passphrase: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If encryption fails, the existing file should be untouched."""
        cm.save(sample_config, sample_passphrase)
        original_content = cm.data_file.read_bytes()

        # Make encryption fail by providing a broken gpg path
        monkeypatch.setattr(cm, "_gpg_path", "/nonexistent/gpg")

        with pytest.raises((EncryptionError, FileNotFoundError, OSError)):
            cm.save(sample_config, sample_passphrase)

        # Original file should be untouched
        assert cm.data_file.read_bytes() == original_content

    def test_special_characters_in_passphrase(
        self, cm: ConfigManager, sample_config: Config
    ) -> None:
        weird_pass = "p@$$w0rd!#%^&*()\n\ttabs"
        cm.save(sample_config, weird_pass)
        loaded = cm.load(weird_pass)
        assert set(loaded.entries.keys()) == set(sample_config.entries.keys())

    def test_unicode_in_entries(
        self, cm: ConfigManager, sample_passphrase: str
    ) -> None:
        config = Config()
        config.add_entry(
            Entry(name="unicode_test", keycombo="Super+F1", string="héllo wörld 日本語")
        )
        cm.save(config, sample_passphrase)
        loaded = cm.load(sample_passphrase)
        assert loaded.entries["unicode_test"].string == "héllo wörld 日本語"

    def test_v1_migration_on_load(
        self, cm: ConfigManager, v1_data: dict, sample_passphrase: str
    ) -> None:
        """Loading a v1-format file triggers auto-migration."""
        # Manually encrypt v1 data
        plaintext = json.dumps(v1_data)
        cm._ensure_dir()
        cm._encrypt(plaintext, sample_passphrase)

        loaded = cm.load(sample_passphrase)
        assert loaded.version == 2
        assert "home1" in loaded.entries
        assert loaded.entries["home1"].keycombo == "Super+F11"

    def test_v1_migration_creates_backup(
        self, cm: ConfigManager, v1_data: dict, sample_passphrase: str
    ) -> None:
        plaintext = json.dumps(v1_data)
        cm._ensure_dir()
        cm._encrypt(plaintext, sample_passphrase)

        cm.load(sample_passphrase)

        backup = cm.data_file.with_name(cm.data_file.name + constants.BACKUP_SUFFIX)
        assert backup.exists()

    def test_lock_for_write(self, cm: ConfigManager) -> None:
        """File lock prevents concurrent writes."""
        cm._ensure_dir()

        with cm.lock_for_write():  # noqa: SIM117
            # Second lock should fail
            with pytest.raises(TimeoutError, match="Another ydoit"):
                with cm.lock_for_write():
                    pass

    def test_save_empty_config(
        self, cm: ConfigManager, sample_passphrase: str
    ) -> None:
        cm.save(Config(), sample_passphrase)
        loaded = cm.load(sample_passphrase)
        assert loaded.entries == {}
        assert loaded.version == 2
