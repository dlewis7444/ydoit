"""GTK4/libadwaita GUI entry point for ydoit."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from ydoit import constants
from ydoit.config_manager import ConfigManager
from ydoit.exceptions import DecryptionError, GioNotAvailableError
from ydoit.keyring_manager import KeyringManager
from ydoit.models import Config
from ydoit.shortcut_manager import ShortcutManager, SyncResult


def _format_sync_failure(result: SyncResult) -> str:
    """Build a human-readable explanation of why a sync failed."""
    lines: list[str] = []
    if result.conflicts:
        lines.append(
            "No GNOME shortcuts were changed because of these conflicts:"
            if len(result.conflicts) > 1
            else "No GNOME shortcuts were changed because of this conflict:"
        )
        for c in result.conflicts:
            lines.append("")
            lines.append(
                f"  • {c.our_label!r} (in '{c.our_category}') wants "
                f"{c.our_keycombo}, which is already bound to "
                f"{c.conflict.existing_name!r} ({c.existing_source_label()})."
            )
        lines.append("")
        lines.append("To fix:")
        lines.append(
            "  – Open GNOME Settings → Keyboard and remove or change the existing binding, or"
        )
        lines.append("  – Edit the entry in ydoit and pick a different shortcut.")
    if result.errors:
        if lines:
            lines.append("")
        lines.append("Other errors:")
        for err in result.errors:
            lines.append(f"  • {err}")
    return "\n".join(lines)


class YdoitApp(Adw.Application):
    """Main GTK application for ydoit."""

    def __init__(self) -> None:
        super().__init__(application_id=constants.APP_ID)
        self._cm = ConfigManager()
        self._km = KeyringManager()
        self._sm = ShortcutManager()
        self._config: Config | None = None
        self._passphrase: str | None = None
        self._gio_available = True

    # --- Activation ---

    def do_activate(self) -> None:
        win = self.get_active_window()
        if win:
            win.present()
            return
        from ydoit.window import MainWindow

        self._main_window = MainWindow(application=self)
        self._main_window.present()
        self._begin_auth()

    # --- Auth flow ---

    def _begin_auth(self) -> None:
        if not self._cm.exists():
            self._config = Config()
            self._main_window.load_config(self._config)
            return

        passphrase = self._km.retrieve_passphrase(timeout_min=0)
        if passphrase:
            self._do_load(passphrase)
        else:
            self._prompt_passphrase()

    def _prompt_passphrase(self, error: str | None = None) -> None:
        from ydoit.passphrase_dialog import PassphraseDialog

        dlg = PassphraseDialog(error_message=error)
        dlg.choose(self._main_window, None, self._on_auth_response)

    def _on_auth_response(self, dlg: object, result: object) -> None:
        from ydoit.passphrase_dialog import PassphraseDialog

        assert isinstance(dlg, PassphraseDialog)
        response = dlg.choose_finish(result)
        if response == "cancel":
            self.quit()
            return
        self._do_load(dlg.passphrase)

    def _do_load(self, passphrase: str) -> None:
        try:
            self._config = self._cm.load(passphrase)
            self._passphrase = passphrase
            s = self._config.settings
            if not s.use_keyring_cache:
                self._km.clear_passphrase()
            elif s.keyring_timeout_min > 0 and self._km.is_expired(s.keyring_timeout_min):
                self._km.clear_passphrase()
            else:
                self._km.store_passphrase(passphrase)
            if not self._sm._check_gio():
                self._gio_available = False
                self._main_window.show_toast(
                    "Shortcut sync unavailable — install python3-gobject"
                )
            self._main_window.load_config(self._config)
        except DecryptionError as e:
            self._prompt_passphrase(error=f"Wrong passphrase: {e}")

    # --- Config persistence ---

    def save_config(self) -> SyncResult | None:
        """Save config and sync shortcuts. Call this after any mutation.

        Returns the SyncResult if a sync was attempted, or None if skipped
        (no config, no passphrase, or Gio unavailable). Callers can check
        ``result.success`` before showing success UI.
        """
        if self._config is None or self._passphrase is None:
            return None
        self._cm.save(self._config, passphrase=self._passphrase)
        if not self._gio_available:
            return None
        try:
            result = self._sm.sync(self._config)
        except GioNotAvailableError:
            self._gio_available = False
            return None
        if not result.success:
            self._main_window.show_alert(
                "Shortcut sync failed",
                _format_sync_failure(result),
            )
        return result

    def update_passphrase(self, new_passphrase: str) -> None:
        """Update stored passphrase (called after change_passphrase)."""
        self._passphrase = new_passphrase
        if self._config and self._config.settings.use_keyring_cache:
            self._km.store_passphrase(new_passphrase)

    # --- Properties ---

    @property
    def config(self) -> Config:
        assert self._config is not None
        return self._config

    @property
    def cm(self) -> ConfigManager:
        return self._cm

    @property
    def passphrase(self) -> str | None:
        return self._passphrase


def main() -> None:
    """Launch the ydoit GUI application."""
    app = YdoitApp()
    app.run(None)
