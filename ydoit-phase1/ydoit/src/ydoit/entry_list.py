"""Entry list page — main view after unlock."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from ydoit.widgets import ShortcutBadge

if TYPE_CHECKING:
    from ydoit.state import AppState
    from ydoit.window import YdoitWindow


class EntryListPage(Adw.NavigationPage):
    """Displays entries grouped by category with search, add, and settings."""

    def __init__(self, state: AppState, window: YdoitWindow, **kwargs: object) -> None:
        super().__init__(title="ydoit", **kwargs)
        self._state = state
        self._window = window
        self._search_active = False
        self._search_text = ""

        self._build_ui()
        self._populate()

        self._state.connect("entries-changed", self._on_entries_changed)

    def _build_ui(self) -> None:
        # Header bar
        header = Adw.HeaderBar()

        # Search button
        self._search_btn = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self._search_btn.connect("toggled", self._on_search_toggled)
        header.pack_start(self._search_btn)

        # Menu button
        menu = Gio.Menu()
        menu.append("Import...", "entry-list.import")
        menu.append("Export...", "entry-list.export")
        menu.append("Settings", "entry-list.settings")

        menu_btn = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            menu_model=menu,
        )
        header.pack_end(menu_btn)

        # Add button
        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.connect("clicked", self._on_add_clicked)
        header.pack_end(add_btn)

        # Search bar
        self._search_entry = Gtk.SearchEntry(placeholder_text="Search entries...")
        self._search_entry.connect("search-changed", self._on_search_changed)

        self._search_bar = Gtk.SearchBar(child=self._search_entry)
        self._search_bar.connect_entry(self._search_entry)

        # Scrolled content
        self._scroll = Gtk.ScrolledWindow(vexpand=True)
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._scroll.set_child(self._content_box)

        # Empty state
        self._empty_status = Adw.StatusPage(
            icon_name="document-new-symbolic",
            title="No Entries",
            description="Click + to add your first entry",
        )

        # Layout
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(self._search_bar)
        main_box.append(self._scroll)
        toolbar_view.set_content(main_box)

        self.set_child(toolbar_view)

        # Actions
        self._setup_actions()

    def _setup_actions(self) -> None:
        action_group = Gio.SimpleActionGroup()

        import_action = Gio.SimpleAction.new("import", None)
        import_action.connect("activate", self._on_import_clicked)
        action_group.add_action(import_action)

        export_action = Gio.SimpleAction.new("export", None)
        export_action.connect("activate", self._on_export_clicked)
        action_group.add_action(export_action)

        settings_action = Gio.SimpleAction.new("settings", None)
        settings_action.connect("activate", self._on_settings_clicked)
        action_group.add_action(settings_action)

        self.insert_action_group("entry-list", action_group)

    def _populate(self) -> None:
        # Clear existing content
        while child := self._content_box.get_first_child():
            self._content_box.remove(child)

        entries = self._state.entries
        if not entries:
            self._scroll.set_child(self._empty_status)
            return

        self._scroll.set_child(self._content_box)
        categories = self._state.get_entries_by_category()

        for cat_name, cat_entries in categories.items():
            # Filter by search
            if self._search_text:
                cat_entries = [
                    e
                    for e in cat_entries
                    if self._search_text in e.name.lower()
                    or self._search_text in e.display_label.lower()
                    or self._search_text in e.keycombo.lower()
                ]
                if not cat_entries:
                    continue

            group = Adw.PreferencesGroup(title=cat_name.title())

            for entry in cat_entries:
                row = Adw.ActionRow(
                    title=entry.display_label,
                    subtitle=entry.name,
                    activatable=True,
                )

                # Shortcut badge as suffix
                if entry.keycombo:
                    badge = ShortcutBadge(entry.keycombo)
                    row.add_suffix(badge)

                # Type indicator
                if entry.filename:
                    icon = Gtk.Image(icon_name="document-open-symbolic")
                else:
                    icon = Gtk.Image(icon_name="edit-paste-symbolic")
                icon.add_css_class("dim-label")
                row.add_suffix(icon)

                # Navigation arrow
                arrow = Gtk.Image(icon_name="go-next-symbolic")
                row.add_suffix(arrow)

                row.connect("activated", self._on_entry_activated, entry.name)
                group.add(row)

            self._content_box.append(group)

    # --- Signal handlers ---

    def _on_entries_changed(self, _state: object) -> None:
        self._populate()

    def _on_search_toggled(self, btn: Gtk.ToggleButton) -> None:
        self._search_active = btn.get_active()
        self._search_bar.set_search_mode(self._search_active)
        if self._search_active:
            self._search_entry.grab_focus()
        else:
            self._search_text = ""
            self._search_entry.set_text("")
            self._populate()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._search_text = entry.get_text().lower()
        self._populate()

    def _on_add_clicked(self, _btn: Gtk.Button) -> None:
        from ydoit.entry_editor import EntryEditorPage

        editor = EntryEditorPage(state=self._state, window=self._window)
        self._window.nav_view.push(editor)

    def _on_entry_activated(self, _row: Adw.ActionRow, entry_name: str) -> None:
        from ydoit.entry_editor import EntryEditorPage

        editor = EntryEditorPage(
            state=self._state, window=self._window, entry_name=entry_name
        )
        self._window.nav_view.push(editor)

    def _on_settings_clicked(self, _action: object, _param: object) -> None:
        from ydoit.settings_page import SettingsPage

        page = SettingsPage(state=self._state, window=self._window)
        self._window.nav_view.push(page)

    def _on_import_clicked(self, _action: object, _param: object) -> None:
        dialog = Gtk.FileDialog(title="Import Config")
        dialog.open(self._window, None, self._on_import_response)

    def _on_import_response(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.open_finish(result)
        except Exception:
            return
        path_str = gfile.get_path()
        if path_str is None:
            return

        from pathlib import Path

        try:
            count = self._state.import_config(Path(path_str))
            self._window.show_toast(f"Imported {count} entries")
        except Exception as e:
            self._window.show_toast(f"Import failed: {e}")

    def _on_export_clicked(self, _action: object, _param: object) -> None:
        dialog = Gtk.FileDialog(
            title="Export Config",
            initial_name="ydoit-export.json",
        )
        dialog.save(self._window, None, self._on_export_response)

    def _on_export_response(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
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
