"""GTK4/libadwaita application entry point."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from ydoit import constants


class YdoitApplication(Adw.Application):
    """Main application class for ydoit GUI."""

    def __init__(self) -> None:
        super().__init__(
            application_id=constants.APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        from ydoit.window import YdoitWindow

        win = self.props.active_window
        if not win:
            win = YdoitWindow(application=self)
        win.present()


def main_gui() -> int:
    """Entry point for the GUI application."""
    app = YdoitApplication()
    return app.run(sys.argv[:1])  # Don't pass CLI args to GTK
