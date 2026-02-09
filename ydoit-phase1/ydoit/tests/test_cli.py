"""Tests for ydoit.cli."""

from __future__ import annotations

import pytest

from ydoit.cli import build_parser, main


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
        assert args.name == "home1"

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
        assert args.name == "myentry"
        assert args.keycombo == "Super+F5"
        assert args.string == "hello"
        assert args.label == "My Entry"
        assert args.category == "passwords"

    def test_add_requires_keycombo(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["add", "myentry"])

    def test_remove_subcommand(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["remove", "myentry", "--yes"])
        assert args.command == "remove"
        assert args.name == "myentry"
        assert args.yes is True

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


class TestMainEntryPoint:
    """Tests for the main() dispatch."""

    def test_no_args_returns_ok(self) -> None:
        """No subcommand prints help and returns 0."""
        result = main([])
        assert result == 0

    def test_version_subcommand(self, capsys: pytest.CaptureFixture) -> None:
        result = main(["version"])
        assert result == 0
        captured = capsys.readouterr()
        assert "ydoit" in captured.out
        assert "2.0.0" in captured.out
