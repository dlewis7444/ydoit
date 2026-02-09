"""Settings page — global preferences and maintenance."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from ydoit import __version__

if TYPE_CHECKING:
    from ydoit.state import AppState
    from ydoit.window import YdoitWindow


class SettingsPage(Adw.NavigationPage):
    """Global settings: delays, keyring, passphrase change, export."""

    def __init__(self, state: AppState, window: YdoitWindow, **kwargs: object) -> None:
        super().__init__(title="Settings", **kwargs)
        self._state = state
        self._window = window

        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        header = Adw.HeaderBar()

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=600)

        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page_box.set_margin_top(24)
        page_box.set_margin_bottom(24)
        page_box.set_margin_start(12)
        page_box.set_margin_end(12)

        # --- Typing delays ---
        delay_group = Adw.PreferencesGroup(
            title="Typing Delays",
            description="Global defaults for typing simulation speed",
        )

        self._typing_delay_row = Adw.ActionRow(title="Typing Delay (ms)")
        self._typing_delay_spin = Gtk.SpinButton.new_with_range(1, 500, 1)
        self._typing_delay_spin.set_valign(Gtk.Align.CENTER)
        self._typing_delay_spin.connect("value-changed", self._on_delay_changed)
        self._typing_delay_row.add_suffix(self._typing_delay_spin)
        delay_group.add(self._typing_delay_row)

        self._hold_delay_row = Adw.ActionRow(title="Hold Delay (ms)")
        self._hold_delay_spin = Gtk.SpinButton.new_with_range(1, 500, 1)
        self._hold_delay_spin.set_valign(Gtk.Align.CENTER)
        self._hold_delay_spin.connect("value-changed", self._on_delay_changed)
        self._hold_delay_row.add_suffix(self._hold_delay_spin)
        delay_group.add(self._hold_delay_row)

        page_box.append(delay_group)

        # --- Keyring ---
        keyring_group = Adw.PreferencesGroup(
            title="Keyring Cache",
            description="Cache the passphrase in GNOME Keyring",
        )

        self._keyring_row = Adw.ActionRow(title="Cache Passphrase")
        self._keyring_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._keyring_switch.connect("state-set", self._on_keyring_toggled)
        self._keyring_row.add_suffix(self._keyring_switch)
        self._keyring_row.set_activatable_widget(self._keyring_switch)
        keyring_group.add(self._keyring_row)

        self._timeout_row = Adw.ActionRow(
            title="Cache Timeout (minutes)",
            subtitle="0 = never expire",
        )
        self._timeout_spin = Gtk.SpinButton.new_with_range(0, 1440, 5)
        self._timeout_spin.set_valign(Gtk.Align.CENTER)
        self._timeout_spin.connect("value-changed", self._on_timeout_changed)
        self._timeout_row.add_suffix(self._timeout_spin)
        keyring_group.add(self._timeout_row)

        page_box.append(keyring_group)

        # --- Security ---
        security_group = Adw.PreferencesGroup(title="Security")

        passphrase_row = Adw.ActionRow(
            title="Change Passphrase",
            subtitle="Re-encrypt all data with a new passphrase",
            activatable=True,
        )
        passphrase_row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        passphrase_row.connect("activated", self._on_change_passphrase)
        security_group.add(passphrase_row)

        page_box.append(security_group)

        # --- Shortcuts ---
        shortcuts_group = Adw.PreferencesGroup(title="Shortcuts")

        sync_row = Adw.ActionRow(
            title="Sync GNOME Shortcuts",
            subtitle="Ensure all entries have matching GNOME keybindings",
            activatable=True,
        )
        sync_row.add_suffix(Gtk.Image(icon_name="emblem-synchronizing-symbolic"))
        sync_row.connect("activated", self._on_sync_shortcuts)
        shortcuts_group.add(sync_row)

        page_box.append(shortcuts_group)

        # --- Backup ---
        backup_group = Adw.PreferencesGroup(title="Backup")

        export_row = Adw.ActionRow(
            title="Export Backup",
            subtitle="Save an unencrypted JSON backup",
            activatable=True,
        )
        export_row.add_suffix(Gtk.Image(icon_name="document-save-symbolic"))
        export_row.connect("activated", self._on_export)
        backup_group.add(export_row)

        page_box.append(backup_group)

        # --- About ---
        about_group = Adw.PreferencesGroup()
        about_row = Adw.ActionRow(
            title="ydoit",
            subtitle=f"Version {__version__}",
        )
        about_group.add(about_row)
        page_box.append(about_group)

        clamp.set_child(page_box)
        scroll.set_child(clamp)
        toolbar_view.set_content(scroll)
        self.set_child(toolbar_view)

    def _load_settings(self) -> None:
        settings = self._state.settings
        self._typing_delay_spin.set_value(settings.typing_delay_ms)
        self._hold_delay_spin.set_value(settings.hold_delay_ms)
        self._keyring_switch.set_active(settings.use_keyring_cache)
        self._timeout_spin.set_value(settings.keyring_timeout_min)

    # --- Handlers ---

    def _on_delay_changed(self, _spin: Gtk.SpinButton) -> None:
        self._state.update_settings(
            typing_delay_ms=int(self._typing_delay_spin.get_value()),
            hold_delay_ms=int(self._hold_delay_spin.get_value()),
        )

    def _on_keyring_toggled(self, switch: Gtk.Switch, state: bool) -> bool:
        self._state.update_settings(use_keyring_cache=state)
        return False

    def _on_timeout_changed(self, _spin: Gtk.SpinButton) -> None:
        self._state.update_settings(
            keyring_timeout_min=int(self._timeout_spin.get_value()),
        )

    def _on_change_passphrase(self, _row: Adw.ActionRow) -> None:
        from ydoit.dialogs import ChangePassphraseDialog

        dialog = ChangePassphraseDialog(state=self._state)
        dialog.present(self._window)

    def _on_sync_shortcuts(self, _row: Adw.ActionRow) -> None:
        try:
            self._state.sync_shortcuts()
            self._window.show_toast("Shortcuts synced")
        except Exception as e:
            self._window.show_toast(f"Sync failed: {e}")

    def _on_export(self, _row: Adw.ActionRow) -> None:
        dialog = Gtk.FileDialog(
            title="Export Backup",
            initial_name="ydoit-backup.json",
        )
        dialog.save(self._window, None, self._on_export_response)

    def _on_export_response(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            gfile = dialog.save_finish(result)
        except Exception:
            return
        path_str = gfile.get_path()
        if path_str is None:
            return

        from pathlib import Path

        try:
            count = self._state.export_plain(Path(path_str))
            self._window.show_toast(f"Exported {count} entries")
        except Exception as e:
            self._window.show_toast(f"Export failed: {e}")
