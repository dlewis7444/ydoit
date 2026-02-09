"""Reusable GUI widgets."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


class ShortcutBadge(Gtk.Box):
    """Displays a keyboard shortcut as styled key badges.

    Example: "Super+F11" renders as [Super] + [F11] with keycap styling.
    """

    def __init__(self, keycombo: str = "", **kwargs: object) -> None:
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            valign=Gtk.Align.CENTER,
            **kwargs,
        )
        if keycombo:
            self.set_keycombo(keycombo)

    def set_keycombo(self, keycombo: str) -> None:
        # Remove existing children
        while child := self.get_first_child():
            self.remove(child)

        if not keycombo:
            return

        parts = keycombo.split("+")
        for i, part in enumerate(parts):
            if i > 0:
                sep = Gtk.Label(label="+")
                sep.add_css_class("dim-label")
                self.append(sep)

            label = Gtk.Label(label=part)
            label.add_css_class("keycap")
            self.append(label)
