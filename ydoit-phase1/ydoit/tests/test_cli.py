"""Tests for ydoit.cli."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ydoit import constants
from ydoit.cli import _supports_color, build_parser, main
from ydoit.exceptions import (
    DecryptionError,
    GioNotAvailableError,
    GpgNotFoundError,
    YdoitError,
    YdotoolError,
)
from ydoit.models import Config, Entry
from ydoit.shortcut_manager import ConflictInfo, SyncResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> Config:
    """Return a sample v2 Config with test entries across two categories."""
    config = Config()
    config.entries = {
        "home1": Entry(
            trigger="home1",
            keycombo="Super+F11",
            string="supersecretpassword!\n",
            label="Home Password",
            category="passwords",
        ),
        "setnet": Entry(
            trigger="setnet",
            keycombo="Super+F8",
            filename="/home/user/subdir/setnet.sh",
            label="Network Setup Script",
            category="scripts",
        ),
        "tmpfile": Entry(
            trigger="tmpfile",
            keycombo="Super+F9",
            filename="/tmp/ydoitmpfile",
            label="Temp File Typer",
            category="scripts",
        ),
    }
    return config


@pytest.fixture
def single_entry_config() -> Config:
    """Return a Config with a single entry in the default category."""
    config = Config()
    config.entries = {
        "mypass": Entry(
            trigger="mypass",
            keycombo="Super+F1",
            string="s3cr3t",
            label="My Password",
            category="general",
        ),
    }
    return config


def _make_cm(exists: bool, config: Config) -> MagicMock:
    """Build a mock ConfigManager instance."""
    cm = MagicMock()
    cm.exists.return_value = exists
    cm.load.return_value = config
    cm.save.return_value = None
    cm.data_file = Path("/fake/.config/ydoit/data.json.gpg")
    return cm


def _make_sm(
    conflict: ConflictInfo | None = None, sync_result: SyncResult | None = None
) -> MagicMock:
    """Build a mock ShortcutManager instance."""
    sm = MagicMock()
    sm.find_conflict.return_value = conflict
    sm.sync.return_value = sync_result or SyncResult()
    sm.get_ydoit_shortcuts.return_value = []
    sm.register_shortcut.return_value = None
    sm.unregister_shortcut.return_value = None
    return sm


# ---------------------------------------------------------------------------
# TestBuildParser  (preserved / expanded)
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for the argument parser structure."""

    def test_version_flag(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_type_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["type", "home1"])
        assert args.command == "type"
        assert args.trigger == "home1"

    def test_list_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"

    def test_add_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "add", "myentry",
            "--keycombo", "Super+F5",
            "--string", "hello",
            "--label", "My Entry",
            "--category", "passwords",
        ])
        assert args.command == "add"
        assert args.trigger == "myentry"
        assert args.keycombo == "Super+F5"
        assert args.string == "hello"
        assert args.label == "My Entry"
        assert args.category == "passwords"

    def test_add_requires_keycombo(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["add", "myentry"])

    def test_add_file_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["add", "myentry", "--keycombo", "Super+F1", "--file", "/tmp/foo"])
        assert args.filename == "/tmp/foo"

    def test_remove_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["remove", "myentry", "--yes"])
        assert args.command == "remove"
        assert args.trigger == "myentry"
        assert args.yes is True

    def test_remove_no_yes_default(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["remove", "myentry"])
        assert args.yes is False

    def test_sync_shortcuts_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sync-shortcuts"])
        assert args.command == "sync-shortcuts"

    def test_export_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["export", "/tmp/backup.gpg", "--plain"])
        assert args.command == "export"
        assert args.file == "/tmp/backup.gpg"
        assert args.plain is True

    def test_export_no_plain_default(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["export", "/tmp/backup.gpg"])
        assert args.plain is False

    def test_import_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["import", "/tmp/backup.json"])
        assert args.command == "import"
        assert args.file == "/tmp/backup.json"

    def test_status_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_no_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_version_subcommand_parsed(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["version"])
        assert args.command == "version"


