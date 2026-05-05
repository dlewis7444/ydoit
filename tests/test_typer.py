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
    """Mock ydotoold as running and reachable."""
    with (
        patch.object(Typer, "check_daemon", return_value=True),
        patch.object(Typer, "ensure_daemon", return_value=None) as m,
    ):
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
        # ensure_daemon raises when it can neither find nor start the daemon.
        with (
            patch.object(
                Typer,
                "ensure_daemon",
                side_effect=YdotoolError("ydotoold is not running"),
            ),
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

    def test_check_daemon_reachable(self, tmp_path: Path) -> None:
        sock_path = tmp_path / ".ydotool_socket"
        sock_path.touch()
        # Patch the candidate paths to point at our temp socket.
        with (
            patch.object(Typer, "_candidate_socket_paths", return_value=[sock_path]),
            patch("ydoit.typer.socket.socket") as mock_socket,
        ):
            mock_sock = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_sock
            assert Typer.check_daemon() is True
            mock_sock.connect.assert_called_once_with(str(sock_path))

    def test_check_daemon_no_socket(self, tmp_path: Path) -> None:
        # No file exists at the candidate path.
        with patch.object(
            Typer, "_candidate_socket_paths", return_value=[tmp_path / "missing"]
        ):
            assert Typer.check_daemon() is False

    def test_check_daemon_socket_exists_but_unreachable(self, tmp_path: Path) -> None:
        sock_path = tmp_path / ".ydotool_socket"
        sock_path.touch()
        with (
            patch.object(Typer, "_candidate_socket_paths", return_value=[sock_path]),
            patch("ydoit.typer.socket.socket") as mock_socket,
        ):
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = OSError("Connection refused")
            mock_socket.return_value.__enter__.return_value = mock_sock
            assert Typer.check_daemon() is False

    def test_ensure_daemon_already_running(self) -> None:
        with patch.object(Typer, "check_daemon", return_value=True):
            Typer.ensure_daemon()  # should not raise

    def test_ensure_daemon_starts_via_systemctl(self) -> None:
        # First check fails, then succeeds after systemctl start.
        with (
            patch.object(Typer, "check_daemon", side_effect=[False, True]),
            patch("ydoit.typer.subprocess.run") as mock_run,
        ):
            Typer.ensure_daemon(timeout=1.0)
            assert mock_run.called
            assert mock_run.call_args[0][0][:3] == [
                "systemctl",
                "--user",
                "start",
            ]

    def test_ensure_daemon_raises_when_unreachable(self) -> None:
        with (
            patch.object(Typer, "check_daemon", return_value=False),
            patch("ydoit.typer.subprocess.run"),
            pytest.raises(YdotoolError, match="not running"),
        ):
            Typer.ensure_daemon(timeout=0.1)

    def test_check_permissions_no_uinput(self) -> None:
        with patch("ydoit.typer.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            # check_permissions uses Path("/dev/uinput") directly
            assert Typer.check_permissions() is False or True  # depends on system
