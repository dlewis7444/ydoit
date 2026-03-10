"""Passphrase prompt dialog."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk


class PassphraseDialog(Adw.AlertDialog):
    """Modal dialog prompting the user for the GPG passphrase."""

    def __init__(self, error_message: str | None = None) -> None:
        body = (
            error_message
            if error_message
            else "Enter your GPG passphrase to unlock ydoit."
        )
        super().__init__(heading="Enter Passphrase", body=body)

        self._entry = Adw.PasswordEntryRow(title="Passphrase")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(self._entry)
        self.set_extra_child(box)

        self.add_response("cancel", "Cancel")
        self.add_response("ok", "Unlock")
        self.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("ok")
        self.set_close_response("cancel")

        self._entry.connect("entry-activated", self._on_entry_activated)

    def _on_entry_activated(self, _: object) -> None:
        self.emit("response", "ok")
        self.close()

    @property
    def passphrase(self) -> str:
        """Return the text currently in the passphrase field."""
        return self._entry.get_text()
