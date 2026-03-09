# Mandatory Shortcut Conflict Check Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the GNOME shortcut conflict check a hard requirement — `GioNotAvailableError` replaces silent skip; `ydoit add` warns on conflict and proceeds; `ydoit sync-shortcuts` hard-fails on conflict.

**Architecture:** Add `GioNotAvailableError` to `exceptions.py`. Add `_require_gio()` to `ShortcutManager` that raises it. Update `find_conflict()`, `sync()`, `register_shortcut()`, `unregister_shortcut()`, and `clear_all_ydoit_shortcuts()` to call `_require_gio()` instead of silently returning empty/zero. Add pre-flight conflict check to `sync()`. Update CLI to handle the exception and remove `--force`.

**Tech Stack:** Python, pytest, `gi`/Gio (PyGObject), argparse, unittest.mock

**All commands run from:** `ydoit-phase1/ydoit/`

---

### Task 1: Add `GioNotAvailableError` and `_require_gio()`

**Files:**
- Modify: `src/ydoit/exceptions.py` (after line 77)
- Modify: `src/ydoit/shortcut_manager.py:87-99` (`_check_gio` section)
- Modify: `tests/test_shortcut_manager.py` (imports + new `TestRequireGio` class)

**Step 1: Write the failing test**

Add to `tests/test_shortcut_manager.py` — update the import line at the top to add `GioNotAvailableError`:
```python
from ydoit.exceptions import GioNotAvailableError
```

Add a new test class after `TestCheckGio` (around line 300):
```python
class TestRequireGio:
    """Tests for ShortcutManager._require_gio."""

    def test_raises_when_gio_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "gi", None)
        mgr = ShortcutManager()
        with pytest.raises(GioNotAvailableError):
            mgr._require_gio()

    def test_does_not_raise_when_gio_available(
        self, mock_gio: mock.MagicMock
    ) -> None:
        mgr = ShortcutManager()
        mgr._gio_available = True
        mgr._require_gio()  # must not raise
```

**Step 2: Run test to confirm it fails**

```bash
pytest tests/test_shortcut_manager.py::TestRequireGio -v
```
Expected: `ImportError` or `AttributeError` — `GioNotAvailableError` does not exist yet.

**Step 3: Add `GioNotAvailableError` to `exceptions.py`**

Append after the `GpgNotFoundError` class at line 77:
```python
class GioNotAvailableError(YdoitError):
    """Gio.Settings is not available (python3-gobject not installed)."""

    def __init__(self) -> None:
        super().__init__(
            "Gio.Settings not available — install python3-gobject (system package). "
            "Fedora: sudo dnf install python3-gobject  "
            "Ubuntu: sudo apt install python3-gi"
        )
```

**Step 4: Add `_require_gio()` to `ShortcutManager`**

In `src/ydoit/shortcut_manager.py`, add the import at the top of the class section. The method goes directly after `_check_gio()` (after line 99):

First, add the import at the top of `shortcut_manager.py` — add to the existing imports from ydoit:
```python
from ydoit.exceptions import GioNotAvailableError
```

Then add the method after `_check_gio()`:
```python
def _require_gio(self) -> None:
    """Raise GioNotAvailableError if Gio.Settings is not available."""
    if not self._check_gio():
        raise GioNotAvailableError()
```

**Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_shortcut_manager.py::TestRequireGio -v
```
Expected: 2 passed.

**Step 6: Run full suite to confirm no regressions**

```bash
pytest --cov --cov-report=term-missing -q
```
Expected: all pass, coverage ≥ 90%.

**Step 7: Commit**

```bash
git add src/ydoit/exceptions.py src/ydoit/shortcut_manager.py tests/test_shortcut_manager.py
git commit -m "feat: add GioNotAvailableError and ShortcutManager._require_gio()"
```

---

### Task 2: Make `find_conflict()` require Gio

**Files:**
- Modify: `src/ydoit/shortcut_manager.py:154-193` (`find_conflict`)
- Modify: `tests/test_shortcut_manager.py:643-651` (`test_returns_none_when_gio_unavailable_for_builtins`)

**Step 1: Update the existing "Gio unavailable" test to expect an exception**

Replace the test at lines 643–651:
```python
# OLD — delete this:
def test_returns_none_when_gio_unavailable_for_builtins(
    self, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "gi", None)
    mgr = ShortcutManager()
    result = mgr.find_conflict("Super+F11")
    assert result is None

