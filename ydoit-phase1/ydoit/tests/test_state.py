"""Tests for AppState controller."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ydoit.config_manager import ConfigManager
from ydoit.exceptions import (
    DecryptionError,
    DuplicateEntryError,
    EntryNotFoundError,
    ShortcutConflictError,
    YdoitError,
)
from ydoit.models import Config, Entry
from ydoit.shortcut_manager import ConflictInfo, ShortcutManager
from ydoit.state import AppState


@pytest.fixture
def mock_config_manager():
    cm = MagicMock(spec=ConfigManager)
    cm.exists.return_value = True
    cm.load.return_value = Config()
    return cm


@pytest.fixture
def mock_shortcut_manager():
    sm = MagicMock(spec=ShortcutManager)
    sm.find_conflict.return_value = None
    return sm


@pytest.fixture
def state(mock_config_manager, mock_shortcut_manager):
    return AppState(
        config_manager=mock_config_manager,
        shortcut_manager=mock_shortcut_manager,
    )


@pytest.fixture
def unlocked_state(state, mock_config_manager, sample_config):
    mock_config_manager.load.return_value = sample_config
    state.unlock("test-pass")
    return state


class TestAppStateLocking:
    def test_starts_locked(self, state):
        assert not state.is_unlocked

    def test_config_raises_when_locked(self, state):
        with pytest.raises(YdoitError, match="locked"):
            _ = state.config

    def test_entries_raises_when_locked(self, state):
        with pytest.raises(YdoitError, match="locked"):
            _ = state.entries

    def test_settings_raises_when_locked(self, state):
        with pytest.raises(YdoitError, match="locked"):
            _ = state.settings

    def test_unlock(self, state, mock_config_manager):
        mock_config_manager.load.return_value = Config()
        state.unlock("test-pass")
        assert state.is_unlocked
        mock_config_manager.load.assert_called_with("test-pass")

    def test_unlock_emits_signals(self, state, mock_config_manager):
        signals = []
        state.connect("unlocked", lambda _: signals.append("unlocked"))
        state.connect("entries-changed", lambda _: signals.append("entries-changed"))

        mock_config_manager.load.return_value = Config()
        state.unlock("test-pass")

        assert "unlocked" in signals
        assert "entries-changed" in signals

    def test_unlock_wrong_passphrase(self, state, mock_config_manager):
        mock_config_manager.load.side_effect = DecryptionError("wrong")
        with pytest.raises(DecryptionError):
            state.unlock("wrong-pass")
        assert not state.is_unlocked

    def test_lock(self, unlocked_state):
        signals = []
        unlocked_state.connect("locked", lambda _: signals.append("locked"))
        unlocked_state.lock()
        assert not unlocked_state.is_unlocked
        assert "locked" in signals

    def test_config_exists(self, state, mock_config_manager):
        mock_config_manager.exists.return_value = True
        assert state.config_exists
        mock_config_manager.exists.return_value = False
        assert not state.config_exists


class TestAppStateCRUD:
    def test_add_entry(self, unlocked_state, mock_config_manager, mock_shortcut_manager):
        signals = []
        unlocked_state.connect("entries-changed", lambda _: signals.append(True))

        entry = Entry(name="test1", keycombo="Super+F1", string="hello")
        unlocked_state.add_entry(entry)

        assert "test1" in unlocked_state.entries
        mock_config_manager.save.assert_called()
        mock_shortcut_manager.register_shortcut.assert_called_with(entry)
        assert signals

    def test_add_entry_no_keycombo(self, unlocked_state, mock_shortcut_manager):
        entry = Entry(name="test1", keycombo="", string="hello")
        unlocked_state.add_entry(entry)

        assert "test1" in unlocked_state.entries
        mock_shortcut_manager.register_shortcut.assert_not_called()

    def test_add_duplicate_entry(self, unlocked_state):
        with pytest.raises(DuplicateEntryError):
            unlocked_state.add_entry(
                Entry(name="home1", keycombo="Super+F12", string="dupe")
            )

    def test_add_entry_shortcut_conflict(self, unlocked_state, mock_shortcut_manager):
        mock_shortcut_manager.find_conflict.return_value = ConflictInfo(
            keycombo="Super+F1",
            existing_name="other",
            existing_source="custom",
        )
        with pytest.raises(ShortcutConflictError):
            unlocked_state.add_entry(
                Entry(name="test1", keycombo="Super+F1", string="hello")
            )

    def test_add_entry_force_shortcut(self, unlocked_state, mock_shortcut_manager):
        mock_shortcut_manager.find_conflict.return_value = ConflictInfo(
            keycombo="Super+F1",
            existing_name="other",
            existing_source="custom",
        )
        entry = Entry(name="test1", keycombo="Super+F1", string="hello")
        unlocked_state.add_entry(entry, force_shortcut=True)
        assert "test1" in unlocked_state.entries

    def test_remove_entry(self, unlocked_state, mock_config_manager, mock_shortcut_manager):
        removed = unlocked_state.remove_entry("home1")
        assert removed.name == "home1"
        assert "home1" not in unlocked_state.entries
        mock_config_manager.save.assert_called()
        mock_shortcut_manager.unregister_shortcut.assert_called_with("home1")

    def test_remove_nonexistent(self, unlocked_state):
        with pytest.raises(EntryNotFoundError):
            unlocked_state.remove_entry("nonexistent")

    def test_get_entry(self, unlocked_state):
        entry = unlocked_state.get_entry("home1")
        assert entry.name == "home1"

    def test_get_nonexistent_entry(self, unlocked_state):
        with pytest.raises(EntryNotFoundError):
            unlocked_state.get_entry("nonexistent")

    def test_update_entry(self, unlocked_state, mock_config_manager):
        updated = unlocked_state.update_entry("home1", label="New Label")
        assert updated.label == "New Label"
        mock_config_manager.save.assert_called()

    def test_update_entry_keycombo(self, unlocked_state, mock_shortcut_manager):
        unlocked_state.update_entry("home1", keycombo="Super+F12")
        entry = unlocked_state.get_entry("home1")
        assert entry.keycombo == "Super+F12"
        mock_shortcut_manager.register_shortcut.assert_called()

    def test_update_entry_conflict(self, unlocked_state, mock_shortcut_manager):
        mock_shortcut_manager.find_conflict.return_value = ConflictInfo(
            keycombo="Super+F1",
            existing_name="other",
            existing_source="custom",
        )
        with pytest.raises(ShortcutConflictError):
            unlocked_state.update_entry("home1", keycombo="Super+F1")

    def test_update_entry_same_keycombo_no_conflict(
        self, unlocked_state, mock_shortcut_manager
    ):
        # Updating with the same keycombo should not trigger conflict check
        original_keycombo = unlocked_state.get_entry("home1").keycombo
        unlocked_state.update_entry("home1", keycombo=original_keycombo)
        mock_shortcut_manager.find_conflict.assert_not_called()

    def test_update_entry_typing_delay(self, unlocked_state):
        unlocked_state.update_entry("home1", typing_delay_ms=10)
        entry = unlocked_state.get_entry("home1")
        assert entry.typing_delay_ms == 10

    def test_update_entry_clear_typing_delay(self, unlocked_state):
        unlocked_state.update_entry("home1", typing_delay_ms=10)
        unlocked_state.update_entry("home1", typing_delay_ms=None)
        entry = unlocked_state.get_entry("home1")
        assert entry.typing_delay_ms is None


class TestAppStateCategories:
    def test_get_entries_by_category(self, unlocked_state):
        categories = unlocked_state.get_entries_by_category()
        assert "passwords" in categories
        assert "scripts" in categories
        assert categories["passwords"][0].name == "home1"
        # scripts should be sorted by name
        script_names = [e.name for e in categories["scripts"]]
        assert script_names == sorted(script_names)


class TestAppStateSettings:
    def test_update_settings(self, unlocked_state, mock_config_manager):
        signals = []
        unlocked_state.connect("settings-changed", lambda _: signals.append(True))

        result = unlocked_state.update_settings(typing_delay_ms=10)
        assert result.typing_delay_ms == 10
        mock_config_manager.save.assert_called()
        assert signals

    def test_update_settings_partial(self, unlocked_state):
        original_hold = unlocked_state.settings.hold_delay_ms
        unlocked_state.update_settings(typing_delay_ms=20)
        assert unlocked_state.settings.typing_delay_ms == 20
        assert unlocked_state.settings.hold_delay_ms == original_hold

    def test_update_keyring_settings(self, unlocked_state):
        unlocked_state.update_settings(
            use_keyring_cache=False, keyring_timeout_min=30
        )
        assert not unlocked_state.settings.use_keyring_cache
        assert unlocked_state.settings.keyring_timeout_min == 30


class TestAppStateShortcuts:
    def test_find_shortcut_conflict(self, unlocked_state, mock_shortcut_manager):
        mock_shortcut_manager.find_conflict.return_value = None
        assert unlocked_state.find_shortcut_conflict("Super+F1") is None
        mock_shortcut_manager.find_conflict.assert_called_with("Super+F1", None)

    def test_find_shortcut_conflict_with_exclude(self, unlocked_state, mock_shortcut_manager):
        unlocked_state.find_shortcut_conflict("Super+F1", exclude_entry="home1")
        mock_shortcut_manager.find_conflict.assert_called_with("Super+F1", "home1")

    def test_sync_shortcuts(self, unlocked_state, mock_shortcut_manager):
        unlocked_state.sync_shortcuts()
        mock_shortcut_manager.sync.assert_called_with(unlocked_state.config)


class TestAppStateExportImport:
    def test_export_plain(self, unlocked_state, tmp_path):
        output = tmp_path / "export.json"
        count = unlocked_state.export_plain(output)
        assert count == 3
        assert output.exists()
        content = output.read_text()
        assert "home1" in content

    def test_import_config(self, unlocked_state, mock_shortcut_manager, tmp_path):
        # Create an export file
        export_file = tmp_path / "import.json"
        import_config = Config()
        import_config.add_entry(Entry(name="imported1", keycombo="Super+F12", string="new"))
        export_file.write_text(import_config.to_json(), encoding="utf-8")

        count = unlocked_state.import_config(export_file)
        assert count == 1
        assert "imported1" in unlocked_state.entries
        mock_shortcut_manager.sync.assert_called()


class TestAppStatePassphrase:
    def test_change_passphrase(self, unlocked_state, mock_config_manager):
        unlocked_state.change_passphrase("test-pass", "new-pass")
        mock_config_manager.load.assert_called_with("test-pass")
        mock_config_manager.save.assert_called()

    def test_change_passphrase_wrong_old(self, unlocked_state, mock_config_manager):
        mock_config_manager.load.side_effect = DecryptionError("wrong")
        with pytest.raises(DecryptionError):
            unlocked_state.change_passphrase("wrong", "new-pass")
