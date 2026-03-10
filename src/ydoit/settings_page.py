"""Settings page."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk


class SettingsPage(Adw.NavigationPage):
    """Global settings form."""

    __gsignals__ = {
        "settings-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(title="Settings")
        self._populating = False
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        header = Adw.HeaderBar()
        prefs = Adw.PreferencesPage()

        # Typing defaults
        defaults = Adw.PreferencesGroup(title="Typing Defaults")
        self._typing_delay = Adw.SpinRow.new_with_range(0, 1000, 1)
        self._typing_delay.set_title("Typing delay (ms)")
        self._typing_delay.connect("notify::value", self._on_changed)
        self._hold_delay = Adw.SpinRow.new_with_range(0, 1000, 1)
        self._hold_delay.set_title("Hold delay (ms)")
        self._hold_delay.connect("notify::value", self._on_changed)
        defaults.add(self._typing_delay)
        defaults.add(self._hold_delay)
        prefs.add(defaults)

        # Security
        security = Adw.PreferencesGroup(title="Security")
        self._keyring_switch = Adw.SwitchRow(title="Cache passphrase in keyring")
        self._keyring_switch.connect("notify::active", self._on_changed)
        self._keyring_timeout = Adw.SpinRow.new_with_range(0, 1440, 1)
        self._keyring_timeout.set_title("Cache timeout (min, 0 = session only)")
        self._keyring_timeout.connect("notify::value", self._on_changed)
        change_pass_row = Adw.ActionRow(title="Change GPG Passphrase")
        change_pass_row.set_activatable(True)
        change_pass_row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        change_pass_row.connect("activated", self._on_change_passphrase)
        security.add(self._keyring_switch)
        security.add(self._keyring_timeout)
        security.add(change_pass_row)
        prefs.add(security)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(prefs)
        self.set_child(toolbar_view)

    def _populate(self) -> None:
        from ydoit import constants

        self._populating = True
        try:
            app = Gtk.Application.get_default()

            if app is None:
                self._typing_delay.set_value(constants.DEFAULT_TYPING_DELAY_MS)
                self._hold_delay.set_value(constants.DEFAULT_HOLD_DELAY_MS)
                self._keyring_switch.set_active(True)
                self._keyring_timeout.set_value(constants.DEFAULT_KEYRING_TIMEOUT_MIN)
                return

            s = app.config.settings
            self._typing_delay.set_value(s.typing_delay_ms)
            self._hold_delay.set_value(s.hold_delay_ms)
            self._keyring_switch.set_active(s.use_keyring_cache)
            self._keyring_timeout.set_value(s.keyring_timeout_min)
        finally:
            self._populating = False

    def _on_changed(self, *args: object) -> None:
        if self._populating:
            return
        app = Gtk.Application.get_default()
        if app is None:
            return
        s = app.config.settings
        s.typing_delay_ms = int(self._typing_delay.get_value())
        s.hold_delay_ms = int(self._hold_delay.get_value())
        s.use_keyring_cache = self._keyring_switch.get_active()
        s.keyring_timeout_min = int(self._keyring_timeout.get_value())
        self.emit("settings-changed")

    def _on_change_passphrase(self, *args: object) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_spacing(6)
        current_row = Adw.PasswordEntryRow(title="Current passphrase")
        new_row = Adw.PasswordEntryRow(title="New passphrase")
        box.append(current_row)
        box.append(new_row)

        dlg = Adw.AlertDialog(heading="Change Passphrase")
        dlg.set_extra_child(box)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("change", "Change")
        dlg.set_response_appearance("change", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("change")
        dlg.set_close_response("cancel")

        def _on_response(d: object, r: object) -> None:
            if d.choose_finish(r) != "change":
                return
            old_pass = current_row.get_text()
            new_pass = new_row.get_text()
            if not new_pass:
                return
            app = Gtk.Application.get_default()
            if app is None:
                return
            from ydoit.exceptions import DecryptionError, EncryptionError

            try:
                app.cm.change_passphrase(old_pass, new_pass)
                app.update_passphrase(new_pass)
                self.get_root().show_toast("Passphrase changed")
            except (DecryptionError, EncryptionError) as e:
                err_dlg = Adw.AlertDialog(heading="Error", body=str(e))
                err_dlg.add_response("ok", "OK")
                err_dlg.choose(self.get_root(), None, lambda d2, r2: None)

        dlg.choose(self.get_root(), None, _on_response)
