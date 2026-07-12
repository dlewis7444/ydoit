"""Typer — input simulation via Mutter RemoteDesktop or ydotool."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ydoit import constants
from ydoit.exceptions import YdoitError, YdotoolError

if TYPE_CHECKING:
    from ydoit.models import Entry, Settings

# Maximum argument length to avoid OS limits. ydotool takes text as an
# argument, so very long strings need to be chunked.
_MAX_CHUNK_SIZE = 4096

# Seconds to wait for the daemon socket to appear after a start attempt.
_DAEMON_START_TIMEOUT = 5.0

# X11 keysyms for control characters
_XK_RETURN = 0xFF0D
_XK_TAB = 0xFF09
_XK_BACKSPACE = 0xFF08


def _char_to_keysym(ch: str) -> int:
    """Map a single Unicode character to an X11 keysym.

    Latin-1 (U+0000..U+00FF) maps 1:1 to keysyms. Other planes use the
    standard Unicode keysym base 0x01000000 + codepoint.
    """
    if ch == "\n" or ch == "\r":
        return _XK_RETURN
    if ch == "\t":
        return _XK_TAB
    if ch == "\b":
        return _XK_BACKSPACE
    code = ord(ch)
    if code < 0x100:
        return code
    return 0x01000000 + code


def _expand_ydotool_escapes(text: str) -> str:
    """Expand backslash escapes the way ``ydotool type`` does by default.

    ydotool enables ``--escape`` for command-line strings, so stored values
    like ``secret\\n`` become Enter after the last character. The Mutter
    backend must do the same or users see a literal ``\\n``.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n:
            esc = text[i + 1]
            if esc == "n":
                out.append("\n")
                i += 2
                continue
            if esc == "r":
                out.append("\r")
                i += 2
                continue
            if esc == "t":
                out.append("\t")
                i += 2
                continue
            if esc == "b":
                out.append("\b")
                i += 2
                continue
            if esc == "\\":
                out.append("\\")
                i += 2
                continue
            # Unknown escape: keep both chars (same as many type tools)
            out.append(text[i])
            out.append(esc)
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


