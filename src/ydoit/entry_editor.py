"""Entry add/edit page."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

if TYPE_CHECKING:
    from ydoit.models import Entry


class EntryEditorPage(Adw.NavigationPage):
    """Form for creating or editing a ydoit entry."""

    __gsignals__ = {
        "saved": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, entry: Entry | None) -> None:
        title = "Edit Entry" if entry is not None else "Add Entry"
        super().__init__(title=title)
        self._original_entry = entry
        self._build_ui()
        if entry is not None:
            self._populate(entry)

    # --- UI construction ---

    def _build_ui(self) -> None:
        header = Adw.HeaderBar()

        prefs = Adw.PreferencesPage()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(prefs)

        # Identity group
        identity = Adw.PreferencesGroup(title="Identity")
        self._label_row = Adw.EntryRow(title="Label")
        self._name_row = Adw.EntryRow(title="Trigger")
        self._category_row = Adw.EntryRow(title="Category")
        identity.add(self._label_row)
        identity.add(self._name_row)
        identity.add(self._category_row)
        prefs.add(identity)

        # What to type group
        type_group = Adw.PreferencesGroup(title="What to Type")
        type_model = Gtk.StringList.new(["Type a string", "Type file contents"])
        self._type_row = Adw.ComboRow(title="Content")
        self._type_row.set_model(type_model)
        self._type_row.connect("notify::selected", self._on_type_changed)
        self._string_row = Adw.PasswordEntryRow(title="String to type")
        self._file_row = Adw.EntryRow(title="File path")
        browse_btn = Gtk.Button(icon_name="document-open-symbolic")
        browse_btn.add_css_class("flat")
        browse_btn.connect("clicked", self._on_browse_clicked)
        self._file_row.add_suffix(browse_btn)
        self._file_row.set_visible(False)
        type_group.add(self._type_row)
        type_group.add(self._string_row)
        type_group.add(self._file_row)
        prefs.add(type_group)

        # Shortcut group
        shortcut_group = Adw.PreferencesGroup(title="Shortcut")
        self._keycombo_row = Adw.EntryRow(title="Key combo (e.g. Super+F11)")
        shortcut_group.add(self._keycombo_row)
        prefs.add(shortcut_group)

        # Advanced group
        advanced = Adw.PreferencesGroup(title="Advanced")
        self._typing_delay_row = Adw.SpinRow.new_with_range(0, 1000, 1)
        self._typing_delay_row.set_title("Typing delay (ms)")
        self._hold_delay_row = Adw.SpinRow.new_with_range(0, 1000, 1)
        self._hold_delay_row.set_title("Hold delay (ms)")
        self._notes_row = Adw.EntryRow(title="Notes")
        advanced.add(self._typing_delay_row)
        advanced.add(self._hold_delay_row)
        advanced.add(self._notes_row)
        prefs.add(advanced)

        # Footer buttons
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)

        self._delete_btn = Gtk.Button(label="Delete")
        self._delete_btn.add_css_class("destructive-action")
        self._delete_btn.connect("clicked", self._on_delete_clicked)
        self._delete_btn.set_visible(self._original_entry is not None)

        footer_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_top=6,
            margin_bottom=6,
        )
        footer_box.append(self._delete_btn)
        spacer = Gtk.Box(hexpand=True)
        footer_box.append(spacer)
        footer_box.append(save_btn)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(scroll)
        main_box.append(separator)
        main_box.append(footer_box)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(main_box)
        self.set_child(toolbar_view)

    def _populate(self, entry: Entry) -> None:
        from ydoit import constants
        from ydoit.models import EntryType

        self._name_row.set_text(entry.trigger)
        self._name_row.set_editable(False)  # Name is immutable when editing
        self._label_row.set_text(entry.label or "")
        self._category_row.set_text(entry.category or constants.DEFAULT_CATEGORY)
        self._keycombo_row.set_text(entry.keycombo or "")
        self._notes_row.set_text(entry.notes or "")

        if entry.entry_type == EntryType.FILE:
            self._type_row.set_selected(1)
            self._file_row.set_text(entry.filename)
            self._string_row.set_visible(False)
            self._file_row.set_visible(True)
        else:
            self._type_row.set_selected(0)
            self._string_row.set_text(entry.string or "")

        if entry.typing_delay_ms is not None:
            self._typing_delay_row.set_value(entry.typing_delay_ms)
        if entry.hold_delay_ms is not None:
            self._hold_delay_row.set_value(entry.hold_delay_ms)

    # --- Signal handlers ---

    def _on_type_changed(self, *args: object) -> None:
        is_file = self._type_row.get_selected() == 1
        self._string_row.set_visible(not is_file)
        self._file_row.set_visible(is_file)

    def _on_browse_clicked(self, *args: object) -> None:
        dialog = Gtk.FileDialog()
        dialog.open(self.get_root(), None, self._on_file_chosen)

    def _on_file_chosen(self, dialog: Gtk.FileDialog, result: object) -> None:
        try:
            gfile = dialog.open_finish(result)
            if gfile:
                self._file_row.set_text(gfile.get_path() or "")
        except Exception:
            pass

    def _on_save_clicked(self, *args: object) -> None:
        from ydoit.exceptions import GioNotAvailableError, InvalidEntryTriggerError
        from ydoit.models import Entry
        from ydoit.shortcut_manager import ShortcutManager

        trigger = self._name_row.get_text().strip()
        try:
            Entry.validate_trigger(trigger)
        except InvalidEntryTriggerError as e:
            self._show_error(str(e))
            return

        keycombo = self._keycombo_row.get_text().strip()
        is_file = self._type_row.get_selected() == 1
        string = "" if is_file else self._string_row.get_text()
        filename = self._file_row.get_text().strip() if is_file else ""

        # Check for shortcut conflict
        if keycombo:
            sm = ShortcutManager()
            try:
                conflict = sm.find_conflict(keycombo, exclude_entry=trigger)
                if conflict:
                    self._show_conflict_dialog(
                        conflict,
                        on_save_anyway=lambda: self._do_save(
                            trigger, keycombo, string, filename
                        ),
                    )
                    return
            except GioNotAvailableError:
                pass  # Gio unavailable; skip conflict check

        self._do_save(trigger, keycombo, string, filename)

    def _do_save(
        self, trigger: str, keycombo: str, string: str, filename: str
    ) -> None:
        from ydoit import constants
        from ydoit.models import Entry

        app = self.get_root().get_application()

        entry = Entry(
            trigger=trigger,
            keycombo=keycombo,
            string=string,
            filename=filename,
            label=self._label_row.get_text().strip(),
            category=self._category_row.get_text().strip() or constants.DEFAULT_CATEGORY,
            notes=self._notes_row.get_text().strip(),
            typing_delay_ms=int(self._typing_delay_row.get_value()) or None,
            hold_delay_ms=int(self._hold_delay_row.get_value()) or None,
        )

        app.config.entries[trigger] = entry
        self.emit("saved")

        nav = self.get_parent()
        if nav is not None:
            nav.pop()
        self.get_root().show_toast("Saved")

    def _on_delete_clicked(self, *args: object) -> None:
        trigger = self._original_entry.trigger if self._original_entry else ""
        dlg = Adw.AlertDialog(
            heading="Delete Entry",
            body=f"Delete '{trigger}'? This cannot be undone.",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.choose(self.get_root(), None, self._on_delete_confirmed)

    def _on_delete_confirmed(self, dlg: object, result: object) -> None:
        response = dlg.choose_finish(result)
        if response != "delete":
            return
        app = self.get_root().get_application()
        trigger = self._original_entry.trigger
        app.config.entries.pop(trigger, None)
        self.emit("saved")
        nav = self.get_parent()
        if nav is not None:
            nav.pop()
        self.get_root().show_toast(f"Deleted '{trigger}'")

    def _show_error(self, message: str) -> None:
        dlg = Adw.AlertDialog(heading="Error", body=message)
        dlg.add_response("ok", "OK")
        dlg.set_default_response("ok")
        dlg.choose(self.get_root(), None, lambda d, r: None)

    def _show_conflict_dialog(
        self, conflict: object, on_save_anyway: object
    ) -> None:
        from ydoit.shortcut_manager import ConflictInfo

        assert isinstance(conflict, ConflictInfo)
        body = (
            f"'{conflict.keycombo}' is already bound to "
            f"'{conflict.existing_name}' ({conflict.existing_source}). "
            "Save anyway?"
        )
        dlg = Adw.AlertDialog(heading="Shortcut Conflict", body=body)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("save", "Save Anyway")
        dlg.set_response_appearance("save", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")

        def _on_response(d: object, r: object) -> None:
            if d.choose_finish(r) == "save":
                on_save_anyway()

        dlg.choose(self.get_root(), None, _on_response)