# NEW — replace with:
def test_raises_when_gio_unavailable(
    self, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "gi", None)
    mgr = ShortcutManager()
    with pytest.raises(GioNotAvailableError):
        mgr.find_conflict("Super+F11")
```

**Step 2: Run to confirm test now fails**

```bash
pytest tests/test_shortcut_manager.py::TestFindConflict::test_raises_when_gio_unavailable -v
```
Expected: FAIL — `find_conflict` returns `None` instead of raising.

**Step 3: Update `find_conflict()` to call `_require_gio()`**

In `src/ydoit/shortcut_manager.py`, update `find_conflict()` — add `self._require_gio()` as the first line of the method body (line 166, before `gnome_binding = ...`):
```python
def find_conflict(
    self, keycombo: str, exclude_entry: str | None = None
) -> ConflictInfo | None:
    """Check if a key combo conflicts with any existing shortcut.
    ...
    """
    self._require_gio()
    gnome_binding = self.to_gnome_binding(keycombo)
    # ... rest unchanged
```

**Step 4: Run test to confirm it passes**

```bash
pytest tests/test_shortcut_manager.py::TestFindConflict -v
```
Expected: all pass.

**Step 5: Run full suite**

```bash
pytest --cov --cov-report=term-missing -q
```
Expected: all pass, coverage ≥ 90%.

**Step 6: Commit**

```bash
git add src/ydoit/shortcut_manager.py tests/test_shortcut_manager.py
git commit -m "feat: find_conflict() raises GioNotAvailableError instead of returning None"
```

---

### Task 3: Make write methods require Gio

These three methods currently silently no-op when Gio is missing: `register_shortcut()`, `unregister_shortcut()`, `clear_all_ydoit_shortcuts()`.

**Files:**
- Modify: `src/ydoit/shortcut_manager.py` (three methods)
- Modify: `tests/test_shortcut_manager.py` (three existing "does nothing" tests)

**Step 1: Update the three existing "Gio unavailable" tests**

In `TestRegisterShortcut` (line 662–666), replace:
```python
def test_does_nothing_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    entry = make_entry()
    mgr.register_shortcut(entry)  # must not raise
```
With:
```python
def test_raises_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    entry = make_entry()
    with pytest.raises(GioNotAvailableError):
        mgr.register_shortcut(entry)
```

In `TestUnregisterShortcut` (line 739–742), replace:
```python
def test_does_nothing_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    mgr.unregister_shortcut("home1")  # must not raise
```
With:
```python
def test_raises_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    with pytest.raises(GioNotAvailableError):
        mgr.unregister_shortcut("home1")
```

In `TestClearAllYdoitShortcuts` (line 793–796), replace:
```python
def test_returns_zero_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    assert mgr.clear_all_ydoit_shortcuts() == 0
```
With:
```python
def test_raises_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    with pytest.raises(GioNotAvailableError):
        mgr.clear_all_ydoit_shortcuts()
```

**Step 2: Run to confirm three tests now fail**

```bash
pytest tests/test_shortcut_manager.py::TestRegisterShortcut::test_raises_when_gio_unavailable \
       tests/test_shortcut_manager.py::TestUnregisterShortcut::test_raises_when_gio_unavailable \
       tests/test_shortcut_manager.py::TestClearAllYdoitShortcuts::test_raises_when_gio_unavailable -v
```
Expected: 3 FAIL.

**Step 3: Update the three methods in `shortcut_manager.py`**

`register_shortcut()` (lines 302–309): replace `if not self._check_gio(): return` with `self._require_gio()`:
```python
def register_shortcut(self, entry: Entry) -> None:
    self._require_gio()

    if not entry.keycombo:
        return
    # ... rest unchanged
```

`unregister_shortcut()` (lines 329–336): same pattern:
```python
def unregister_shortcut(self, entry_name: str) -> None:
    self._require_gio()

    for shortcut in self.get_ydoit_shortcuts():
        # ... rest unchanged
```

`clear_all_ydoit_shortcuts()` (lines 343–350): same pattern:
```python
def clear_all_ydoit_shortcuts(self) -> int:
    self._require_gio()

    count = 0
    # ... rest unchanged
