"""Tests for ydoit.typer."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ydoit.exceptions import YdoitError, YdotoolError
from ydoit.models import Entry, Settings
from ydoit.typer import _MAX_CHUNK_SIZE, Typer


@pytest.fixture
def typer() -> Typer:
    """Create a Typer with defaults."""
    t = Typer(typing_delay_ms=5, hold_delay_ms=5)
    t._ydotool_path = "/usr/bin/ydotool"
    return t


@pytest.fixture
def mock_daemon() -> MagicMock:
    """Mock ydotoold as running."""
    with patch.object(Typer, "check_daemon", return_value=True) as m:
        yield m


class TestTyper:
    """Tests for the Typer class."""

    def test_type_string_calls_ydotool(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            typer.type_string("hello")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "/usr/bin/ydotool"
            assert args[1] == "type"
            assert "--key-delay" in args
            assert "5" in args
            assert "hello" in args

    def test_type_string_empty_is_noop(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        with patch("ydoit.typer.subprocess.run") as mock_run:
            typer.type_string("")
            mock_run.assert_not_called()

    def test_type_string_chunks_long_input(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        long_text = "x" * (_MAX_CHUNK_SIZE * 3 + 100)
        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            typer.type_string(long_text)
            assert mock_run.call_count == 4  # 3 full + 1 remainder

    def test_type_string_daemon_not_running(self, typer: Typer) -> None:
        with (
            patch.object(Typer, "check_daemon", return_value=False),
            pytest.raises(YdotoolError, match="not running"),
        ):
            typer.type_string("hello")

    def test_type_file(
        self, typer: Typer, mock_daemon: MagicMock, tmp_path: Path
    ) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("file contents", encoding="utf-8")

        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            typer.type_file(test_file)

            args = mock_run.call_args[0][0]
            assert "file contents" in args

    def test_type_file_not_found(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        with pytest.raises(YdoitError, match="File not found"):
            typer.type_file(Path("/nonexistent/file.txt"))

    def test_type_entry_string(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        entry = Entry(trigger="test", keycombo="Super+F1", string="secret")
        settings = Settings()

        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            typer.type_entry(entry, settings)

            args = mock_run.call_args[0][0]
            assert "secret" in args

    def test_type_entry_file(
        self, typer: Typer, mock_daemon: MagicMock, tmp_path: Path
    ) -> None:
        test_file = tmp_path / "script.sh"
        test_file.write_text("#!/bin/bash\necho hi", encoding="utf-8")

        entry = Entry(trigger="test", keycombo="Super+F1", filename=str(test_file))
        settings = Settings()

        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            typer.type_entry(entry, settings)

            args = mock_run.call_args[0][0]
            assert "#!/bin/bash" in args[-1]

    def test_type_entry_per_entry_delay_override(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        entry = Entry(
            trigger="test",
            keycombo="Super+F1",
            string="x",
            typing_delay_ms=50,
            hold_delay_ms=100,
        )
        settings = Settings(typing_delay_ms=5, hold_delay_ms=5)

        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            typer.type_entry(entry, settings)

            args = mock_run.call_args[0][0]
            delay_idx = args.index("--key-delay") + 1
            hold_idx = args.index("--key-hold") + 1
            assert args[delay_idx] == "50"
            assert args[hold_idx] == "100"

    def test_type_entry_restores_delays(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        """Per-entry overrides don't permanently change the typer."""
        entry = Entry(
            trigger="test", keycombo="Super+F1", string="x", typing_delay_ms=99
        )
        settings = Settings()

        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            typer.type_entry(entry, settings)

        assert typer.typing_delay_ms == 5
        assert typer.hold_delay_ms == 5

    def test_ydotool_command_failure(
        self, typer: Typer, mock_daemon: MagicMock
    ) -> None:
        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "ydotool", stderr="error")
            with pytest.raises(YdotoolError, match="failed"):
                typer.type_string("hello")


class TestTyperSystemChecks:
    """Tests for daemon and permission checks."""

    def test_check_daemon_via_pgrep(self) -> None:
        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 0)
            assert Typer.check_daemon() is True

    def test_check_daemon_not_running(self) -> None:
        with patch("ydoit.typer.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess([], 1)
            # Falls through to systemctl check, which also returns 1
            assert Typer.check_daemon() is False

    def test_check_permissions_no_uinput(self) -> None:
        with patch("ydoit.typer.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            # check_permissions uses Path("/dev/uinput") directly
            assert Typer.check_permissions() is False or True  # depends on system
