# Phase 2 GUI — Design

Date: 2026-03-09

## Overview

Phase 2 adds a GTK4/libadwaita desktop GUI to ydoit. All new code lives in the existing
`ydoit-phase1/ydoit/src/ydoit/` package alongside Phase 1. No UI XML files — all layout
and logic in Python (Option A). A separate `ydoit-gui` entry point launches the app;
the existing `ydoit` CLI entry point is unchanged.

## New Files

```
src/ydoit/
├── app.py               # Adw.Application subclass — startup, owns Config + managers
├── window.py            # AdwApplicationWindow — main list view, navigation root
├── entry_editor.py      # AdwNavigationPage — add/edit entry form
├── settings_page.py     # AdwNavigationPage — settings form
└── passphrase_dialog.py # AdwAlertDialog subclass — passphrase prompt
```

`pyproject.toml` gains a second entry point:

```toml
[project.scripts]
ydoit     = "ydoit.cli:main"
ydoit-gui = "ydoit.app:main"
```

## Startup and Passphrase Flow

`YdoitApp` (`Adw.Application`, app-id `org.ydoit.app`) owns a `ConfigManager` and a
`ShortcutManager`. On `activate`:

1. Call `KeyringManager.get_passphrase()` — if cached, proceed
2. Otherwise show `PassphraseDialog` (an `AdwAlertDialog` with one `AdwPasswordEntryRow`)
3. Call `cm.load(passphrase)` — on `DecryptionError`, show error dialog and re-prompt
4. On success, store passphrase in keyring if `settings.use_keyring_cache` is True
5. Create and present `MainWindow`

The live `Config` object lives on `YdoitApp` for the session lifetime. Windows hold a
reference to it; they do not own it.

## Main Window

`MainWindow` is an `Adw.ApplicationWindow` wrapping an `AdwNavigationView`. The root
page is an `AdwPreferencesPage` rendering entries grouped by category — one
`AdwPreferencesGroup` per category, each entry as an `AdwActionRow` showing label and
keycombo badge. An **Add** button sits in the header bar.

A footer toolbar contains **Import**, **Export**, and **Settings** buttons.

- Clicking a row or Add pushes `EntryEditorPage` onto the nav stack
- Settings pushes `SettingsPage`
- Import/Export call `ConfigManager` directly, then reload the list and sync shortcuts;
  results surface as toasts
- The list rebuilds from `config.entries` on every pop (return from editor)

## Entry Editor

`EntryEditorPage` (`AdwNavigationPage`) receives an existing `Entry` or `None` for new.

Form layout (AdwPreferencesPage with groups):

- **Identity**: Name (`AdwEntryRow`, disabled when editing), Label, Category
- **What to type**: Radio-style toggle between "Type a string"
  (`AdwPasswordEntryRow` with show/hide) and "Type file contents"
  (`AdwEntryRow` + file chooser via `Gtk.FileDialog`)
- **Shortcut**: `AdwEntryRow` for key combo (plain text, e.g. `Super+F11`; shortcut
  recorder deferred to a later phase)
- **Advanced**: Spin rows for typing delay and hold delay (ms); entry row for notes

Footer: **Delete** (destructive, hidden for new entries) and **Save** (suggested).

**Save flow**: validate → `ShortcutManager.find_conflict()` → if conflict, show
`AdwAlertDialog` naming the conflicting shortcut with Cancel / Save Anyway → mutate
`Config` → `cm.save(config)` → `sm.sync(config)` → pop nav → success toast.

**Delete flow**: `AdwAlertDialog` confirmation → remove from `Config` → save → sync →
pop nav.

## Settings Page

`SettingsPage` (`AdwNavigationPage`) with two preference groups:

- **Typing defaults**: Spin rows for typing delay and hold delay (ms)
- **Security**: Switch row for "Cache passphrase in keyring"; spin row for cache timeout
  (minutes, 0 = session only); **Change GPG Passphrase** button (AdwAlertDialog with
  current + new passphrase fields; calls `cm.change_passphrase(old, new)`)

Changes apply on field change (no Save button) — each change calls `cm.save(config)`.

`ConfigManager.change_passphrase(old_passphrase, new_passphrase)` is a new method:
decrypt with old → re-encrypt with new → atomic write → update keyring cache.

## Error Handling and Toasts

A single `AdwToastOverlay` wraps the main window content; child pages access it via the
application instance.

| Situation | Surface |
|---|---|
| Shortcut conflict, invalid name | `AdwAlertDialog` (blocking, user retries) |
| Save/sync failure (GPG, dconf) | `AdwAlertDialog` with message; config not mutated |
| Gio unavailable at startup | Warning toast: "Shortcut sync unavailable: install python3-gobject" |
| Wrong passphrase on load | Re-prompt (passphrase dialog again) |

No `print()` or `sys.stderr` in the GUI path — all errors via dialogs or toasts.

## Testing Strategy

GTK widgets are not instantiated in headless pytest runs. Coverage strategy:

- All business logic (save, sync, conflict check, passphrase) is covered by Phase 1 tests
- `ConfigManager.change_passphrase()` gets unit tests matching the existing config
  manager test patterns
- A `conftest.py` fixture provides a mock app-like object (no GTK, just managers +
  config) for testing any non-widget coordinator logic
- A manual smoke-test checklist covers: launch, passphrase prompt, add/edit/delete,
  conflict dialog, settings changes, import/export, Gio-unavailable warning

GTK in CI deferred to Phase 3 (container-based test environments).

## Out of Scope for Phase 2

- Shortcut recorder (keyboard capture on "Record" button) — later phase
- Search/filter bar — later phase
- `ydoit` (no args) launching the GUI — `ydoit-gui` is the separate entry point
