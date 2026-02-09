"""Entry editor page — create and edit entries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ydoit import constants
from ydoit.exceptions import (
    DuplicateEntryError,
    InvalidEntryNameError,
    ShortcutConflictError,
)
from ydoit.models import Entry

if TYPE_CHECKING:
    from ydoit.state import AppState
    from ydoit.window import YdoitWindow


class EntryEditorPage(Adw.NavigationPage):
    """Create or edit an entry with all fields."""

    def __init__(
        self,
        state: AppState,
        window: YdoitWindow,
        entry_name: str | None = None,
        **kwargs: object,
    ) -> None:
        self._is_edit = entry_name is not None
        title = "Edit Entry" if self._is_edit else "New Entry"
        super().__init__(title=title, **kwargs)

        self._state = state
        self._window = window
        self._entry_name = entry_name

        self._build_ui()

        if self._is_edit:
            self._load_entry()

    def _build_ui(self) -> None:
        header = Adw.HeaderBar()

        # Save button
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)

        scroll = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=600)

        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page_box.set_margin_top(24)
        page_box.set_margin_bottom(24)
        page_box.set_margin_start(12)
        page_box.set_margin_end(12)

        # --- Identity group ---
        identity_group = Adw.PreferencesGroup(title="Identity")

        self._name_row = Adw.EntryRow(title="Name")
        if self._is_edit:
            self._name_row.set_editable(False)
            self._name_row.add_css_class("dim-label")
        identity_group.add(self._name_row)

        self._label_row = Adw.EntryRow(title="Label")
        identity_group.add(self._label_row)

        self._category_row = Adw.EntryRow(title="Category")
        self._category_row.set_text(constants.DEFAULT_CATEGORY)
        identity_group.add(self._category_row)

        page_box.append(identity_group)

        # --- Shortcut group ---
        shortcut_group = Adw.PreferencesGroup(
            title="Keyboard Shortcut",
            description='Type a combo like "Super+F11" or click Record',
        )

        self._shortcut_row = Adw.EntryRow(title="Key Combination")
        record_btn = Gtk.Button(
            icon_name="media-record-symbolic",
            valign=Gtk.Align.CENTER,
            tooltip_text="Record shortcut",
        )
        record_btn.add_css_class("flat")
        record_btn.connect("clicked", self._on_record_shortcut)
        self._shortcut_row.add_suffix(record_btn)
        shortcut_group.add(self._shortcut_row)

        page_box.append(shortcut_group)

        # --- Content group ---
        content_group = Adw.PreferencesGroup(title="Content")

        # Type selector
        self._type_row = Adw.ActionRow(title="Type")
        type_box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)

        self._string_radio = Gtk.CheckButton(label="String")
        self._file_radio = Gtk.CheckButton(label="File")
        self._file_radio.set_group(self._string_radio)
        self._string_radio.set_active(True)
        self._string_radio.connect("toggled", self._on_type_changed)

        type_box.append(self._string_radio)
        type_box.append(self._file_radio)
        self._type_row.add_suffix(type_box)
        content_group.add(self._type_row)

        # String content
        self._string_frame = Gtk.Frame()
        self._string_frame.add_css_class("view")
        self._string_view = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=8,
            bottom_margin=8,
            left_margin=8,
            right_margin=8,
            height_request=120,
        )
        self._string_frame.set_child(self._string_view)
        content_group.add(self._string_frame)

        # File path
        self._file_row = Adw.EntryRow(title="File Path")
        self._file_row.set_visible(False)
        content_group.add(self._file_row)

        page_box.append(content_group)

        # --- Notes group ---
        notes_group = Adw.PreferencesGroup(title="Notes")
        self._notes_frame = Gtk.Frame()
        self._notes_frame.add_css_class("view")
        self._notes_view = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=8,
            bottom_margin=8,
            left_margin=8,
            right_margin=8,
            height_request=80,
        )
        self._notes_frame.set_child(self._notes_view)
        notes_group.add(self._notes_frame)
        page_box.append(notes_group)

        # --- Advanced group ---
        advanced_group = Adw.PreferencesGroup(
            title="Advanced",
            description="Per-entry delay overrides (leave at 0 to use global defaults)",
        )

        self._typing_delay_row = Adw.ActionRow(title="Typing Delay (ms)")
        self._typing_delay_spin = Gtk.SpinButton.new_with_range(0, 500, 1)
        self._typing_delay_spin.set_valign(Gtk.Align.CENTER)
        self._typing_delay_row.add_suffix(self._typing_delay_spin)
        advanced_group.add(self._typing_delay_row)

        self._hold_delay_row = Adw.ActionRow(title="Hold Delay (ms)")
        self._hold_delay_spin = Gtk.SpinButton.new_with_range(0, 500, 1)
        self._hold_delay_spin.set_valign(Gtk.Align.CENTER)
        self._hold_delay_row.add_suffix(self._hold_delay_spin)
        advanced_group.add(self._hold_delay_row)

        page_box.append(advanced_group)

        # --- Delete button (edit mode only) ---
        if self._is_edit:
            delete_group = Adw.PreferencesGroup()
            delete_btn = Gtk.Button(label="Delete Entry")
            delete_btn.add_css_class("destructive-action")
            delete_btn.add_css_class("pill")
            delete_btn.set_halign(Gtk.Align.CENTER)
            delete_btn.connect("clicked", self._on_delete)
            delete_group.add(delete_btn)
            page_box.append(delete_group)

        clamp.set_child(page_box)
        scroll.set_child(clamp)
        toolbar_view.set_content(scroll)
        self.set_child(toolbar_view)

    def _load_entry(self) -> None:
        entry = self._state.get_entry(self._entry_name)
        self._name_row.set_text(entry.name)
        self._label_row.set_text(entry.label)
        self._category_row.set_text(entry.category)

        self._shortcut_row.set_text(entry.keycombo)

        if entry.filename:
            self._file_radio.set_active(True)
            self._file_row.set_text(entry.filename)
        else:
            self._string_radio.set_active(True)
            self._string_view.get_buffer().set_text(entry.string)

        self._notes_view.get_buffer().set_text(entry.notes)

        if entry.typing_delay_ms is not None:
            self._typing_delay_spin.set_value(entry.typing_delay_ms)
        if entry.hold_delay_ms is not None:
            self._hold_delay_spin.set_value(entry.hold_delay_ms)

    # --- Type toggle ---

    def _on_type_changed(self, btn: Gtk.CheckButton) -> None:
        is_string = self._string_radio.get_active()
        self._string_frame.set_visible(is_string)
        self._file_row.set_visible(not is_string)

    # --- Shortcut recording ---

    def _on_record_shortcut(self, _btn: Gtk.Button) -> None:
        from ydoit.dialogs import ShortcutRecorderDialog

        dialog = ShortcutRecorderDialog(
            state=self._state,
            exclude_entry=self._entry_name,
        )
        dialog.connect("shortcut-recorded", self._on_shortcut_recorded)
        dialog.present(self._window)

    def _on_shortcut_recorded(self, _dialog: object, keycombo: str) -> None:
        self._shortcut_row.set_text(keycombo)

    # --- Save ---

    def _on_save(self, _btn: Gtk.Button) -> None:
        name = self._name_row.get_text().strip()
        label = self._label_row.get_text().strip()
        category = self._category_row.get_text().strip() or constants.DEFAULT_CATEGORY
        keycombo = self._shortcut_row.get_text().strip()

        buf = self._string_view.get_buffer()
        string_content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

        filename = self._file_row.get_text().strip()
        is_string = self._string_radio.get_active()

        notes_buf = self._notes_view.get_buffer()
        notes = notes_buf.get_text(
            notes_buf.get_start_iter(), notes_buf.get_end_iter(), False
        )

        typing_delay = int(self._typing_delay_spin.get_value())
        hold_delay = int(self._hold_delay_spin.get_value())

        try:
            if self._is_edit:
                self._state.update_entry(
                    name,
                    keycombo=keycombo,
                    string=string_content if is_string else "",
                    filename=filename if not is_string else "",
                    label=label,
                    category=category,
                    notes=notes,
                    typing_delay_ms=typing_delay if typing_delay > 0 else None,
                    hold_delay_ms=hold_delay if hold_delay > 0 else None,
                )
                self._window.show_toast(f"Updated '{name}'")
            else:
                if not name:
                    self._window.show_toast("Name is required")
                    return
                entry = Entry(
                    name=name,
                    keycombo=keycombo,
                    string=string_content if is_string else "",
                    filename=filename if not is_string else "",
                    label=label,
                    category=category,
                    notes=notes,
                    typing_delay_ms=typing_delay if typing_delay > 0 else None,
                    hold_delay_ms=hold_delay if hold_delay > 0 else None,
                )
                self._state.add_entry(entry)
                self._window.show_toast(f"Added '{name}'")

            self._window.nav_view.pop()

        except InvalidEntryNameError as e:
            self._window.show_toast(str(e))
        except DuplicateEntryError:
            self._window.show_toast(f"Entry '{name}' already exists")
        except ShortcutConflictError as e:
            self._window.show_toast(str(e))
        except Exception as e:
            self._window.show_toast(f"Error: {e}")

    # --- Delete ---

    def _on_delete(self, _btn: Gtk.Button) -> None:
        from ydoit.dialogs import confirm_delete

        confirm_delete(
            self._window,
            self._entry_name,
            self._do_delete,
        )

    def _do_delete(self) -> None:
        try:
            self._state.remove_entry(self._entry_name)
            self._window.show_toast(f"Deleted '{self._entry_name}'")
            self._window.nav_view.pop()
        except Exception as e:
            self._window.show_toast(f"Error: {e}")
