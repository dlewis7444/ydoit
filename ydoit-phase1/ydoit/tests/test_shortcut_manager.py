"""Tests for ydoit.shortcut_manager."""

from __future__ import annotations

import pytest

from ydoit.shortcut_manager import GnomeShortcut, ShortcutManager, SyncResult


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
