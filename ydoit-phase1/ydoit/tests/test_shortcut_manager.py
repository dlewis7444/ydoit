"""Tests for ydoit.shortcut_manager."""

from __future__ import annotations

import sys
import unittest.mock as mock

import pytest

from ydoit.exceptions import GioNotAvailableError
from ydoit.models import Config, Entry
from ydoit.shortcut_manager import ConflictInfo, GnomeShortcut, ShortcutManager, SyncResult

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

BASE_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"


def make_entry(
    name: str = "home1",
    keycombo: str = "Super+F11",
    label: str = "Home Password",
) -> Entry:
    return Entry(name=name, keycombo=keycombo, label=label)


def make_config(*entries: Entry) -> Config:
    cfg = Config()
    for e in entries:
        cfg.entries[e.name] = e
    return cfg


def _make_kb_settings(name: str, command: str, binding: str) -> mock.MagicMock:
    """Return a mock kb_settings object with get_string wired up."""
    kb = mock.MagicMock()

    def _get_string(key: str) -> str:
        return {"name": name, "command": command, "binding": binding}[key]

    kb.get_string.side_effect = _get_string
    return kb


@pytest.fixture()
def mock_gio(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    """Inject a clean mock Gio module hierarchy and return the Gio mock."""
    gio_mod = mock.MagicMock()
    gi_mod = mock.MagicMock()
    gi_mod.repository.Gio = gio_mod

    monkeypatch.setitem(sys.modules, "gi", gi_mod)
    monkeypatch.setitem(sys.modules, "gi.repository", gi_mod.repository)
    monkeypatch.setitem(sys.modules, "gi.repository.Gio", gio_mod)

    return gio_mod


@pytest.fixture()
def manager_with_gio(mock_gio: mock.MagicMock) -> tuple[ShortcutManager, mock.MagicMock]:
    """Return a ShortcutManager that thinks Gio is available, plus the Gio mock."""
    mgr = ShortcutManager()
    mgr._gio_available = True  # skip the real import dance
    return mgr, mock_gio


# ---------------------------------------------------------------------------
# Helpers that configure Gio mock return values for common scenarios
# ---------------------------------------------------------------------------


def _setup_gio_shortcuts(
    mock_gio: mock.MagicMock,
    shortcuts: list[dict],
) -> None:
    """
    Wire mock_gio so that:
    - Gio.Settings.new() returns a media-keys mock whose get_strv yields [path, ...]
    - Gio.Settings.new_with_path(schema, path) returns a per-shortcut mock.

    Each element of *shortcuts* must be a dict with keys:
        path, name, command, binding
    """
    paths = [s["path"] for s in shortcuts]

    media_keys_mock = mock.MagicMock()
    media_keys_mock.get_strv.return_value = paths
    media_keys_mock.set_strv = mock.MagicMock()

    kb_mocks: dict[str, mock.MagicMock] = {}
    for s in shortcuts:
        kb_mocks[s["path"]] = _make_kb_settings(s["name"], s["command"], s["binding"])

    def _new(schema_id: str) -> mock.MagicMock:
        return media_keys_mock

    def _new_with_path(schema_id: str, path: str) -> mock.MagicMock:
        return kb_mocks.get(path, mock.MagicMock())

    mock_gio.Settings.new.side_effect = _new
    mock_gio.Settings.new_with_path.side_effect = _new_with_path


class TestGnomeShortcut:
    """Tests for GnomeShortcut dataclass."""

    def test_is_ydoit(self) -> None:
        s = GnomeShortcut(
            path="/custom0/", name="ydoit: Home Password",
            command="ydoit type home1", binding="<Super>F11"
        )
        assert s.is_ydoit is True

    def test_is_not_ydoit(self) -> None:
        s = GnomeShortcut(
            path="/custom0/", name="My Script",
            command="/usr/bin/script.sh", binding="<Super>F11"
        )
        assert s.is_ydoit is False

    def test_entry_name_extraction(self) -> None:
        s = GnomeShortcut(
            path="/custom0/", name="ydoit: Home Password",
            command="ydoit type home1", binding="<Super>F11"
        )
        assert s.entry_name == "home1"

    def test_entry_name_non_ydoit(self) -> None:
        s = GnomeShortcut(
            path="/custom0/", name="Other",
            command="other cmd", binding="<Super>F11"
        )
        assert s.entry_name is None


class TestFormatConversion:
    """Tests for key combo format translation."""

    @pytest.mark.parametrize(
        "user_input,expected",
        [
            ("Super+F11", "<Super>F11"),
            ("Ctrl+Alt+P", "<Primary><Alt>p"),
            ("Shift+Super+S", "<Shift><Super>s"),
            ("Ctrl+Shift+1", "<Primary><Shift>1"),
            ("Alt+Tab", "<Alt>Tab"),
            ("Super+A", "<Super>a"),
            ("Ctrl+C", "<Primary>c"),
            ("F5", "F5"),
        ],
    )
    def test_to_gnome_binding(self, user_input: str, expected: str) -> None:
        assert ShortcutManager.to_gnome_binding(user_input) == expected

    @pytest.mark.parametrize(
        "gnome_binding,expected",
        [
            ("<Super>F11", "Super+F11"),
            ("<Primary><Alt>p", "Ctrl+Alt+P"),
            ("<Shift><Super>s", "Shift+Super+S"),
            ("<Primary><Shift>1", "Ctrl+Shift+1"),
            ("<Alt>Tab", "Alt+Tab"),
            ("<Super>a", "Super+A"),
            ("F5", "F5"),
        ],
    )
    def test_from_gnome_binding(self, gnome_binding: str, expected: str) -> None:
        assert ShortcutManager.from_gnome_binding(gnome_binding) == expected

    @pytest.mark.parametrize(
        "keycombo",
        [
            "Super+F11",
            "Ctrl+Alt+P",
            "Shift+Super+S",
            "Ctrl+Shift+1",
            "F5",
            "Super+A",
        ],
    )
    def test_round_trip(self, keycombo: str) -> None:
        gnome = ShortcutManager.to_gnome_binding(keycombo)
        restored = ShortcutManager.from_gnome_binding(gnome)
        assert restored == keycombo

    def test_empty_string(self) -> None:
        assert ShortcutManager.to_gnome_binding("") == ""
        assert ShortcutManager.from_gnome_binding("") == ""

    def test_control_alias(self) -> None:
        """'Control' should be treated the same as 'Ctrl'."""
        assert ShortcutManager.to_gnome_binding("Control+C") == "<Primary>c"

    def test_meta_alias(self) -> None:
        """'Meta' should map to Super."""
        assert ShortcutManager.to_gnome_binding("Meta+F1") == "<Super>F1"

    def test_unknown_modifier_passthrough(self) -> None:
        """An unrecognised modifier is wrapped in angle brackets verbatim."""
        result = ShortcutManager.to_gnome_binding("Hyper+F1")
        assert result == "<Hyper>F1"


class TestMakeCommand:
    """Tests for command generation."""

    def test_simple(self) -> None:
        assert ShortcutManager.make_command("home1") == "ydoit type home1"

    def test_with_hyphens(self) -> None:
        assert ShortcutManager.make_command("my-entry") == "ydoit type my-entry"


class TestSyncResult:
    """Tests for SyncResult."""

    def test_empty(self) -> None:
        r = SyncResult()
        assert r.total_changes == 0
        assert str(r) == "no changes"

    def test_with_changes(self) -> None:
        r = SyncResult(added=2, updated=1, removed=3)
        assert r.total_changes == 6
        assert "2 added" in str(r)
        assert "1 updated" in str(r)
        assert "3 removed" in str(r)

    def test_with_errors(self) -> None:
        r = SyncResult(errors=["something broke"])
        assert "1 errors" in str(r)

    def test_total_changes_only_added(self) -> None:
        r = SyncResult(added=5)
        assert r.total_changes == 5

    def test_total_changes_only_updated(self) -> None:
        r = SyncResult(updated=3)
        assert r.total_changes == 3

    def test_total_changes_only_removed(self) -> None:
        r = SyncResult(removed=7)
        assert r.total_changes == 7

    def test_str_errors_only(self) -> None:
        r = SyncResult(errors=["e1", "e2"])
        assert str(r) == "2 errors"

    def test_str_changes_and_errors(self) -> None:
        r = SyncResult(added=1, errors=["boom"])
        s = str(r)
        assert "1 added" in s
        assert "1 errors" in s


# ---------------------------------------------------------------------------
# TestCheckGio
# ---------------------------------------------------------------------------


class TestCheckGio:
    """Tests for ShortcutManager._check_gio."""

    def test_returns_true_when_gio_available(
        self, mock_gio: mock.MagicMock
    ) -> None:
        mgr = ShortcutManager()
        # gi is in sys.modules via mock_gio fixture
        result = mgr._check_gio()
        assert result is True
        assert mgr._gio_available is True

    def test_returns_false_when_gi_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Make sure gi is not importable
        monkeypatch.setitem(sys.modules, "gi", None)
        mgr = ShortcutManager()
        result = mgr._check_gio()
        assert result is False
        assert mgr._gio_available is False

    def test_caches_result(self, mock_gio: mock.MagicMock) -> None:
        mgr = ShortcutManager()
        mgr._check_gio()
        mgr._check_gio()  # second call should not re-import
        assert mgr._gio_available is True

    def test_cached_false_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "gi", None)
        mgr = ShortcutManager()
        mgr._check_gio()
        assert mgr._gio_available is False
        # call again — should still be False, no exception
        assert mgr._check_gio() is False


