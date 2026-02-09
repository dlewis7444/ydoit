"""Main application window with lock/unlock states."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ydoit import constants
from ydoit.exceptions import DecryptionError
from ydoit.state import AppState


class YdoitWindow(Adw.ApplicationWindow):
    """Main window that manages locked/unlocked states.

    Starts in locked state with a passphrase prompt. On successful unlock,
    switches to the main NavigationView with entry list.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(
            default_width=constants.DEFAULT_WINDOW_WIDTH,
            default_height=constants.DEFAULT_WINDOW_HEIGHT,
            title="ydoit",
            **kwargs,
        )
        self._state = AppState()
        self._toast_overlay = Adw.ToastOverlay()
        self._nav_view = Adw.NavigationView()

        # Build the UI structure
        self._build_lock_screen()
        self.set_content(self._toast_overlay)
        self._toast_overlay.set_child(self._lock_page)

        # Try keyring auto-unlock
        if self._state.try_keyring_unlock():
            self._on_unlocked()

    # --- Lock screen ---

    def _build_lock_screen(self) -> None:
        self._lock_page = Adw.StatusPage(
            icon_name="dialog-password-symbolic",
            title="ydoit",
            description="Enter your passphrase to unlock",
        )

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_size_request(300, -1)

        self._passphrase_entry = Gtk.PasswordEntry(
            placeholder_text="GPG Passphrase",
            show_peek_icon=True,
        )
        self._passphrase_entry.connect("activate", self._on_unlock_activate)
        box.append(self._passphrase_entry)

        # Show "Create new" or "Unlock" depending on whether config exists
        if self._state.config_exists:
            btn_label = "Unlock"
        else:
            btn_label = "Create New Config"
            self._lock_page.set_description(
                "No config found. Enter a passphrase to create one."
            )

        unlock_btn = Gtk.Button(label=btn_label)
        unlock_btn.add_css_class("suggested-action")
        unlock_btn.add_css_class("pill")
        unlock_btn.connect("clicked", self._on_unlock_activate)
        box.append(unlock_btn)

        self._lock_error_label = Gtk.Label(visible=False)
        self._lock_error_label.add_css_class("error")
        box.append(self._lock_error_label)

        self._lock_page.set_child(box)

    def _on_unlock_activate(self, _widget: Gtk.Widget) -> None:
        passphrase = self._passphrase_entry.get_text()
        if not passphrase:
            self._show_lock_error("Please enter a passphrase")
            return

        try:
            self._state.unlock(passphrase)
            self._on_unlocked()
        except DecryptionError:
            self._show_lock_error("Wrong passphrase. Please try again.")
            self._passphrase_entry.set_text("")
            self._passphrase_entry.grab_focus()

    def _show_lock_error(self, message: str) -> None:
        self._lock_error_label.set_text(message)
        self._lock_error_label.set_visible(True)

    # --- Unlocked state ---

    def _on_unlocked(self) -> None:
        from ydoit.entry_list import EntryListPage

        self._passphrase_entry.set_text("")

        entry_list_page = EntryListPage(state=self._state, window=self)
        self._nav_view.replace([entry_list_page])
        self._toast_overlay.set_child(self._nav_view)

    # --- Public helpers for child pages ---

    def show_toast(self, message: str) -> None:
        toast = Adw.Toast(title=message, timeout=3)
        self._toast_overlay.add_toast(toast)

    @property
    def state(self) -> AppState:
        return self._state

    @property
    def nav_view(self) -> Adw.NavigationView:
        return self._nav_view
