"""Typer — input simulation via ydotool."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ydoit.exceptions import YdoitError, YdotoolError

if TYPE_CHECKING:
    from ydoit.models import Entry, Settings

# Maximum argument length to avoid OS limits. ydotool takes text as an
# argument, so very long strings need to be chunked.
_MAX_CHUNK_SIZE = 4096

# Seconds to wait for the daemon socket to appear after a start attempt.
_DAEMON_START_TIMEOUT = 5.0


class Typer:
    """Simulates keyboard input using ydotool.

    ydotool works by writing to /dev/uinput via the ydotoold daemon.
    It must be running as a systemd user service or standalone.
    """

    def __init__(
        self,
        typing_delay_ms: int = 5,
        hold_delay_ms: int = 5,
    ) -> None:
        self.typing_delay_ms = typing_delay_ms
        self.hold_delay_ms = hold_delay_ms
        self._ydotool_path: str | None = None

    @property
    def ydotool_path(self) -> str:
        """Find the ydotool binary. Cached after first lookup."""
        if self._ydotool_path is None:
            path = shutil.which("ydotool")
            if not path:
                raise YdotoolError(
                    "ydotool is not installed or not found in PATH. "
                    "Install it with: sudo dnf install ydotool  (Fedora) or "
                    "sudo apt install ydotool  (Ubuntu)"
                )
            self._ydotool_path = path
        return self._ydotool_path

    def type_string(self, text: str) -> None:
        """Type a string using ydotool.

        Handles chunking for long strings and ensures the daemon is running.

        Args:
            text: The string to type.

        Raises:
            YdotoolError: If ydotool is not available or the daemon is not running.
        """
        if not text:
            return

        self.ensure_daemon()

        # Chunk long strings to avoid argument length limits
        chunks = [text[i : i + _MAX_CHUNK_SIZE] for i in range(0, len(text), _MAX_CHUNK_SIZE)]
        for chunk in chunks:
            self._run_ydotool_type(chunk)

    def type_file(self, filepath: Path) -> None:
        """Read a file and type its contents.

        Args:
            filepath: Path to the file to read and type.

        Raises:
            YdoitError: If the file does not exist or cannot be read.
            YdotoolError: If ydotool fails.
        """
        path = Path(filepath)
        if not path.is_file():
            raise YdoitError(f"File not found: {path}")

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise YdoitError(f"Cannot read file {path}: {e}") from e

        self.type_string(text)

    def type_entry(self, entry: Entry, default_settings: Settings) -> None:
        """Type an entry, using per-entry delay overrides or defaults.

        Args:
            entry: The entry to type.
            default_settings: Global settings for fallback delays.
        """
        # Apply per-entry overrides
        original_typing = self.typing_delay_ms
        original_hold = self.hold_delay_ms
        try:
            self.typing_delay_ms = (
                entry.typing_delay_ms
                if entry.typing_delay_ms is not None
                else default_settings.typing_delay_ms
            )
            self.hold_delay_ms = (
                entry.hold_delay_ms
                if entry.hold_delay_ms is not None
                else default_settings.hold_delay_ms
            )

            if entry.filename:
                self.type_file(Path(entry.filename))
            else:
                self.type_string(entry.string)
        finally:
            self.typing_delay_ms = original_typing
            self.hold_delay_ms = original_hold

    def _run_ydotool_type(self, text: str) -> None:
        """Execute a single ydotool type command.

        Args:
            text: Text to type (should be within chunk size limits).

        Raises:
            YdotoolError: If the command fails.
        """
        cmd = [
            self.ydotool_path,
            "type",
            "--key-delay", str(self.typing_delay_ms),
            "--key-hold", str(self.hold_delay_ms),
            "--",
            text,
        ]
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
        except subprocess.CalledProcessError as e:
            # ydotool prints connection errors to stdout, not stderr — surface both.
            detail = (e.stderr or "").strip() or (e.stdout or "").strip()
            raise YdotoolError(
                f"ydotool type failed (exit {e.returncode}): {detail}"
                if detail
                else f"ydotool type failed (exit {e.returncode})"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise YdotoolError("ydotool type timed out (>60s)") from e
        except FileNotFoundError as e:
            raise YdotoolError(
                "ydotool binary not found at expected path"
            ) from e

    @staticmethod
    def _candidate_socket_paths() -> list[Path]:
        """Socket paths the ydotool client checks, in order."""
        paths: list[Path] = []
        env_path = os.environ.get("YDOTOOL_SOCKET")
        if env_path:
            paths.append(Path(env_path))
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime:
            paths.append(Path(runtime) / ".ydotool_socket")
        paths.append(Path("/tmp/.ydotool_socket"))
        return paths

    @classmethod
    def daemon_socket(cls) -> Path | None:
        """Return the first connectable ydotoold socket, or None.

        ydotoold uses an AF_UNIX SOCK_DGRAM socket; older builds may have
        used SOCK_STREAM, so we try both before giving up.
        """
        for path in cls._candidate_socket_paths():
            if not path.exists():
                continue
            for sock_type in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
                try:
                    with socket.socket(socket.AF_UNIX, sock_type) as s:
                        s.settimeout(0.5)
                        s.connect(str(path))
                    return path
                except OSError:
                    continue
        return None

    @classmethod
    def check_daemon(cls) -> bool:
        """Check if ydotoold is reachable via its socket.

        Returns:
            True if a connectable ydotoold socket is found.
        """
        return cls.daemon_socket() is not None

    @classmethod
    def ensure_daemon(cls, timeout: float = _DAEMON_START_TIMEOUT) -> None:
        """Make sure ydotoold is reachable, attempting to start it if not.

        Tries `systemctl --user start ydotoold` and polls for the socket.

        Raises:
            YdotoolError: If the daemon cannot be started or reached.
        """
        if cls.check_daemon():
            return

        try:
            subprocess.run(
                ["systemctl", "--user", "start", "ydotoold.service"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass  # fall through to the final probe below

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cls.check_daemon():
                return
            time.sleep(0.1)

        raise YdotoolError(
            "ydotoold is not running and could not be started automatically.\n"
            "Try: systemctl --user start ydotoold\n"
            "Or check the unit:  systemctl --user status ydotoold"
        )

    @staticmethod
    def check_permissions() -> bool:
        """Check if the current user can write to /dev/uinput.

        Returns:
            True if /dev/uinput is accessible.
        """
        uinput = Path("/dev/uinput")
        if not uinput.exists():
            return False
        try:
            return uinput.stat().st_mode & 0o222 != 0
        except OSError:
            return False
