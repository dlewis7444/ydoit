"""Modal dialogs — shortcut recorder, passphrase change, confirmations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GObject, Gtk

if TYPE_CHECKING:
    from ydoit.state import AppState

# Map Gdk modifier flags to user-facing names
_GDK_MOD_MAP = {
    Gdk.ModifierType.CONTROL_MASK: "Ctrl",
    Gdk.ModifierType.ALT_MASK: "Alt",
    Gdk.ModifierType.SHIFT_MASK: "Shift",
    Gdk.ModifierType.SUPER_MASK: "Super",
}


class ShortcutRecorderDialog(Adw.Dialog):
    """Modal dialog that captures a keyboard shortcut.

    Emits 'shortcut-recorded' with the keycombo string when the user
    presses a valid key combination (modifier + key).
    """

    __gsignals__ = {
        "shortcut-recorded": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(
        self,
        state: AppState,
        exclude_entry: str | None = None,
    ) -> None:
        super().__init__(
            title="Record Shortcut",
            content_width=400,
            content_height=250,
        )
        self._state = state
        self._exclude_entry = exclude_entry
        self._recorded_combo = ""

        self._build_ui()

    def _build_ui(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        self._status_label = Gtk.Label(
            label="Press a key combination...",
            wrap=True,
        )
        self._status_label.add_css_class("title-3")
        box.append(self._status_label)

        self._combo_label = Gtk.Label(label="")
        self._combo_label.add_css_class("title-1")
        box.append(self._combo_label)

        self._conflict_label = Gtk.Label(label="", wrap=True, visible=False)
        self._conflict_label.add_css_class("error")
        box.append(self._conflict_label)

        # Buttons
        btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
        )

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", self._on_clear)
        btn_box.append(clear_btn)

        self._accept_btn = Gtk.Button(label="Accept", sensitive=False)
        self._accept_btn.add_css_class("suggested-action")
        self._accept_btn.connect("clicked", self._on_accept)
        btn_box.append(self._accept_btn)

        box.append(btn_box)

        # Make box focusable to receive key events
        box.set_focusable(True)
        self._focus_box = box

        # Key controller on the box
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        box.add_controller(key_ctrl)

        self.set_child(box)

    def do_map(self) -> None:
        """Grab focus after the dialog is mapped to screen."""
        if hasattr(Adw.Dialog, "do_map"):
            Adw.Dialog.do_map(self)
        else:
            super().do_map()
        self._focus_box.grab_focus()

    def _on_key_pressed(
        self,
        controller: Gtk.EventControllerKey,
        keyval: int,
        keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        # Ignore bare modifier presses
        if keyval in (
            Gdk.KEY_Shift_L,
            Gdk.KEY_Shift_R,
            Gdk.KEY_Control_L,
            Gdk.KEY_Control_R,
            Gdk.KEY_Alt_L,
            Gdk.KEY_Alt_R,
            Gdk.KEY_Super_L,
            Gdk.KEY_Super_R,
            Gdk.KEY_Meta_L,
            Gdk.KEY_Meta_R,
        ):
            return True

        # Escape cancels
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True

        # Build the keycombo string
        parts = []
        for mask, name in _GDK_MOD_MAP.items():
            if state & mask:
                parts.append(name)

        # Need at least one modifier for a valid shortcut
        if not parts:
            self._status_label.set_text("Press a modifier + key combination")
            return True

        key_name = Gdk.keyval_name(keyval)
        if key_name is None:
            return True

        # Normalize: capitalize single chars, keep F-keys as-is
        if len(key_name) == 1:
            key_name = key_name.upper()
        elif key_name.startswith("F") and key_name[1:].isdigit():
            pass  # Already correct
        else:
            # Capitalize first letter for display
            key_name = key_name.capitalize()

        parts.append(key_name)
        combo = "+".join(parts)

        self._recorded_combo = combo
        self._combo_label.set_text(combo)
        self._accept_btn.set_sensitive(True)

        # Check for conflicts
        conflict = self._state.find_shortcut_conflict(
            combo, exclude_entry=self._exclude_entry
        )
        if conflict:
            self._conflict_label.set_text(
                f"Conflicts with {conflict.existing_source} shortcut "
                f"'{conflict.existing_name}'"
            )
            self._conflict_label.set_visible(True)
        else:
            self._conflict_label.set_visible(False)

        return True

    def _on_clear(self, _btn: Gtk.Button) -> None:
        self._recorded_combo = ""
        self.emit("shortcut-recorded", "")
        self.close()

    def _on_accept(self, _btn: Gtk.Button) -> None:
        if self._recorded_combo:
            self.emit("shortcut-recorded", self._recorded_combo)
        self.close()


class ChangePassphraseDialog(Adw.Dialog):
    """Dialog for changing the GPG passphrase."""

    def __init__(self, state: AppState) -> None:
        super().__init__(
            title="Change Passphrase",
            content_width=400,
            content_height=300,
        )
        self._state = state
        self._build_ui()

    def _build_ui(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        group = Adw.PreferencesGroup()

        self._old_row = Adw.PasswordEntryRow(title="Current Passphrase")
        group.add(self._old_row)

        self._new_row = Adw.PasswordEntryRow(title="New Passphrase")
        group.add(self._new_row)

        self._confirm_row = Adw.PasswordEntryRow(title="Confirm New Passphrase")
        group.add(self._confirm_row)

        box.append(group)

        self._error_label = Gtk.Label(visible=False, wrap=True)
        self._error_label.add_css_class("error")
        box.append(self._error_label)

        btn_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            halign=Gtk.Align.END,
        )

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        btn_box.append(cancel_btn)

        save_btn = Gtk.Button(label="Change")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_change)
        btn_box.append(save_btn)

        box.append(btn_box)
        self.set_child(box)

    def _on_change(self, _btn: Gtk.Button) -> None:
        old_pass = self._old_row.get_text()
        new_pass = self._new_row.get_text()
        confirm_pass = self._confirm_row.get_text()

        if not old_pass or not new_pass:
            self._show_error("All fields are required")
            return

        if new_pass != confirm_pass:
            self._show_error("New passphrases do not match")
            return

        try:
            self._state.change_passphrase(old_pass, new_pass)
            self.close()
        except Exception as e:
            self._show_error(str(e))

    def _show_error(self, msg: str) -> None:
        self._error_label.set_text(msg)
        self._error_label.set_visible(True)


def confirm_delete(
    window: Adw.ApplicationWindow,
    entry_name: str,
    on_confirm: object,
) -> None:
    """Show a confirmation dialog before deleting an entry."""
    dialog = Adw.AlertDialog(
        heading="Delete Entry?",
        body=f"Are you sure you want to delete '{entry_name}'? "
        "This will also remove its keyboard shortcut.",
    )
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("delete", "Delete")
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.set_default_response("cancel")
    dialog.set_close_response("cancel")

    def on_response(dialog: Adw.AlertDialog, response: str) -> None:
        if response == "delete":
            on_confirm()

    dialog.connect("response", on_response)
    dialog.present(window)