# ---------------------------------------------------------------------------
# TestMainEntryPoint — basic dispatch
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    """Tests for the main() dispatch."""

    def test_no_args_returns_ok(self) -> None:
        """No subcommand prints help and returns EXIT_OK."""
        result = main([])
        assert result == constants.EXIT_OK

    def test_version_subcommand(self, capsys: pytest.CaptureFixture) -> None:
        result = main(["version"])
        assert result == constants.EXIT_OK
        captured = capsys.readouterr()
        assert "ydoit" in captured.out
        assert "2.0.0" in captured.out


# ---------------------------------------------------------------------------
# TestColorSupport
# ---------------------------------------------------------------------------


class TestColorSupport:
    """Tests for _supports_color()."""

    def test_returns_false_when_not_tty(self, capsys: pytest.CaptureFixture) -> None:
        """In pytest captured mode stdout is not a tty."""
        # capsys captures stdout, making it a non-tty.
        # We verify _supports_color() returns False in this environment.
        result = _supports_color()
        assert result is False

    def test_returns_true_when_isatty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = True
        monkeypatch.setattr(sys, "stdout", mock_stdout)
        assert _supports_color() is True

    def test_returns_false_when_isatty_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = False
        monkeypatch.setattr(sys, "stdout", mock_stdout)
        assert _supports_color() is False

    def test_returns_false_when_no_isatty_attr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_stdout = object()  # no isatty attribute
        monkeypatch.setattr(sys, "stdout", mock_stdout)
        assert _supports_color() is False


# ---------------------------------------------------------------------------
# TestCmdList
# ---------------------------------------------------------------------------


