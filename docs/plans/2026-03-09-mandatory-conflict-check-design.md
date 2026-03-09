# Design: Mandatory Shortcut Conflict Check

**Date:** 2026-03-09
**Status:** Approved

## Problem

The shortcut conflict check in `ydoit add` and `ydoit sync-shortcuts` silently skips when
`gi`/Gio is unavailable (no `python3-gobject` system package). This is a lie:

- `find_conflict()` returns `None` (no conflict) instead of signalling it couldn't check
- `sync()` returns a soft error string in `SyncResult.errors` instead of failing hard
- `register_shortcut()` / `unregister_shortcut()` silently no-op

The conflict check is a hard requirement for this application — it must never be skipped.
Dependency verification belongs in the install process (deferred to Phase 3 packaging).

## Design

### Exception Layer

Add `GioNotAvailableError(YdoitError)` to `exceptions.py`. This is a hard dependency
error, distinct from a runtime conflict (which stays as a return value).

### `ShortcutManager` changes

- Add private `_require_gio()`: calls `_check_gio()`, raises `GioNotAvailableError` if False
  - Message: `"Gio.Settings not available — install python3-gobject (system package)"`
- `find_conflict()`: call `_require_gio()` at entry — now unambiguous: returns
  `ConflictInfo | None` or raises; never silently returns `None` due to missing deps
- `sync()`: call `_require_gio()` at entry; add pre-flight conflict check before any
  mutations — iterate entries with keycombos, collect all conflicts, populate
  `SyncResult.errors` and return early (no partial sync) if any found
- `register_shortcut()` / `unregister_shortcut()`: call `_require_gio()` — removes silent no-op

### `_cmd_add` changes

- Remove `--force` argument (no longer needed)
- Call `_require_gio()` (via `sm.find_conflict()`) **before saving** — if Gio unavailable,
  hard fail without writing config
- Conflict found: `_warn(...)` and proceed (downgraded from hard fail)
- Gio unavailable: `_error(...)`, return `EXIT_ERROR`

**Behaviour matrix for `ydoit add --keycombo`:**

| Scenario               | Outcome                        |
|------------------------|--------------------------------|
| Gio unavailable        | Hard fail, no config written   |
| Conflict found         | Warn, proceed, register        |
| No conflict            | Proceed, register              |

### `_cmd_sync_shortcuts` changes

- Wrap `sm.sync(config)` in try/except `GioNotAvailableError` → `_error(...)`, `EXIT_ERROR`
- Conflict in pre-flight: reported via `SyncResult.errors` → existing error path returns
  `EXIT_ERROR` (no change needed in CLI, only in `sync()` internals)

**Behaviour matrix for `ydoit sync-shortcuts`:**

| Scenario               | Outcome                        |
|------------------------|--------------------------------|
| Gio unavailable        | Hard fail                      |
| Any conflict found     | Hard fail, all conflicts reported, no mutations |
| No conflicts           | Sync proceeds normally         |

### Pre-flight conflict check in `sync()`

- Skip entries with no keycombo
- Use `find_conflict(exclude_entry=entry.name)` so ydoit-owned shortcuts don't conflict
  with themselves during re-sync
- Collect all conflicts before returning — full report, not fail-fast

## Tests

- `test_shortcut_manager.py`: `find_conflict()` raises on missing Gio; `sync()` raises on
  missing Gio; pre-flight conflict in `sync()` returns `SyncResult.errors` without mutations
- `test_cli.py`: remove `--force` cases; add Gio-unavailable hard-fail for `add`;
  conflict on `add` → warn+proceed; Gio-unavailable hard-fail for `sync-shortcuts`

## Future

Gio/`python3-gobject` availability check should be enforced at install time in Phase 3
packaging (RPM/DEB). At that point `_check_gio()` may become unreachable dead code.