class Typer:
    """Simulates keyboard input.

    Backends:
    - **mutter** — GNOME Mutter RemoteDesktop D-Bus (works inside
      gnome-remote-desktop sessions where uinput is orphaned).
    - **ydotool** — ydotoold + /dev/uinput (local physical seat).
    - **auto** — remote-like session + Mutter → mutter; else ydotool;
      else mutter last resort.
    """

    def __init__(
        self,
        typing_delay_ms: int = 5,
        hold_delay_ms: int = 5,
        backend: str | None = None,
    ) -> None:
        self.typing_delay_ms = typing_delay_ms
        self.hold_delay_ms = hold_delay_ms
        # Explicit backend (CLI --backend or forced tests). None → settings/env/auto.
        self._requested_backend = backend
        self._ydotool_path: str | None = None

    # --- Backend resolution ---

    def configured_backend(self, settings: Settings | None = None) -> str:
        """Backend the user asked for (before auto resolution).

        Priority: constructor override → YDOIT_INPUT_BACKEND → settings → auto.
        """
        if self._requested_backend is not None:
            return self._normalize_backend(self._requested_backend)
        env = os.environ.get(constants.INPUT_BACKEND_ENV, "").strip()
        if env:
            return self._normalize_backend(env)
        if settings is not None and getattr(settings, "input_backend", None):
            return self._normalize_backend(settings.input_backend)
        return constants.DEFAULT_INPUT_BACKEND

    @staticmethod
    def _normalize_backend(value: str) -> str:
        if value in constants.VALID_INPUT_BACKENDS:
            return value
        return constants.DEFAULT_INPUT_BACKEND

    def effective_backend(self, settings: Settings | None = None) -> str:
        """Resolve configured backend to the concrete backend that would run."""
        return self._select_backend(settings)

    def _select_backend(self, settings: Settings | None = None) -> str:
        requested = self.configured_backend(settings)

        if requested == constants.INPUT_BACKEND_MUTTER:
            if not self._mutter_available():
                raise YdotoolError(
                    "Mutter RemoteDesktop is not available in this session. "
                    "It requires GNOME/Mutter with org.gnome.Mutter.RemoteDesktop "
                    "on the session bus (typical of GNOME Remote Desktop sessions)."
                )
            return constants.INPUT_BACKEND_MUTTER

        if requested == constants.INPUT_BACKEND_YDOTOOL:
            return constants.INPUT_BACKEND_YDOTOOL

        # auto
        if self._session_looks_remote() and self._mutter_available():
            return constants.INPUT_BACKEND_MUTTER
        if self.check_daemon():
            return constants.INPUT_BACKEND_YDOTOOL
        if self._mutter_available():
            return constants.INPUT_BACKEND_MUTTER
        raise YdotoolError(
            "No input backend available. On a normal GNOME seat, start "
            "ydotoold: systemctl --user start ydotoold. On a "
            "gnome-remote-desktop session, set input backend to Mutter "
            "(or Auto) and ensure org.gnome.Mutter.RemoteDesktop is available."
        )

    @staticmethod
    def _mutter_available() -> bool:
        try:
            import dbus  # type: ignore

            bus = dbus.SessionBus()
            bus.get_object(
                "org.gnome.Mutter.RemoteDesktop",
                "/org/gnome/Mutter/RemoteDesktop",
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _session_looks_remote() -> bool:
        """Best-effort: is this a remote/RDP-style session?

        Primary signal: loginctl show-session $XDG_SESSION_ID -p Remote=yes.
        Also honors YDOIT_SESSION_REMOTE=1 for tests and odd environments.
        """
        env_flag = os.environ.get("YDOIT_SESSION_REMOTE", "").strip().lower()
        if env_flag in ("1", "true", "yes"):
            return True
        if env_flag in ("0", "false", "no"):
            return False

        session_id = os.environ.get("XDG_SESSION_ID", "").strip()
        if not session_id:
            return False
        try:
            result = subprocess.run(
                ["loginctl", "show-session", session_id, "-p", "Remote", "--value"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip().lower() in ("yes", "true", "1")
        except Exception:
            pass

        # Fallback without --value (older loginctl)
        try:
            result = subprocess.run(
                ["loginctl", "show-session", session_id, "-p", "Remote"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Remote="):
                        return line.split("=", 1)[1].strip().lower() in (
                            "yes",
                            "true",
                            "1",
                        )
        except Exception:
            pass
        return False

    @staticmethod
    def ydotool_binary_available() -> bool:
        """True if ydotool is on PATH."""
        return shutil.which("ydotool") is not None

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

    def type_string(
        self, text: str, settings: Settings | None = None
    ) -> None:
        """Type a string using the configured/effective backend.

        Args:
            text: The string to type.
            settings: Optional settings for backend resolution.

        Raises:
            YdotoolError: If no backend can type the text.
        """
        if not text:
            return

        backend = self._select_backend(settings)
        if backend == constants.INPUT_BACKEND_MUTTER:
            # Match ydotool CLI default: expand \n \t \r \\ etc.
            self._type_string_mutter(_expand_ydotool_escapes(text))
            return

        # ydotool path — ensure daemon (start if needed), then type.
        self.ensure_daemon()

        chunks = [
            text[i : i + _MAX_CHUNK_SIZE]
            for i in range(0, len(text), _MAX_CHUNK_SIZE)
        ]
        for chunk in chunks:
            self._run_ydotool_type(chunk)

    def type_file(
        self, filepath: Path, settings: Settings | None = None
    ) -> None:
        """Read a file and type its contents.

        Args:
            filepath: Path to the file to read and type.
            settings: Optional settings for backend resolution.

        Raises:
            YdoitError: If the file does not exist or cannot be read.
            YdotoolError: If typing fails.
        """
        path = Path(filepath)
        if not path.is_file():
            raise YdoitError(f"File not found: {path}")

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise YdoitError(f"Cannot read file {path}: {e}") from e

        self.type_string(text, settings=settings)

    def type_entry(self, entry: Entry, default_settings: Settings) -> None:
        """Type an entry, using per-entry delay overrides or defaults.

        Args:
            entry: The entry to type.
            default_settings: Global settings for fallback delays and backend.
        """
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
                self.type_file(Path(entry.filename), settings=default_settings)
            else:
                self.type_string(entry.string, settings=default_settings)
        finally:
            self.typing_delay_ms = original_typing
            self.hold_delay_ms = original_hold

    # --- Mutter RemoteDesktop backend ---

    def _type_string_mutter(self, text: str) -> None:
        """Type via org.gnome.Mutter.RemoteDesktop session D-Bus API.

        This is the path that works inside gnome-remote-desktop sessions:
        uinput/ydotool is orphaned there (exit 0, no visible keys).
        """
        try:
            import dbus  # type: ignore
        except ImportError as e:
            raise YdotoolError(
                "python3-dbus required for Mutter RemoteDesktop typing backend"
            ) from e

        try:
            bus = dbus.SessionBus()
            rd = bus.get_object(
                "org.gnome.Mutter.RemoteDesktop",
                "/org/gnome/Mutter/RemoteDesktop",
            )
            rd_iface = dbus.Interface(rd, "org.gnome.Mutter.RemoteDesktop")
            path = rd_iface.CreateSession()
            sess = bus.get_object("org.gnome.Mutter.RemoteDesktop", path)
            siface = dbus.Interface(
                sess, "org.gnome.Mutter.RemoteDesktop.Session"
            )
            siface.Start()
        except Exception as e:
            raise YdotoolError(
                f"Mutter RemoteDesktop session failed to start: {e}"
            ) from e

        delay_s = max(self.typing_delay_ms, 0) / 1000.0
        hold_s = max(self.hold_delay_ms, 0) / 1000.0

        try:
            for ch in text:
                keysym = _char_to_keysym(ch)
                siface.NotifyKeyboardKeysym(dbus.UInt32(keysym), True)
                if hold_s:
                    time.sleep(hold_s)
                siface.NotifyKeyboardKeysym(dbus.UInt32(keysym), False)
                if delay_s:
                    time.sleep(delay_s)
        except Exception as e:
            raise YdotoolError(
                f"Mutter RemoteDesktop key injection failed: {e}"
            ) from e
        finally:
            try:
                siface.Stop()
            except Exception:
                pass

    # --- ydotool backend ---

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
            "--key-delay",
            str(self.typing_delay_ms),
            "--key-hold",
            str(self.hold_delay_ms),
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

    @staticmethod
    def backend_status(
        settings: Settings | None = None,
        requested_backend: str | None = None,
    ) -> str:
        """Human-readable backend availability for `ydoit status`."""
        mutter = Typer._mutter_available()
        ydo = Typer.check_daemon()
        remote = Typer._session_looks_remote()
        parts = [
            f"mutter: {'yes' if mutter else 'no'}",
            f"ydotoold: {'running' if ydo else 'not running'}",
            f"session remote: {'yes' if remote else 'no'}",
        ]
        try:
            typer = Typer(backend=requested_backend)
            configured = typer.configured_backend(settings)
            effective = typer.effective_backend(settings)
            parts.insert(0, f"configured: {configured}")
            parts.insert(1, f"effective: {effective}")
        except YdotoolError:
            if settings is not None or requested_backend is not None:
                typer = Typer(backend=requested_backend)
                configured = typer.configured_backend(settings)
                parts.insert(0, f"configured: {configured}")
                parts.insert(1, "effective: none")
            else:
                parts.insert(0, "effective: none")
        return "; ".join(parts)