```

**Step 4: Run the three tests to confirm they pass**

```bash
pytest tests/test_shortcut_manager.py::TestRegisterShortcut \
       tests/test_shortcut_manager.py::TestUnregisterShortcut \
       tests/test_shortcut_manager.py::TestClearAllYdoitShortcuts -v
```
Expected: all pass.

**Step 5: Run full suite**

```bash
pytest --cov --cov-report=term-missing -q
```
Expected: all pass, coverage ≥ 90%.

**Step 6: Commit**

```bash
git add src/ydoit/shortcut_manager.py tests/test_shortcut_manager.py
git commit -m "feat: register/unregister/clear_all raise GioNotAvailableError instead of silently no-oping"
```

---

### Task 4: Make `sync()` require Gio + add pre-flight conflict check

**Files:**
- Modify: `src/ydoit/shortcut_manager.py:241-300` (`sync`)
- Modify: `tests/test_shortcut_manager.py:899-905` + new tests in `TestSync`

**Step 1: Update the "Gio unavailable" test for `sync()`**

Replace the test at lines 899–905:
```python
# OLD:
def test_returns_error_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    config = make_config()
    result = mgr.sync(config)
    assert len(result.errors) > 0
    assert result.total_changes == 0

# NEW:
def test_raises_when_gio_unavailable(self) -> None:
    mgr = ShortcutManager()
    mgr._gio_available = False
    config = make_config()
    with pytest.raises(GioNotAvailableError):
        mgr.sync(config)
```

**Step 2: Add pre-flight conflict test**

Add after `test_raises_when_gio_unavailable` in `TestSync`:
```python
def test_preflight_conflict_returns_errors_without_mutating(
    self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
) -> None:
    """Pre-flight detects conflict; sync returns errors and makes no changes."""
    mgr, gio = manager_with_gio
    # Existing non-ydoit shortcut already holds <Super>F11
    media_keys_mock = self._setup(
        gio,
        [
            {
                "path": f"{BASE_PATH}/custom0/",
                "name": "Screenshot Tool",
                "command": "/usr/bin/scrot.sh",
                "binding": "<Super>F11",
            }
        ],
    )
    # Schema source returns None so builtin check finds nothing
    gio.SettingsSchemaSource.get_default.return_value = None

    config = make_config(make_entry("home1", "Super+F11", "Home Password"))
    result = mgr.sync(config)

    assert len(result.errors) == 1
    assert "home1" in result.errors[0]
    assert result.total_changes == 0
    # No shortcuts were added
    media_keys_mock.set_strv.assert_not_called()

def test_preflight_skips_entries_without_keycombo(
    self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
) -> None:
    """Entries with no keycombo are excluded from conflict pre-flight."""
    mgr, gio = manager_with_gio
    self._setup(gio, [])
    gio.SettingsSchemaSource.get_default.return_value = None

    config = make_config(Entry(name="nokey", keycombo="", string="hello"))
    result = mgr.sync(config)

    assert not result.errors

def test_preflight_excludes_own_existing_shortcut(
    self, manager_with_gio: tuple[ShortcutManager, mock.MagicMock]
) -> None:
    """Re-syncing an entry that already owns its shortcut does not self-conflict."""
    mgr, gio = manager_with_gio
    self._setup(
        gio,
        [
            {
                "path": f"{BASE_PATH}/custom0/",
                "name": "ydoit: Home Password",
                "command": "ydoit type home1",
                "binding": "<Super>F11",
            }
        ],
    )
    gio.SettingsSchemaSource.get_default.return_value = None

    config = make_config(make_entry("home1", "Super+F11", "Home Password"))
    result = mgr.sync(config)

    assert not result.errors
```

**Step 3: Run to confirm new/updated tests fail**

```bash
pytest tests/test_shortcut_manager.py::TestSync::test_raises_when_gio_unavailable \
       tests/test_shortcut_manager.py::TestSync::test_preflight_conflict_returns_errors_without_mutating \
       tests/test_shortcut_manager.py::TestSync::test_preflight_skips_entries_without_keycombo \
       tests/test_shortcut_manager.py::TestSync::test_preflight_excludes_own_existing_shortcut -v
