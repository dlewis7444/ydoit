"""Main application window."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

if TYPE_CHECKING:
    from ydoit.models import Config


class MainWindow(Adw.ApplicationWindow):
    """The root window for ydoit."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.set_title("ydoit")
        self.set_default_size(600, 700)
        self._groups: list[Adw.PreferencesGroup] = []
        self._config: Config | None = None

        self._nav_view = Adw.NavigationView()
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._nav_view)
        self.set_content(self._toast_overlay)

        self._main_page = self._build_main_page()
        self._nav_view.push(self._main_page)

    # --- Public API ---

    def load_config(self, config: Config) -> None:
        """Populate or refresh the entry list from config."""
        self._config = config
        self._rebuild_list()

    def show_toast(self, message: str) -> None:
        """Show a brief toast notification."""
        toast = Adw.Toast(title=message)
        self._toast_overlay.add_toast(toast)

    # --- Main page construction ---

    def _build_main_page(self) -> Adw.NavigationPage:
        page = Adw.NavigationPage(title="ydoit")

        # Header bar
        header = Adw.HeaderBar()
        add_btn = Gtk.Button(label="Add")
        add_btn.add_css_class("suggested-action")
        add_btn.connect("clicked", self._on_add_clicked)
        header.pack_end(add_btn)

        # Preferences page for entry list
        self._prefs_page = Adw.PreferencesPage()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self._prefs_page)

        # Footer action bar
        import_btn = Gtk.Button(label="Import")
        import_btn.connect("clicked", self._on_import_clicked)
        export_btn = Gtk.Button(label="Export")
        export_btn.connect("clicked", self._on_export_clicked)
        settings_btn = Gtk.Button(label="Settings")
        settings_btn.connect("clicked", self._on_settings_clicked)
        for btn in (import_btn, export_btn, settings_btn):
            btn.add_css_class("flat")

        footer_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_top=6,
            margin_bottom=6,
        )
        footer_box.append(import_btn)
        footer_box.append(export_btn)
        spacer = Gtk.Box(hexpand=True)
        footer_box.append(spacer)
        footer_box.append(settings_btn)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(scroll)
        main_box.append(separator)
        main_box.append(footer_box)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(main_box)

        page.set_child(toolbar_view)
        return page

    # --- Entry list rebuild ---

    def _rebuild_list(self) -> None:
        """Clear and repopulate the preferences page from self._config."""
        for group in self._groups:
            self._prefs_page.remove(group)
        self._groups.clear()

        if self._config is None or not self._config.entries:
            empty_group = Adw.PreferencesGroup()
            empty_row = Adw.ActionRow(title="No entries yet")
            empty_row.set_subtitle("Click Add to create your first entry")
            empty_group.add(empty_row)
            self._prefs_page.add(empty_group)
            self._groups.append(empty_group)
            return

        # Group entries by category
        by_category: dict[str, list[str]] = {}
        for name, entry in self._config.entries.items():
            cat = entry.category or "general"
            by_category.setdefault(cat, []).append(name)

        for category, names in sorted(by_category.items()):
            group = Adw.PreferencesGroup(title=category.upper())
            for name in sorted(names):
                entry = self._config.entries[name]
                row = Adw.ActionRow()
                row.set_title(entry.display_label)
                row.set_subtitle(entry.keycombo if entry.keycombo else "No shortcut")
                row.set_activatable(True)
                row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
                row.connect("activated", self._on_entry_activated, name)
                group.add(row)
            self._prefs_page.add(group)
            self._groups.append(group)

    # --- Navigation callbacks ---

    def _on_add_clicked(self, *args: object) -> None:
        from ydoit.entry_editor import EntryEditorPage

        editor = EntryEditorPage(entry=None)
        self._nav_view.push(editor)
        editor.connect("saved", self._on_editor_saved)

    def _on_entry_activated(self, row: object, name: str) -> None:
        from ydoit.entry_editor import EntryEditorPage

        assert self._config is not None
        entry = self._config.entries[name]
        editor = EntryEditorPage(entry=entry)
        self._nav_view.push(editor)
        editor.connect("saved", self._on_editor_saved)

    def _on_editor_saved(self, *args: object) -> None:
        app = self.get_application()
        app.save_config()
        self._rebuild_list()

    def _on_settings_clicked(self, *args: object) -> None:
        from ydoit.settings_page import SettingsPage

        page = SettingsPage()
        self._nav_view.push(page)
        page.connect("settings-changed", self._on_settings_changed)

    def _on_settings_changed(self, *args: object) -> None:
        app = self.get_application()
        app.save_config()

    def _on_import_clicked(self, *args: object) -> None:
        dialog = Gtk.FileDialog()
        dialog.open(self, None, self._on_import_file_chosen)

    def _on_import_file_chosen(self, dialog: Gtk.FileDialog, result: object) -> None:
        import json
        from pathlib import Path

        from ydoit.exceptions import YdoitError
        from ydoit.models import Config

        try:
            gfile = dialog.open_finish(result)
        except Exception:
            return
        if gfile is None:
            return
        path = Path(gfile.get_path())
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            imported = Config.from_dict(data)
            app = self.get_application()
            count = 0
            for name, entry in imported.entries.items():
                if name not in app.config.entries:
                    app.config.entries[name] = entry
                    count += 1
            app.save_config()
            self._rebuild_list()
            self.show_toast(f"Import complete: {count} new entries")
        except (YdoitError, Exception) as e:
            self._show_error_dialog(f"Import failed: {e}")

    def _on_export_clicked(self, *args: object) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_initial_filename("ydoit-export.json")
        dialog.save(self, None, self._on_export_file_chosen)

    def _on_export_file_chosen(self, dialog: Gtk.FileDialog, result: object) -> None:
        import json
        from pathlib import Path

        try:
            gfile = dialog.save_finish(result)
        except Exception:
            return
        if gfile is None:
            return
        path = Path(gfile.get_path())
        app = self.get_application()
        try:
            path.write_text(
                json.dumps(app.config.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.show_toast(f"Exported to {path.name}")
        except Exception as e:
            self._show_error_dialog(f"Export failed: {e}")

    def _show_error_dialog(self, message: str) -> None:
        dlg = Adw.AlertDialog(heading="Error", body=message)
        dlg.add_response("ok", "OK")
        dlg.set_default_response("ok")
        dlg.choose(self, None, lambda d, r: None)