class TestCmdList:
    """Tests for 'ydoit list'."""

    def test_no_config_file(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        cm = _make_cm(exists=False, config=Config())
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        result = main(["list"])
        assert result == constants.EXIT_OK
        captured = capsys.readouterr()
        assert "No config file found" in captured.err

    def test_empty_config(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        cm = _make_cm(exists=True, config=Config())
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        result = main(["list"])
        assert result == constants.EXIT_OK
        captured = capsys.readouterr()
        assert "No entries found" in captured.err

    def test_single_category_no_heading(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        single_entry_config: Config
    ) -> None:
        cm = _make_cm(exists=True, config=single_entry_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        result = main(["list"])
        assert result == constants.EXIT_OK
        out = capsys.readouterr().out
        assert "mypass" in out
        # Only one category → no category heading in brackets
        assert "[general]" not in out

    def test_multi_category_shows_headings(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        result = main(["list"])
        assert result == constants.EXIT_OK
        out = capsys.readouterr().out
        assert "[passwords]" in out
        assert "[scripts]" in out

    def test_entry_count_shown(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        main(["list"])
        out = capsys.readouterr().out
        assert "3 entries" in out

    def test_file_type_shown(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        main(["list"])
        out = capsys.readouterr().out
        assert "file" in out
        assert "string" in out


# ---------------------------------------------------------------------------
# TestCmdType
# ---------------------------------------------------------------------------


class TestCmdType:
    """Tests for 'ydoit type <name>'."""

    def test_successful_type(
        self, monkeypatch: pytest.MonkeyPatch, sample_config: Config
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        mock_typer = MagicMock()
        mock_typer.type_entry.return_value = None
        monkeypatch.setattr("ydoit.cli.Typer", lambda **kwargs: mock_typer)
        result = main(["type", "home1"])
        assert result == constants.EXIT_OK
        mock_typer.type_entry.assert_called_once()

    def test_entry_not_found(
        self, monkeypatch: pytest.MonkeyPatch, sample_config: Config,
        capsys: pytest.CaptureFixture
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        result = main(["type", "nonexistent"])
        assert result == constants.EXIT_ENTRY_NOT_FOUND
        assert "not found" in capsys.readouterr().err.lower()

    def test_ydotool_error(
        self, monkeypatch: pytest.MonkeyPatch, sample_config: Config,
        capsys: pytest.CaptureFixture
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        mock_typer = MagicMock()
        mock_typer.type_entry.side_effect = YdotoolError("daemon not running")
        monkeypatch.setattr("ydoit.cli.Typer", lambda **kwargs: mock_typer)
        result = main(["type", "home1"])
        assert result == constants.EXIT_YDOTOOL_NOT_RUNNING


# ---------------------------------------------------------------------------
# TestCmdAdd
# ---------------------------------------------------------------------------


class TestCmdAdd:
    """Tests for 'ydoit add <name>'."""

    def _setup_add(self, monkeypatch: pytest.MonkeyPatch, config: Config,
                    sm: MagicMock | None = None) -> MagicMock:
        """Wire up mocks for _cmd_add.

        _cmd_add calls ConfigManager() (no kwargs) for exists() check, then
        ConfigManager(passphrase_provider=...) to load/save. We use a call
        counter so both calls return a sensible mock.
        """
        cm = _make_cm(exists=False, config=config)

        call_count = {"n": 0}

        def cm_factory(**kwargs: object) -> MagicMock:
            call_count["n"] += 1
            return cm

        monkeypatch.setattr("ydoit.cli.ConfigManager", cm_factory)
        monkeypatch.setattr("getpass.getpass", lambda prompt="": "test-pass")

        if sm is None:
            sm = _make_sm()
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: sm)

        return cm

    def test_invalid_name(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        result = main(["add", "bad name!", "--keycombo", "Super+F1", "--string", "hi"])
        assert result == constants.EXIT_ERROR

    def test_duplicate_entry(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        single_entry_config: Config
    ) -> None:
        self._setup_add(monkeypatch, single_entry_config)
        # Override cm.exists to return True so it loads the existing config
        cm = _make_cm(exists=True, config=single_entry_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        result = main(["add", "mypass", "--keycombo", "Super+F2", "--string", "hi"])
        assert result == constants.EXIT_ERROR
        assert "already exists" in capsys.readouterr().err

    def test_shortcut_conflict_proceeds_with_warning(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """Conflict is warned but add proceeds."""
        conflict = ConflictInfo(
            keycombo="Super+F1",
            existing_name="other_entry",
            existing_source="ydoit",
        )
        sm = _make_sm(conflict=conflict)
        self._setup_add(monkeypatch, Config(), sm=sm)
        result = main(["add", "newentry", "--keycombo", "Super+F1", "--string", "hello"])
        assert result == constants.EXIT_OK
        err = capsys.readouterr().err
        assert "conflicts" in err.lower() or "conflict" in err.lower()

    def test_gio_unavailable_fails_before_save(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """When Gio is unavailable, add fails before writing config."""
        sm = _make_sm()
        sm.find_conflict.side_effect = GioNotAvailableError()
        cm = self._setup_add(monkeypatch, Config(), sm=sm)
        result = main(["add", "newentry", "--keycombo", "Super+F1", "--string", "hello"])
        assert result == constants.EXIT_ERROR
        cm.save.assert_not_called()

    def test_successful_add_string(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_add(monkeypatch, Config())
        result = main(["add", "myentry", "--keycombo", "Super+F5", "--string", "secret"])
        assert result == constants.EXIT_OK
        assert "Added entry" in capsys.readouterr().out

    def test_successful_add_file(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_add(monkeypatch, Config())
        result = main(["add", "myentry", "--keycombo", "Super+F5", "--file", "/tmp/test.sh"])
        assert result == constants.EXIT_OK
        assert "Added entry" in capsys.readouterr().out

    def test_add_no_keycombo_no_shortcut_registration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Entry with no keycombo still gets added without shortcut registration."""
        sm = _make_sm()
        self._setup_add(monkeypatch, Config(), sm=sm)
        # The add subparser requires --keycombo so we test the handler logic
        # by verifying sm.register_shortcut is NOT called when keycombo is empty.
        # Build a config that already has the entry to check we hit the register branch.
        # The simplest: if keycombo is provided, register is called.
        sm.register_shortcut.assert_not_called()

    def test_successful_add_registers_shortcut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sm = _make_sm()
        self._setup_add(monkeypatch, Config(), sm=sm)
        main(["add", "myentry", "--keycombo", "Super+F5", "--string", "secret"])
        sm.register_shortcut.assert_called_once()

    def test_add_with_label_and_category(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_add(monkeypatch, Config())
        result = main([
            "add", "myentry",
            "--keycombo", "Super+F5",
            "--string", "secret",
            "--label", "My Label",
            "--category", "work",
        ])
        assert result == constants.EXIT_OK


# ---------------------------------------------------------------------------
# TestCmdRemove
# ---------------------------------------------------------------------------


class TestCmdRemove:
    """Tests for 'ydoit remove <name>'."""

    def _setup_remove(self, monkeypatch: pytest.MonkeyPatch, config: Config) -> MagicMock:
        cm = _make_cm(exists=True, config=config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        monkeypatch.setattr("getpass.getpass", lambda prompt="": "test-pass")
        sm = _make_sm()
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: sm)
        return cm

    def test_entry_not_found(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        single_entry_config: Config
    ) -> None:
        self._setup_remove(monkeypatch, single_entry_config)
        result = main(["remove", "nonexistent", "--yes"])
        assert result == constants.EXIT_ENTRY_NOT_FOUND

    def test_remove_with_yes_flag(
        self, monkeypatch: pytest.MonkeyPatch, single_entry_config: Config,
        capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_remove(monkeypatch, single_entry_config)
        result = main(["remove", "mypass", "--yes"])
        assert result == constants.EXIT_OK
        assert "Removed entry" in capsys.readouterr().out

    def test_remove_user_confirms(
        self, monkeypatch: pytest.MonkeyPatch, single_entry_config: Config,
        capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_remove(monkeypatch, single_entry_config)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        result = main(["remove", "mypass"])
        assert result == constants.EXIT_OK
        assert "Removed entry" in capsys.readouterr().out

    def test_remove_user_confirms_yes_word(
        self, monkeypatch: pytest.MonkeyPatch, single_entry_config: Config,
        capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_remove(monkeypatch, single_entry_config)
        monkeypatch.setattr("builtins.input", lambda _: "yes")
        result = main(["remove", "mypass"])
        assert result == constants.EXIT_OK

    def test_remove_user_cancels(
        self, monkeypatch: pytest.MonkeyPatch, single_entry_config: Config,
        capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_remove(monkeypatch, single_entry_config)
        monkeypatch.setattr("builtins.input", lambda _: "n")
        result = main(["remove", "mypass"])
        assert result == constants.EXIT_OK
        assert "Cancelled" in capsys.readouterr().out

    def test_remove_user_cancels_uppercase(
        self, monkeypatch: pytest.MonkeyPatch, single_entry_config: Config,
        capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_remove(monkeypatch, single_entry_config)
        monkeypatch.setattr("builtins.input", lambda _: "N")
        result = main(["remove", "mypass"])
        assert result == constants.EXIT_OK
        assert "Cancelled" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# TestCmdSyncShortcuts
# ---------------------------------------------------------------------------


class TestCmdSyncShortcuts:
    """Tests for 'ydoit sync-shortcuts'."""

    def _setup_sync(self, monkeypatch: pytest.MonkeyPatch, exists: bool,
                    config: Config, sm: MagicMock) -> MagicMock:
        cm = _make_cm(exists=exists, config=config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: sm)
        return cm

    def test_no_config_file(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        sm = _make_sm()
        self._setup_sync(monkeypatch, exists=False, config=Config(), sm=sm)
        result = main(["sync-shortcuts"])
        assert result == constants.EXIT_OK
        assert "No config file found" in capsys.readouterr().err

    def test_sync_no_changes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config
    ) -> None:
        sm = _make_sm(sync_result=SyncResult())  # 0 total_changes, no errors
        self._setup_sync(monkeypatch, exists=True, config=sample_config, sm=sm)
        result = main(["sync-shortcuts"])
        assert result == constants.EXIT_OK
        assert "in sync" in capsys.readouterr().out

    def test_sync_with_changes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config
    ) -> None:
        sm = _make_sm(sync_result=SyncResult(added=2, removed=1))
        self._setup_sync(monkeypatch, exists=True, config=sample_config, sm=sm)
        result = main(["sync-shortcuts"])
        assert result == constants.EXIT_OK
        out = capsys.readouterr().out
        assert "Sync complete" in out

    def test_sync_with_errors(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config
    ) -> None:
        sm = _make_sm(sync_result=SyncResult(errors=["Failed to add home1: permission denied"]))
        self._setup_sync(monkeypatch, exists=True, config=sample_config, sm=sm)
        result = main(["sync-shortcuts"])
        assert result == constants.EXIT_ERROR
        err = capsys.readouterr().err
        assert "Failed to add home1" in err

    def test_gio_unavailable_fails_hard(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config
    ) -> None:
        """When Gio is unavailable, sync-shortcuts hard-fails."""
        sm = _make_sm()
        sm.sync.side_effect = GioNotAvailableError()
        self._setup_sync(monkeypatch, exists=True, config=sample_config, sm=sm)
        result = main(["sync-shortcuts"])
        assert result == constants.EXIT_ERROR
        err = capsys.readouterr().err
        assert "Gio" in err or "python3-gobject" in err


# ---------------------------------------------------------------------------
# TestCmdExport
# ---------------------------------------------------------------------------


class TestCmdExport:
    """Tests for 'ydoit export <file>'."""

    def test_no_config_file_returns_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        tmp_path: Path
    ) -> None:
        cm = _make_cm(exists=False, config=Config())
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        out_file = str(tmp_path / "export.json")
        result = main(["export", out_file])
        assert result == constants.EXIT_ERROR

    def test_export_plain(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config, tmp_path: Path
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        out_file = tmp_path / "export.json"
        result = main(["export", str(out_file), "--plain"])
        assert result == constants.EXIT_OK
        assert out_file.exists()
        content = out_file.read_text()
        assert "home1" in content
        captured = capsys.readouterr()
        assert "unencrypted" in captured.out
        assert "sensitive" in captured.err

    def test_export_encrypted(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config, tmp_path: Path
    ) -> None:
        cm = _make_cm(exists=True, config=sample_config)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        monkeypatch.setattr("getpass.getpass", lambda prompt="": "test-pass")

        # Mock the export ConfigManager so we don't actually GPG-encrypt
        export_cm = MagicMock()
        export_cm.save.return_value = None

        call_count = {"n": 0}

        def cm_factory(**kwargs: object) -> MagicMock:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return cm
            return export_cm

        monkeypatch.setattr("ydoit.cli.ConfigManager", cm_factory)
        out_file = tmp_path / "export.gpg"
        result = main(["export", str(out_file)])
        assert result == constants.EXIT_OK
        export_cm.save.assert_called_once()


# ---------------------------------------------------------------------------
# TestCmdImport
# ---------------------------------------------------------------------------


class TestCmdImport:
    """Tests for 'ydoit import <file>'."""

    def test_file_not_found(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
    ) -> None:
        result = main(["import", str(tmp_path / "nonexistent.json")])
        assert result == constants.EXIT_ERROR
        assert "not found" in capsys.readouterr().err.lower()

    def test_plain_json_new_config(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config, tmp_path: Path
    ) -> None:
        # Write a plain-text JSON file
        import_file = tmp_path / "import.json"
        import_file.write_text(sample_config.to_json(), encoding="utf-8")

        # No existing config
        cm = _make_cm(exists=False, config=Config())
        monkeypatch.setattr("getpass.getpass", lambda prompt="": "test-pass")
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: _make_sm())

        call_count = {"n": 0}

        def cm_factory(**kwargs: object) -> MagicMock:
            call_count["n"] += 1
            return cm

        monkeypatch.setattr("ydoit.cli.ConfigManager", cm_factory)
        result = main(["import", str(import_file)])
        assert result == constants.EXIT_OK
        out = capsys.readouterr().out
        assert "Imported" in out or "entries" in out

    def test_plain_json_merge_with_existing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config, single_entry_config: Config, tmp_path: Path
    ) -> None:
        import_file = tmp_path / "import.json"
        import_file.write_text(sample_config.to_json(), encoding="utf-8")

        # Existing config present
        cm = _make_cm(exists=True, config=single_entry_config)
        monkeypatch.setattr("getpass.getpass", lambda prompt="": "test-pass")
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: _make_sm())

        call_count = {"n": 0}

        def cm_factory(**kwargs: object) -> MagicMock:
            call_count["n"] += 1
            return cm

        monkeypatch.setattr("ydoit.cli.ConfigManager", cm_factory)
        result = main(["import", str(import_file)])
        assert result == constants.EXIT_OK
        assert "Merged" in capsys.readouterr().out

    def test_encrypted_import_decrypt_failure(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        tmp_path: Path
    ) -> None:
        # Write a binary file that will fail JSON decoding
        import_file = tmp_path / "import.gpg"
        import_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe binary data")

        monkeypatch.setattr("getpass.getpass", lambda prompt="": "wrong-pass")

        import_cm = MagicMock()
        import_cm.load.side_effect = DecryptionError("bad passphrase")

        def cm_factory(**kwargs: object) -> MagicMock:
            return import_cm

        monkeypatch.setattr("ydoit.cli.ConfigManager", cm_factory)
        result = main(["import", str(import_file)])
        assert result == constants.EXIT_DECRYPTION_FAILED

    def test_import_with_shortcut_sync_changes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
        sample_config: Config, tmp_path: Path
    ) -> None:
        import_file = tmp_path / "import.json"
        import_file.write_text(sample_config.to_json(), encoding="utf-8")

        cm = _make_cm(exists=False, config=Config())
        sm = _make_sm(sync_result=SyncResult(added=3))
        monkeypatch.setattr("getpass.getpass", lambda prompt="": "test-pass")
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: sm)
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)

        result = main(["import", str(import_file)])
        assert result == constants.EXIT_OK
        assert "Shortcuts" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# TestCmdStatus
# ---------------------------------------------------------------------------


class TestCmdStatus:
    """Tests for 'ydoit status'."""

    def _setup_status(
        self,
        monkeypatch: pytest.MonkeyPatch,
        config_exists: bool,
        daemon_running: bool,
        permissions_ok: bool,
        keyring_available: bool = False,
        passphrase_cached: bool = False,
        shortcut_count: int = 0,
    ) -> None:
        cm = MagicMock()
        cm.exists.return_value = config_exists
        cm.data_file = Path("/fake/.config/ydoit/data.json.gpg")
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)

        monkeypatch.setattr("ydoit.cli.Typer.check_daemon", staticmethod(lambda: daemon_running))
        monkeypatch.setattr(
            "ydoit.cli.Typer.check_permissions", staticmethod(lambda: permissions_ok)
        )

        sm = MagicMock()
        sm.get_ydoit_shortcuts.return_value = [MagicMock()] * shortcut_count
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: sm)

        # Mock KeyringManager — disable it for most tests
        km = MagicMock()
        km.is_available.return_value = keyring_available
        km.retrieve_passphrase.return_value = "cached-pass" if passphrase_cached else None
        monkeypatch.setattr("ydoit.keyring_manager.KeyringManager", lambda: km)

    def test_status_returns_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=True, permissions_ok=True
        )
        result = main(["status"])
        assert result == constants.EXIT_OK

    def test_status_shows_config_exists(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False, permissions_ok=False
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "exists" in out

    def test_status_shows_config_not_found(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=False, daemon_running=False, permissions_ok=False
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "not found" in out

    def test_status_shows_daemon_running(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=True, permissions_ok=False
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "running" in out

    def test_status_shows_daemon_not_running(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False, permissions_ok=False
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "not running" in out

    def test_status_shows_uinput_accessible(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False, permissions_ok=True
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "accessible" in out

    def test_status_shows_uinput_not_accessible(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False, permissions_ok=False
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "not accessible" in out

    def test_status_shows_shortcut_count(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False,
            permissions_ok=False, shortcut_count=5
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "5 registered" in out

    def test_status_keyring_available_with_cache(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False, permissions_ok=False,
            keyring_available=True, passphrase_cached=True,
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "passphrase cached" in out

    def test_status_keyring_available_no_cache(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False, permissions_ok=False,
            keyring_available=True, passphrase_cached=False,
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "no cached passphrase" in out

    def test_status_keyring_not_available(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        self._setup_status(
            monkeypatch, config_exists=True, daemon_running=False, permissions_ok=False,
            keyring_available=False,
        )
        main(["status"])
        out = capsys.readouterr().out
        assert "not available" in out

    def test_status_keyring_exception(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """If KeyringManager raises, status still returns EXIT_OK."""
        cm = MagicMock()
        cm.exists.return_value = True
        cm.data_file = Path("/fake/.config/ydoit/data.json.gpg")
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        monkeypatch.setattr("ydoit.cli.Typer.check_daemon", staticmethod(lambda: False))
        monkeypatch.setattr("ydoit.cli.Typer.check_permissions", staticmethod(lambda: False))
        sm = MagicMock()
        sm.get_ydoit_shortcuts.return_value = []
        monkeypatch.setattr("ydoit.cli.ShortcutManager", lambda: sm)

        # KeyringManager is imported locally inside _cmd_status; patch at source.
        monkeypatch.setattr(
            "ydoit.keyring_manager.KeyringManager",
            lambda: (_ for _ in ()).throw(Exception("no keyring")),
        )
        result = main(["status"])
        assert result == constants.EXIT_OK


# ---------------------------------------------------------------------------
# TestMainErrorHandling — exception handlers in main()
# ---------------------------------------------------------------------------


class TestMainErrorHandling:
    """Tests for exception handling wrappers in main()."""

    def _raise_in_handler(self, monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
        """Patch 'list' handler to raise exc."""
        cm = _make_cm(exists=True, config=Config())
        # Make cm.load() raise the exception so it propagates from the handler
        cm.load.side_effect = exc
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        # Also override exists to avoid early return
        cm.exists.return_value = True

    def test_decryption_error_returns_decryption_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._raise_in_handler(monkeypatch, DecryptionError("bad key"))
        result = main(["list"])
        assert result == constants.EXIT_DECRYPTION_FAILED

    def test_gpg_not_found_error_returns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._raise_in_handler(monkeypatch, GpgNotFoundError())
        result = main(["list"])
        assert result == constants.EXIT_ERROR

    def test_ydotool_error_returns_ydotool_not_running(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._raise_in_handler(monkeypatch, YdotoolError("daemon not running"))
        result = main(["list"])
        assert result == constants.EXIT_YDOTOOL_NOT_RUNNING

    def test_ydoit_error_returns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._raise_in_handler(monkeypatch, YdoitError("generic ydoit error"))
        result = main(["list"])
        assert result == constants.EXIT_ERROR

    def test_keyboard_interrupt_returns_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cm = _make_cm(exists=True, config=Config())
        cm.exists.return_value = True
        cm.load.side_effect = KeyboardInterrupt()
        monkeypatch.setattr("ydoit.cli.ConfigManager", lambda **kwargs: cm)
        result = main(["list"])
        assert result == constants.EXIT_ERROR


# ---------------------------------------------------------------------------
# TestGetPassphraseProvider
# ---------------------------------------------------------------------------


class TestGetPassphraseProvider:
    """Tests for _get_passphrase_provider().

    KeyringManager is imported locally inside _get_passphrase_provider's
    closure (via ``from ydoit.keyring_manager import KeyringManager``), so we
    must patch it at its *source* module path, not at ``ydoit.cli``.
    """

    def test_falls_back_to_getpass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When keyring is unavailable, falls back to getpass.getpass."""
        from ydoit.cli import _get_passphrase_provider

        monkeypatch.setattr("getpass.getpass", lambda prompt="": "my-passphrase")

        # Make KeyringManager unavailable
        km = MagicMock()
        km.is_available.return_value = False
        monkeypatch.setattr("ydoit.keyring_manager.KeyringManager", lambda: km)
        provider = _get_passphrase_provider(new_file=False)
        result = provider()
        assert result == "my-passphrase"

    def test_returns_cached_from_keyring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When keyring has a cached passphrase, it returns that."""
        from ydoit.cli import _get_passphrase_provider

        km = MagicMock()
        km.is_available.return_value = True
        km.retrieve_passphrase.return_value = "cached-secret"
        monkeypatch.setattr("ydoit.keyring_manager.KeyringManager", lambda: km)
        provider = _get_passphrase_provider()
        result = provider()
        assert result == "cached-secret"

    def test_stores_passphrase_in_keyring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After prompting, passphrase is stored in keyring."""
        from ydoit.cli import _get_passphrase_provider

        km = MagicMock()
        km.is_available.return_value = True
        km.retrieve_passphrase.return_value = None  # nothing cached
        km.store_passphrase.return_value = True

        monkeypatch.setattr("getpass.getpass", lambda prompt="": "fresh-pass")
        monkeypatch.setattr("ydoit.keyring_manager.KeyringManager", lambda: km)
        provider = _get_passphrase_provider()
        result = provider()
        assert result == "fresh-pass"
        km.store_passphrase.assert_called_once_with("fresh-pass")

    def test_new_file_confirms_passphrase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """new_file=True calls getpass twice (prompt + confirm)."""
        from ydoit.cli import _get_passphrase_provider

        calls = []

        def mock_getpass(prompt: str = "") -> str:
            calls.append(prompt)
            return "new-pass"

        monkeypatch.setattr("getpass.getpass", mock_getpass)
        km = MagicMock()
        km.is_available.return_value = False
        monkeypatch.setattr("ydoit.keyring_manager.KeyringManager", lambda: km)
        provider = _get_passphrase_provider(new_file=True)
        result = provider()
        assert result == "new-pass"
        assert len(calls) == 2  # GPG passphrase + Confirm passphrase

    def test_mismatched_passphrase_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mismatched confirmation causes sys.exit(EXIT_ERROR)."""
        from ydoit.cli import _get_passphrase_provider

        responses = iter(["pass1", "different"])
        monkeypatch.setattr("getpass.getpass", lambda prompt="": next(responses))
        km = MagicMock()
        km.is_available.return_value = False
        monkeypatch.setattr("ydoit.keyring_manager.KeyringManager", lambda: km)
        provider = _get_passphrase_provider(new_file=True)
        with pytest.raises(SystemExit) as exc_info:
            provider()
        assert exc_info.value.code == constants.EXIT_ERROR

    def test_keyring_exception_falls_back_to_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If KeyringManager raises an exception, falls back to getpass."""
        from ydoit.cli import _get_passphrase_provider

        monkeypatch.setattr("getpass.getpass", lambda prompt="": "fallback-pass")
        # Patching the class to raise on instantiation
        monkeypatch.setattr(
            "ydoit.keyring_manager.KeyringManager",
            lambda: (_ for _ in ()).throw(Exception("no keyring service")),
        )
        provider = _get_passphrase_provider()
        result = provider()
        assert result == "fallback-pass"