```
Expected: FAIL (`test_raises_when_gio_unavailable` fails because sync returns `SyncResult` instead of raising; pre-flight tests fail because pre-flight doesn't exist).

**Step 4: Update `sync()` in `shortcut_manager.py`**

Replace lines 252–253 (`if not self._check_gio():` block) and insert pre-flight after the `desired` assignment:

```python
def sync(self, config: Config) -> SyncResult:
    """Sync GNOME shortcuts to match config entries.
    ...
    """
    self._require_gio()

    result = SyncResult()
    current = {s.entry_name: s for s in self.get_ydoit_shortcuts() if s.entry_name}
    desired = config.entries

    # Pre-flight: check all keyed entries for conflicts before any mutations
    for entry_name, entry in desired.items():
        if not entry.keycombo:
            continue
        conflict = self.find_conflict(entry.keycombo, exclude_entry=entry_name)
        if conflict:
            result.errors.append(
                f"Shortcut {entry.keycombo!r} for {entry_name!r} conflicts with "
                f"{conflict.existing_source} shortcut {conflict.existing_name!r}"
            )
    if result.errors:
        return result

    # Remove stale shortcuts
    # ... rest of method unchanged from original line 260
```

**Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_shortcut_manager.py::TestSync -v
```
Expected: all pass.

**Step 6: Run full suite**

```bash
pytest --cov --cov-report=term-missing -q
```
Expected: all pass, coverage ≥ 90%.

**Step 7: Commit**

```bash
git add src/ydoit/shortcut_manager.py tests/test_shortcut_manager.py
git commit -m "feat: sync() raises GioNotAvailableError and adds pre-flight conflict check"
```

---

### Task 5: Update `_cmd_add` (CLI)

Remove `--force`, make Gio unavailability a hard fail before saving, downgrade conflict to warning.

**Files:**
- Modify: `src/ydoit/cli.py` (imports, `_cmd_add`, `build_parser`)
- Modify: `tests/test_cli.py` (imports, `TestBuildParser`, `TestCmdAdd`)

**Step 1: Update CLI tests**

Add `GioNotAvailableError` to the import in `tests/test_cli.py` (line 13–18):
```python
from ydoit.exceptions import (
    DecryptionError,
    GioNotAvailableError,
    GpgNotFoundError,
    YdoitError,
    YdotoolError,
)
```

In `TestBuildParser`, remove `test_add_force_flag` entirely (lines 142–145).

In `TestCmdAdd`, replace `test_shortcut_conflict_no_force` and `test_shortcut_conflict_with_force` (lines 426–451) with:
```python
def test_shortcut_conflict_proceeds_with_warning(
    self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Conflict is warned but add proceeds."""
    conflict = ConflictInfo(
        keycombo="Super+F1",
        existing_name="other_entry",
        existing_source="ydoit",
    )
    sm = _make_sm(conflict=conflict)
    self._setup_add(monkeypatch, Config(), sm=sm)
    result = main(["add", "newentry", "--keycombo", "Super+F1", "--string", "hello"])
    assert result == constants.EXIT_OK
    err = capsys.readouterr().err
    assert "conflicts" in err.lower() or "conflict" in err.lower()

def test_gio_unavailable_fails_before_save(
    self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """When Gio is unavailable, add fails before writing config."""
    sm = _make_sm()
    sm.find_conflict.side_effect = GioNotAvailableError()
    cm = self._setup_add(monkeypatch, Config(), sm=sm)
    result = main(["add", "newentry", "--keycombo", "Super+F1", "--string", "hello"])
    assert result == constants.EXIT_ERROR
    cm.save.assert_not_called()
```

**Step 2: Run to confirm new tests fail**

```bash
pytest tests/test_cli.py::TestCmdAdd::test_shortcut_conflict_proceeds_with_warning \
       tests/test_cli.py::TestCmdAdd::test_gio_unavailable_fails_before_save -v
```
Expected: FAIL.

**Step 3: Update `src/ydoit/cli.py`**

Add `GioNotAvailableError` to the imports block (lines 17–24):
```python
from ydoit.exceptions import (
    DecryptionError,
    EntryNotFoundError,
    GioNotAvailableError,
    GpgNotFoundError,
    InvalidEntryNameError,
    YdoitError,
    YdotoolError,
)
```

