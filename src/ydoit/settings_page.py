"""Settings page."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from ydoit import __version__, constants
from ydoit.typer import Typer

# Combo order must match VALID backends mapping below.
_BACKEND_LABELS = [
    "Auto (recommended)",
    "Mutter (GNOME / Remote Desktop)",
    "ydotool",
]
_BACKEND_VALUES = [
    constants.INPUT_BACKEND_AUTO,
    constants.INPUT_BACKEND_MUTTER,
    constants.INPUT_BACKEND_YDOTOOL,
]


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

        self._input_backend = Adw.ComboRow(title="Input backend")
        self._input_backend.set_model(Gtk.StringList.new(_BACKEND_LABELS))
        self._input_backend.set_subtitle(
            "Local seat → ydotool; GNOME RDP-style remote → Mutter"
        )
        self._input_backend.connect("notify::selected", self._on_backend_changed)

        defaults.add(self._typing_delay)
        defaults.add(self._hold_delay)
        defaults.add(self._input_backend)
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

        # About
        about = Adw.PreferencesGroup(title="About")
        version_row = Adw.ActionRow(title="Version")
        version_row.set_subtitle(__version__)
        about.add(version_row)
        prefs.add(about)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(prefs)
        self.set_child(toolbar_view)

    def _populate(self) -> None:
        self._populating = True
        try:
            app = Gtk.Application.get_default()

            if app is None:
                self._typing_delay.set_value(constants.DEFAULT_TYPING_DELAY_MS)
                self._hold_delay.set_value(constants.DEFAULT_HOLD_DELAY_MS)
                self._keyring_switch.set_active(True)
                self._keyring_timeout.set_value(constants.DEFAULT_KEYRING_TIMEOUT_MIN)
                self._input_backend.set_selected(
                    _BACKEND_VALUES.index(constants.DEFAULT_INPUT_BACKEND)
                )
                return

            s = app.config.settings
            self._typing_delay.set_value(s.typing_delay_ms)
            self._hold_delay.set_value(s.hold_delay_ms)
            self._keyring_switch.set_active(s.use_keyring_cache)
            self._keyring_timeout.set_value(s.keyring_timeout_min)
            backend = s.input_backend
            if backend not in _BACKEND_VALUES:
                backend = constants.DEFAULT_INPUT_BACKEND
            self._input_backend.set_selected(_BACKEND_VALUES.index(backend))
            self._update_backend_subtitle(backend)
        finally:
            self._populating = False

    def _selected_backend(self) -> str:
        idx = self._input_backend.get_selected()
        if 0 <= idx < len(_BACKEND_VALUES):
            return _BACKEND_VALUES[idx]
        return constants.DEFAULT_INPUT_BACKEND

    def _update_backend_subtitle(self, backend: str) -> None:
        base = "Local seat → ydotool; GNOME RDP-style remote → Mutter"
        if backend == constants.INPUT_BACKEND_AUTO:
            self._input_backend.set_subtitle(base)
            return
        if backend == constants.INPUT_BACKEND_MUTTER:
            if Typer._mutter_available():
                self._input_backend.set_subtitle("Mutter RemoteDesktop available here")
            else:
                self._input_backend.set_subtitle(
                    "Mutter not available in this session — typing will fail until "
                    "you are on GNOME with RemoteDesktop (e.g. GNOME RDP)"
                )
            return
        # ydotool
        parts: list[str] = []
        if not Typer.ydotool_binary_available():
            parts.append("ydotool binary not found")
        if not Typer.check_daemon():
            parts.append("ydotoold not running")
        if parts:
            self._input_backend.set_subtitle(
                "; ".join(parts) + " — still saved for multi-machine configs"
            )
        else:
            self._input_backend.set_subtitle("ydotool/ydotoold ready on this machine")

    def _on_backend_changed(self, *args: object) -> None:
        if self._populating:
            return
        backend = self._selected_backend()
        self._update_backend_subtitle(backend)
        self._on_changed()

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
        s.input_backend = self._selected_backend()
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