class TestRequireGio:
    """Tests for ShortcutManager._require_gio."""

    def test_raises_when_gio_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "gi", None)
        mgr = ShortcutManager()
        with pytest.raises(GioNotAvailableError):
            mgr._require_gio()

    def test_does_not_raise_when_gio_available(
        self, mock_gio: mock.MagicMock
    ) -> None:
        mgr = ShortcutManager()
        mgr._gio_available = True
        mgr._require_gio()  # must not raise


# ---------------------------------------------------------------------------
# TestGetAllCustomShortcuts
# ---------------------------------------------------------------------------


class TestGetAllCustomShortcuts:
    """Tests for ShortcutManager.get_all_custom_shortcuts."""

    def test_returns_empty_when_gio_unavailable(self) -> None:
        mgr = ShortcutManager()
        mgr._gio_available = False
        assert mgr.get_all_custom_shortcuts() == []

    def test_returns_shortcuts_for_each_path(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                },
                {
                    "path": f"{BASE_PATH}/custom1/",
                    "name": "ydoit: Network Setup Script",
                    "command": "ydoit type setnet",
                    "binding": "<Super>F8",
                },
            ],
        )
        shortcuts = mgr.get_all_custom_shortcuts()
        assert len(shortcuts) == 2
        assert shortcuts[0].name == "ydoit: Home Password"
        assert shortcuts[1].binding == "<Super>F8"

    def test_returns_empty_when_no_paths(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(gio, [])
        assert mgr.get_all_custom_shortcuts() == []

    def test_skips_malformed_entry(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        good_path = f"{BASE_PATH}/custom0/"
        bad_path = f"{BASE_PATH}/custom1/"

        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = [good_path, bad_path]

        good_kb = _make_kb_settings("ydoit: Home Password", "ydoit type home1", "<Super>F11")

        bad_kb = mock.MagicMock()
        bad_kb.get_string.side_effect = RuntimeError("dconf exploded")

        def _new_with_path(schema_id: str, path: str) -> mock.MagicMock:
            return good_kb if path == good_path else bad_kb

        gio.Settings.new.return_value = media_keys_mock
        gio.Settings.new_with_path.side_effect = _new_with_path

        shortcuts = mgr.get_all_custom_shortcuts()
        assert len(shortcuts) == 1
        assert shortcuts[0].path == good_path


# ---------------------------------------------------------------------------
# TestGetYdoitAndNonYdoitShortcuts
# ---------------------------------------------------------------------------


class TestGetYdoitAndNonYdoitShortcuts:
    """Tests for get_ydoit_shortcuts / get_non_ydoit_shortcuts filtering."""

    @pytest.fixture()
    def mixed_shortcuts(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> ShortcutManager:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                },
                {
                    "path": f"{BASE_PATH}/custom1/",
                    "name": "Screenshot Tool",
                    "command": "/usr/bin/scrot.sh",
                    "binding": "<Primary>Print",
                },
                {
                    "path": f"{BASE_PATH}/custom2/",
                    "name": "ydoit: Setnet",
                    "command": "ydoit type setnet",
                    "binding": "<Super>F8",
                },
            ],
        )
        return mgr

    def test_get_ydoit_shortcuts(self, mixed_shortcuts: ShortcutManager) -> None:
        result = mixed_shortcuts.get_ydoit_shortcuts()
        assert len(result) == 2
        assert all(s.is_ydoit for s in result)

    def test_get_non_ydoit_shortcuts(self, mixed_shortcuts: ShortcutManager) -> None:
        result = mixed_shortcuts.get_non_ydoit_shortcuts()
        assert len(result) == 1
        assert result[0].name == "Screenshot Tool"