Replace the conflict-check block in `_cmd_add` (lines 219–231) with:
```python
# Check for shortcut conflict — must happen before saving
if args.keycombo:
    sm = ShortcutManager()
    try:
        conflict = sm.find_conflict(args.keycombo)
    except GioNotAvailableError as e:
        _error(str(e))
        return constants.EXIT_ERROR
    if conflict:
        _warn(
            f"Shortcut {args.keycombo!r} conflicts with "
            f"{conflict.existing_source} shortcut {conflict.existing_name!r}"
            " — registering anyway"
        )
```

Replace the shortcut registration block (lines 247–251) — reuse the `sm` already created above, remove the redundant `sm = ShortcutManager()`:
```python
# Sync shortcuts
if entry.keycombo:
    sm.register_shortcut(entry)
    _info(f"Registered shortcut {entry.keycombo}")
```

Remove `--force` from `build_parser` (lines 473–475):
```python
# DELETE these lines:
add_p.add_argument(
    "--force", action="store_true", help="Force reassignment on shortcut conflict"
)
```

**Step 4: Run updated tests to confirm they pass**

```bash
pytest tests/test_cli.py::TestCmdAdd tests/test_cli.py::TestBuildParser -v
```
Expected: all pass (old `--force` tests gone, new tests pass).

**Step 5: Run full suite**

```bash
pytest --cov --cov-report=term-missing -q
```
Expected: all pass, coverage ≥ 90%.

**Step 6: Commit**

```bash
git add src/ydoit/cli.py tests/test_cli.py
git commit -m "feat: ydoit add -- remove --force, conflict is warning, Gio missing is hard fail before save"
```

---

### Task 6: Update `_cmd_sync_shortcuts` (CLI)

**Files:**
- Modify: `src/ydoit/cli.py:290-310` (`_cmd_sync_shortcuts`)
- Modify: `tests/test_cli.py:581-630` (`TestCmdSyncShortcuts`)

**Step 1: Add test for Gio unavailable in sync-shortcuts**

Add to `TestCmdSyncShortcuts` (after `test_sync_with_errors`):
```python
def test_gio_unavailable_fails_hard(
    self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    sample_config: Config
) -> None:
    """When Gio is unavailable, sync-shortcuts hard-fails."""
    from ydoit.exceptions import GioNotAvailableError
    sm = _make_sm()
    sm.sync.side_effect = GioNotAvailableError()
    self._setup_sync(monkeypatch, exists=True, config=sample_config, sm=sm)
    result = main(["sync-shortcuts"])
    assert result == constants.EXIT_ERROR
    err = capsys.readouterr().err
    assert "Gio" in err or "python3-gobject" in err
```

**Step 2: Run to confirm it fails**

```bash
pytest tests/test_cli.py::TestCmdSyncShortcuts::test_gio_unavailable_fails_hard -v
```
Expected: FAIL — `GioNotAvailableError` propagates uncaught and the test sees an exception instead of `EXIT_ERROR`.

**Step 3: Update `_cmd_sync_shortcuts` in `cli.py`**

Wrap `sm.sync(config)` with a try/except:
```python
def _cmd_sync_shortcuts(args: argparse.Namespace) -> int:
    """Handle 'ydoit sync-shortcuts'."""
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider())

    if not cm.exists():
        _warn("No config file found.")
        return constants.EXIT_OK

    config = cm.load()
    sm = ShortcutManager()
    try:
        result = sm.sync(config)
    except GioNotAvailableError as e:
        _error(str(e))
        return constants.EXIT_ERROR

    if result.total_changes == 0 and not result.errors:
        _info("Shortcuts are in sync")
    else:
        _info(f"Sync complete: {result}")

    for error in result.errors:
        _error(error)

    return constants.EXIT_OK if not result.errors else constants.EXIT_ERROR
```

**Step 4: Run test to confirm it passes**

```bash
pytest tests/test_cli.py::TestCmdSyncShortcuts -v
```
Expected: all pass.

**Step 5: Run full suite**

```bash
pytest --cov --cov-report=term-missing -q
```
Expected: all pass, coverage ≥ 90%.

**Step 6: Commit**

```bash
git add src/ydoit/cli.py tests/test_cli.py
git commit -m "feat: sync-shortcuts hard-fails when Gio is unavailable"
```

---

## Final Verification

```bash
pytest --cov --cov-report=term-missing -q
ruff check src/ tests/
```

All tests pass, coverage ≥ 90%, no lint errors.
