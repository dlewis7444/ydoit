"""GTK4/libadwaita GUI entry point for ydoit."""

from __future__ import annotations


def main() -> None:
    """Launch the ydoit GUI application."""
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw

    from ydoit import constants

    app = Adw.Application(application_id=constants.APP_ID)
    app.run(None)