# ---------------------------------------------------------------------------
# TestFindConflict
# ---------------------------------------------------------------------------


class TestFindConflict:
    """Tests for ShortcutManager.find_conflict."""

    def test_no_conflict_returns_none(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                }
            ],
        )
        gio.SettingsSchemaSource.get_default.return_value = None

        result = mgr.find_conflict("Super+F12")
        assert result is None

    def test_conflict_with_custom_shortcut(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "Screenshot Tool",
                    "command": "/usr/bin/scrot.sh",
                    "binding": "<Super>F11",
                }
            ],
        )
        gio.SettingsSchemaSource.get_default.return_value = None

        result = mgr.find_conflict("Super+F11")
        assert result is not None
        assert isinstance(result, ConflictInfo)
        assert result.existing_source == "custom"
        assert result.keycombo == "Super+F11"

    def test_conflict_with_ydoit_shortcut(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                }
            ],
        )
        gio.SettingsSchemaSource.get_default.return_value = None

        result = mgr.find_conflict("Super+F11")
        assert result is not None
        assert result.existing_source == "ydoit"
        assert result.existing_name == "home1"

    def test_exclude_entry_skips_own_shortcut(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                }
            ],
        )
        gio.SettingsSchemaSource.get_default.return_value = None

        # Checking if "home1" conflicts with itself — should be excluded
        result = mgr.find_conflict("Super+F11", exclude_entry="home1")
        assert result is None

    def test_exclude_entry_does_not_skip_other_shortcuts(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                }
            ],
        )
        gio.SettingsSchemaSource.get_default.return_value = None

        # Excluding "setnet", but home1 still holds <Super>F11 — conflict
        result = mgr.find_conflict("Super+F11", exclude_entry="setnet")
        assert result is not None

    def test_case_insensitive_binding_comparison(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<SUPER>f11",  # unusual casing stored in dconf
                }
            ],
        )
        gio.SettingsSchemaSource.get_default.return_value = None

        result = mgr.find_conflict("Super+F11")
        assert result is not None

    def test_conflict_with_builtin_shortcut(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio

        # Set up schema source with one built-in schema that has the binding
        schema_source = mock.MagicMock()
        schema = mock.MagicMock()
        schema.list_keys.return_value = ["switch-windows"]

        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = []  # no custom shortcuts

        builtin_settings = mock.MagicMock()
        builtin_settings.get_strv.return_value = ["<Alt>Tab"]

        # Both _get_media_keys_settings and the builtin schema settings call
        # Gio.Settings.new — the media-keys call uses the MEDIA_KEYS_SCHEMA,
        # builtin schemas use their own ids.  Use side_effect to distinguish.
        from ydoit import constants

        def _new(schema_id: str) -> mock.MagicMock:
            if schema_id == constants.MEDIA_KEYS_SCHEMA:
                return media_keys_mock
            return builtin_settings

        gio.Settings.new.side_effect = _new
        gio.Settings.new_with_path.return_value = mock.MagicMock()
        gio.SettingsSchemaSource.get_default.return_value = schema_source
        schema_source.lookup.return_value = schema

        result = mgr.find_conflict("Alt+Tab")
        assert result is not None
        assert result.existing_source == "builtin"
        assert result.existing_path is None

    def test_builtin_check_skips_none_schema(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio


        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = []
        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.return_value = mock.MagicMock()

        schema_source = mock.MagicMock()
        # lookup returns None for all schemas → no conflict
        schema_source.lookup.return_value = None
        gio.SettingsSchemaSource.get_default.return_value = schema_source

        result = mgr.find_conflict("Alt+Tab")
        assert result is None

    def test_builtin_check_handles_key_exception(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio

        from ydoit import constants

        schema_source = mock.MagicMock()
        schema = mock.MagicMock()
        schema.list_keys.return_value = ["bad-key"]

        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = []

        bad_settings = mock.MagicMock()
        bad_settings.get_strv.side_effect = RuntimeError("no such key")

        def _new(schema_id: str) -> mock.MagicMock:
            if schema_id == constants.MEDIA_KEYS_SCHEMA:
                return media_keys_mock
            return bad_settings

        gio.Settings.new.side_effect = _new
        gio.Settings.new_with_path.return_value = mock.MagicMock()
        gio.SettingsSchemaSource.get_default.return_value = schema_source
        schema_source.lookup.return_value = schema

        # Should not raise; exception is swallowed and no conflict reported
        result = mgr.find_conflict("Alt+Tab")
        assert result is None

    def test_returns_none_when_gio_unavailable_for_builtins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "gi", None)
        mgr = ShortcutManager()
        # _check_gio returns False → get_all_custom_shortcuts returns []
        # _check_builtin_conflict also returns None immediately
        result = mgr.find_conflict("Super+F11")
        assert result is None


# ---------------------------------------------------------------------------
# TestRegisterShortcut
# ---------------------------------------------------------------------------


class TestRegisterShortcut:
    """Tests for ShortcutManager.register_shortcut."""

    def test_does_nothing_when_gio_unavailable(self) -> None:
        mgr = ShortcutManager()
        mgr._gio_available = False
        entry = make_entry()
        mgr.register_shortcut(entry)  # must not raise

    def test_does_nothing_when_keycombo_empty(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(gio, [])
        entry = make_entry(keycombo="")
        mgr.register_shortcut(entry)
        gio.Settings.new.assert_not_called()

    def test_updates_existing_shortcut(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        existing_path = f"{BASE_PATH}/custom0/"


        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = [existing_path]

        # The read mock for the initial scan and the write mock for the update
        # both hit new_with_path(schema, existing_path).
        # We use a call counter so that the first call returns readable data
        # and the second call returns a writable mock.
        read_kb = _make_kb_settings("ydoit: Home Password", "ydoit type home1", "<Super>F11")
        write_kb = mock.MagicMock()
        call_count = {"n": 0}

        def _new_with_path(schema_id: str, path: str) -> mock.MagicMock:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return read_kb
            return write_kb

        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.side_effect = _new_with_path

        entry = make_entry(name="home1", keycombo="Super+F12", label="Home Password")
        mgr.register_shortcut(entry)

        write_kb.set_string.assert_any_call("binding", "<Super>F12")

    def test_registers_new_shortcut(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio


        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = []  # no existing shortcuts

        new_kb = mock.MagicMock()
        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.return_value = new_kb

        entry = make_entry(name="home1", keycombo="Super+F11", label="Home Password")
        mgr.register_shortcut(entry)

        new_kb.set_string.assert_any_call("name", "ydoit: Home Password")
        new_kb.set_string.assert_any_call("command", "ydoit type home1")
        new_kb.set_string.assert_any_call("binding", "<Super>F11")
        media_keys_mock.set_strv.assert_called_once()


# ---------------------------------------------------------------------------
# TestUnregisterShortcut
# ---------------------------------------------------------------------------


class TestUnregisterShortcut:
    """Tests for ShortcutManager.unregister_shortcut."""

    def test_does_nothing_when_gio_unavailable(self) -> None:
        mgr = ShortcutManager()
        mgr._gio_available = False
        mgr.unregister_shortcut("home1")  # must not raise

    def test_does_nothing_when_entry_not_found(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(gio, [])
        mgr.unregister_shortcut("ghost_entry")
        gio.Settings.new_with_path.assert_not_called()

    def test_removes_matching_shortcut(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        target_path = f"{BASE_PATH}/custom0/"

        # Wire up the media-keys settings mock with the target path
        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = [target_path]

        # The read on the first scan returns readable data;
        # the write during _remove_shortcut_path also uses the same path.
        read_kb = _make_kb_settings("ydoit: Home Password", "ydoit type home1", "<Super>F11")
        write_kb = mock.MagicMock()
        call_count = {"n": 0}

        def _new_with_path(schema_id: str, path: str) -> mock.MagicMock:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return read_kb
            return write_kb

        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.side_effect = _new_with_path

        mgr.unregister_shortcut("home1")

        write_kb.reset.assert_any_call("name")
        write_kb.reset.assert_any_call("command")
        write_kb.reset.assert_any_call("binding")
        media_keys_mock.set_strv.assert_called_once()


# ---------------------------------------------------------------------------
# TestClearAllYdoitShortcuts
# ---------------------------------------------------------------------------


class TestClearAllYdoitShortcuts:
    """Tests for ShortcutManager.clear_all_ydoit_shortcuts."""

    def test_returns_zero_when_gio_unavailable(self) -> None:
        mgr = ShortcutManager()
        mgr._gio_available = False
        assert mgr.clear_all_ydoit_shortcuts() == 0

    def test_returns_zero_when_no_ydoit_shortcuts(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": f"{BASE_PATH}/custom0/",
                    "name": "Screenshot Tool",
                    "command": "/usr/bin/scrot.sh",
                    "binding": "<Primary>Print",
                }
            ],
        )
        assert mgr.clear_all_ydoit_shortcuts() == 0

    def test_removes_all_ydoit_shortcuts(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        path0 = f"{BASE_PATH}/custom0/"
        path1 = f"{BASE_PATH}/custom1/"
        _setup_gio_shortcuts(
            gio,
            [
                {
                    "path": path0,
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                },
                {
                    "path": path1,
                    "name": "ydoit: Setnet",
                    "command": "ydoit type setnet",
                    "binding": "<Super>F8",
                },
            ],
        )
        media_keys_mock = gio.Settings.new.return_value
        media_keys_mock.get_strv.return_value = [path0, path1]
        kb_mock = mock.MagicMock()
        gio.Settings.new_with_path.return_value = kb_mock

        count = mgr.clear_all_ydoit_shortcuts()
        assert count == 2


# ---------------------------------------------------------------------------
# TestSync
# ---------------------------------------------------------------------------


class TestSync:
    """Tests for ShortcutManager.sync."""

    # ------------------------------------------------------------------
    # Helper: build a fully self-contained Gio mock for sync tests.
    # _setup_gio_shortcuts sets side_effect on Settings.new, so we avoid
    # mixing that helper with return_value overrides here.
    # ------------------------------------------------------------------

    @staticmethod
    def _setup(
        gio: mock.MagicMock,
        shortcuts: list[dict],
    ) -> mock.MagicMock:
        """
        Wire gio for sync tests.

        Returns the media_keys_mock so callers can inspect set_strv calls.
        The initial get_strv on media_keys returns the path list;
        subsequent calls (inside write helpers) also return the same list
        unless overridden by the test.
        """
        paths = [s["path"] for s in shortcuts]

        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = paths

        kb_mocks: dict[str, mock.MagicMock] = {}
        for s in shortcuts:
            kb_mocks[s["path"]] = _make_kb_settings(
                s["name"], s["command"], s["binding"]
            )

        write_kb = mock.MagicMock()

        def _new(schema_id: str) -> mock.MagicMock:
            return media_keys_mock

        def _new_with_path(schema_id: str, path: str) -> mock.MagicMock:
            # Return read-only mock if we have one, else the write mock
            return kb_mocks.get(path, write_kb)

        gio.Settings.new.side_effect = _new
        gio.Settings.new_with_path.side_effect = _new_with_path

        return media_keys_mock

    def test_returns_error_when_gio_unavailable(self) -> None:
        mgr = ShortcutManager()
        mgr._gio_available = False
        config = make_config()
        result = mgr.sync(config)
        assert len(result.errors) > 0
        assert result.total_changes == 0

    def test_adds_new_entries(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        self._setup(gio, [])  # no existing shortcuts

        config = make_config(make_entry("home1", "Super+F11", "Home Password"))
        result = mgr.sync(config)

        assert result.added == 1
        assert result.updated == 0
        assert result.removed == 0
        assert result.errors == []

    def test_removes_stale_entries(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        stale_path = f"{BASE_PATH}/custom0/"
        self._setup(
            gio,
            [
                {
                    "path": stale_path,
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                }
            ],
        )
        # Config is empty — home1 is stale
        config = make_config()
        result = mgr.sync(config)

        assert result.removed == 1
        assert result.added == 0
        assert result.errors == []

    def test_updates_changed_entry(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        existing_path = f"{BASE_PATH}/custom0/"

        # For the update path, new_with_path is called twice with existing_path:
        # once during get_all_custom_shortcuts (read) and once during the update (write).
        # We use a call counter to return a writable mock on the second call.
        read_kb = _make_kb_settings("ydoit: Home Password", "ydoit type home1", "<Super>F11")
        write_kb = mock.MagicMock()
        call_count = {"n": 0}

        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = [existing_path]

        def _new(schema_id: str) -> mock.MagicMock:
            return media_keys_mock

        def _new_with_path(schema_id: str, path: str) -> mock.MagicMock:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return read_kb
            return write_kb

        gio.Settings.new.side_effect = _new
        gio.Settings.new_with_path.side_effect = _new_with_path

        config = make_config(make_entry("home1", "Super+F12", "Home Password"))
        result = mgr.sync(config)

        assert result.updated == 1
        assert result.added == 0
        assert result.removed == 0
        assert result.errors == []
        write_kb.set_string.assert_any_call("binding", "<Super>F12")

    def test_idempotent_no_changes(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        existing_path = f"{BASE_PATH}/custom0/"
        self._setup(
            gio,
            [
                {
                    "path": existing_path,
                    "name": "ydoit: Home Password",
                    "command": "ydoit type home1",
                    "binding": "<Super>F11",
                }
            ],
        )

        config = make_config(make_entry("home1", "Super+F11", "Home Password"))
        result = mgr.sync(config)

        assert result.total_changes == 0
        assert result.errors == []

    def test_skips_entries_with_empty_keycombo(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        self._setup(gio, [])

        config = make_config(make_entry("home1", keycombo="", label="No Shortcut"))
        result = mgr.sync(config)

        assert result.added == 0
        assert result.errors == []

    def test_counts_remove_errors(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        stale_path = f"{BASE_PATH}/custom0/"

        read_kb = _make_kb_settings("ydoit: Home Password", "ydoit type home1", "<Super>F11")
        media_keys_mock = mock.MagicMock()
        # First get_strv returns the path so home1 is found in current map;
        # subsequent calls (inside _remove_shortcut_path) raise an error.
        media_keys_mock.get_strv.side_effect = [
            [stale_path],               # scan: build current map
            RuntimeError("dconf fail"), # _remove_shortcut_path: get current paths
        ]

        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.side_effect = lambda schema_id, path: read_kb

        config = make_config()  # empty — home1 is stale
        result = mgr.sync(config)

        assert len(result.errors) == 1
        assert result.removed == 0

    def test_counts_add_errors(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio

        media_keys_mock = mock.MagicMock()
        # First get_strv returns [] so current map is empty;
        # second call (inside _register_new_shortcut) raises.
        media_keys_mock.get_strv.side_effect = [
            [],                         # scan: no existing shortcuts
            RuntimeError("no space"),   # _register_new_shortcut: get paths
        ]
        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.return_value = mock.MagicMock()

        config = make_config(make_entry("home1", "Super+F11"))
        result = mgr.sync(config)

        assert len(result.errors) == 1
        assert result.added == 0

    def test_counts_update_errors(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        mgr, gio = manager_with_gio
        existing_path = f"{BASE_PATH}/custom0/"

        read_kb = _make_kb_settings("ydoit: Home Password", "ydoit type home1", "<Super>F11")
        media_keys_mock = mock.MagicMock()
        media_keys_mock.get_strv.return_value = [existing_path]

        call_count = {"n": 0}

        def _new_with_path(schema_id: str, path: str) -> mock.MagicMock:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return read_kb
            raise RuntimeError("write failed")

        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.side_effect = _new_with_path

        # Binding changed → triggers update which will fail on the second new_with_path call
        config = make_config(make_entry("home1", "Super+F12", "Home Password"))
        result = mgr.sync(config)

        assert len(result.errors) == 1
        assert result.updated == 0

    def test_next_free_slot_skips_used_indices(
        self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
    ) -> None:
        """When custom0 and custom1 are taken, the new slot should be custom2."""
        mgr, gio = manager_with_gio
        path0 = f"{BASE_PATH}/custom0/"
        path1 = f"{BASE_PATH}/custom1/"

        media_keys_mock = mock.MagicMock()
        # On first get_strv (scan for ydoit shortcuts), return [] so there
        # are no existing ydoit shortcuts.  On the second get_strv (inside
        # _register_new_shortcut), return the two pre-existing non-ydoit paths
        # so the index-allocation logic sees indices 0 and 1 as taken.
        media_keys_mock.get_strv.side_effect = [
            [],             # get_ydoit_shortcuts → empty
            [path0, path1], # _register_new_shortcut → pick index 2
        ]
        new_kb = mock.MagicMock()
        gio.Settings.new.side_effect = lambda schema_id: media_keys_mock
        gio.Settings.new_with_path.return_value = new_kb

        config = make_config(make_entry("newentry", "Super+F5"))
        mgr.sync(config)

        # The set_strv call must include a custom2 path
        call_args = media_keys_mock.set_strv.call_args
        assert call_args is not None
        paths_written = call_args[0][1]
        assert any("custom2" in p for p in paths_written)
