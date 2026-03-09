"""Config manager — GPG encryption, loading, saving, and migration."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from ydoit import constants
from ydoit.exceptions import (
    ConfigDirError,
    DecryptionError,
    EncryptionError,
    GpgNotFoundError,
)
from ydoit.migration import detect_version, migrate_v1_to_v2
from ydoit.models import Config

# Type alias for passphrase provider callback
PassphraseProvider = Callable[[], str]


class ConfigManager:
    """Manages the encrypted ydoit config file.

    Handles:
    - GPG symmetric encrypt/decrypt (AES-256)
    - Atomic file writes (write to .tmp then rename)
    - v1 → v2 migration with backup
    - File and directory permission enforcement
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        passphrase_provider: PassphraseProvider | None = None,
    ) -> None:
        self.config_dir = config_dir or constants.CONFIG_DIR
        self.data_file = self.config_dir / "data.json.gpg"
        self._passphrase_provider = passphrase_provider
        self._gpg_path: str | None = None

    @property
    def gpg_path(self) -> str:
        """Find the gpg binary. Cached after first lookup."""
        if self._gpg_path is None:
            path = shutil.which("gpg2") or shutil.which("gpg")
            if not path:
                raise GpgNotFoundError()
            self._gpg_path = path
        return self._gpg_path

    def exists(self) -> bool:
        """Check if the encrypted data file exists."""
        return self.data_file.is_file()

    def load(self, passphrase: str | None = None) -> Config:
        """Decrypt and load the config.

        If no config file exists, returns an empty Config.
        If the file is v1 format, migrates to v2 automatically (with backup).

        Args:
            passphrase: GPG passphrase. If None, uses the passphrase_provider.

        Returns:
            Loaded (and possibly migrated) Config.

        Raises:
            DecryptionError: Wrong passphrase or corrupt file.
            GpgNotFoundError: GPG not installed.
        """
        if not self.exists():
            return Config()

        if passphrase is None:
            passphrase = self._get_passphrase()

        plaintext = self._decrypt(passphrase)
        raw = json.loads(plaintext)

        version = detect_version(raw)
        if version == 1:
            self._backup()
            raw = migrate_v1_to_v2(raw)
            config = Config.from_dict(raw)
            self.save(config, passphrase)
            return config

        return Config.from_dict(raw)

    def save(self, config: Config, passphrase: str | None = None) -> None:
        """Encrypt and save the config atomically.

        Args:
            config: Config to save.
            passphrase: GPG passphrase. If None, uses the passphrase_provider.

        Raises:
            EncryptionError: GPG encryption failed.
            ConfigDirError: Cannot create config directory.
        """
        if passphrase is None:
            passphrase = self._get_passphrase()

        self._ensure_dir()
        plaintext = config.to_json()

        # Atomic write: encrypt to .tmp, then rename
        tmp_file = self.data_file.with_suffix(".gpg.tmp")
        try:
            self._encrypt(plaintext, passphrase, output_file=tmp_file)
            tmp_file.rename(self.data_file)
        except Exception:
            # Clean up temp file on failure
            tmp_file.unlink(missing_ok=True)
            raise
        finally:
            self._enforce_permissions()

    def change_passphrase(self, old_passphrase: str, new_passphrase: str) -> None:
        """Re-encrypt the config file with a new passphrase.

        Args:
            old_passphrase: Current GPG passphrase (used to decrypt).
            new_passphrase: New GPG passphrase (used to re-encrypt).

        Raises:
            DecryptionError: old_passphrase is wrong or file is corrupt.
            EncryptionError: Re-encryption failed.
        """
        config = self.load(passphrase=old_passphrase)
        self.save(config, passphrase=new_passphrase)

    def _decrypt(self, passphrase: str) -> str:
        """Decrypt the data file using GPG.

        Args:
            passphrase: GPG passphrase.

        Returns:
            Decrypted plaintext JSON string.

        Raises:
            DecryptionError: Decryption failed.
        """
        cmd = [
            self.gpg_path,
            "--batch",
            "--yes",
            "--quiet",
            "--pinentry-mode", "loopback",
            "--passphrase-fd", "0",
            "--decrypt",
            str(self.data_file),
        ]
        try:
            result = subprocess.run(
                cmd,
                input=passphrase,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise DecryptionError(
                f"Failed to decrypt {self.data_file}: {e.stderr.strip()}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise DecryptionError("GPG decryption timed out") from e

    def _encrypt(
        self,
        plaintext: str,
        passphrase: str,
        output_file: Path | None = None,
    ) -> None:
        """Encrypt plaintext to a file using GPG symmetric AES-256.

        Uses a temporary file for plaintext input so the passphrase
        (which may contain newlines or special characters) is cleanly
        separated from the data on stdin.

        Args:
            plaintext: Data to encrypt.
            passphrase: GPG passphrase.
            output_file: Where to write. Defaults to self.data_file.

        Raises:
            EncryptionError: Encryption failed.
        """
        import tempfile

        target = output_file or self.data_file

        # Write plaintext to a temp file so stdin is used only for the passphrase.
        # This avoids issues when the passphrase contains newlines.
        tmp_input = None
        try:
            tmp_input = tempfile.NamedTemporaryFile(  # noqa: SIM115
                mode="w",
                suffix=".json",
                dir=self.config_dir if self.config_dir.exists() else None,
                delete=False,
                encoding="utf-8",
            )
            tmp_input.write(plaintext)
            tmp_input.close()
            os.chmod(tmp_input.name, 0o600)

            cmd = [
                self.gpg_path,
                "--batch",
                "--yes",
                "--quiet",
                "--pinentry-mode", "loopback",
                "--passphrase-fd", "0",
                "--symmetric",
                "--cipher-algo", "AES256",
                "--output", str(target),
                tmp_input.name,
            ]
            subprocess.run(
                cmd,
                input=passphrase,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        except subprocess.CalledProcessError as e:
            raise EncryptionError(
                f"Failed to encrypt to {target}: {e.stderr.strip()}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise EncryptionError("GPG encryption timed out") from e
        finally:
            if tmp_input is not None:
                Path(tmp_input.name).unlink(missing_ok=True)

    def _ensure_dir(self) -> None:
        """Create the config directory with correct permissions if needed."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ConfigDirError(f"Cannot create config directory {self.config_dir}: {e}") from e
        with contextlib.suppress(OSError):
            os.chmod(self.config_dir, 0o700)  # Best-effort — skip if we don't own the directory

    def _enforce_permissions(self) -> None:
        """Ensure the config dir and data file have restrictive permissions."""
        try:
            if self.config_dir.exists():
                os.chmod(self.config_dir, 0o700)
            if self.data_file.exists():
                os.chmod(self.data_file, 0o600)
        except OSError:
            pass  # Best-effort

    def _backup(self) -> None:
        """Create a backup of the current data file before migration."""
        backup_path = self.data_file.with_name(
            self.data_file.name + constants.BACKUP_SUFFIX
        )
        if self.data_file.exists():
            shutil.copy2(self.data_file, backup_path)

    def _get_passphrase(self) -> str:
        """Get passphrase from the provider callback."""
        if self._passphrase_provider is None:
            raise DecryptionError("No passphrase provided and no passphrase_provider configured")
        return self._passphrase_provider()

    def lock_for_write(self) -> _ConfigFileLock:
        """Acquire an exclusive lock for writing. Use as a context manager."""
        return _ConfigFileLock(self.config_dir / ".lock")


class _ConfigFileLock:
    """File-based exclusive lock to prevent concurrent config writes."""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fd: int | None = None

    def __enter__(self) -> _ConfigFileLock:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            os.close(self._fd)
            self._fd = None
            raise TimeoutError(
                "Another ydoit process is writing to the config file"
            ) from e
        return self

    def __exit__(self, *args: object) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
