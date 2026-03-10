# ydoit v2 — Phase 1: Core Implementation Plan

## Overview

Phase 1 builds the entire headless foundation: everything needed to encrypt/decrypt config, type entries via keyboard shortcuts, and manage GNOME keybindings — all without the GUI. By the end of Phase 1, a user can fully operate ydoit from the CLI and have working shortcuts.

**Duration:** 3 weeks
**Deliverable:** A working CLI tool that can be installed with `pip install -e .` and used end-to-end.

---

## Week 1 — Data Layer & Config Manager

### Goals
Stand up the project skeleton, data model, GPG encryption, v1 migration, and keyring caching. All tested.

### Day 1–2: Project Skeleton & Data Model

**Set up the repo and tooling:**

```
ydoit/
├── src/ydoit/
│   ├── __init__.py          # version string
│   ├── models.py            # dataclasses
│   └── constants.py         # paths, defaults, schema names
├── tests/
│   ├── conftest.py          # shared fixtures
│   └── test_models.py
├── pyproject.toml           # PEP 621, pytest config
├── LICENSE
└── README.md
```

**pyproject.toml setup:**
- Build backend: `setuptools` (simplest for now, switch to meson in Phase 3)
- Dev dependencies: `pytest`, `pytest-cov`, `pytest-tmp-files`
- Entry point: `ydoit = "ydoit.cli:main"`
- Minimum Python: 3.10

**Data model (`models.py`):**

```python
from dataclasses import dataclass, field
from enum import Enum

class EntryType(Enum):
    STRING = "string"
    FILE = "file"

@dataclass
class Entry:
    name: str                          # unique key, e.g. "home1"
    keycombo: str                      # e.g. "Super+F11"
    string: str = ""                   # content to type (if STRING)
    filename: str = ""                 # file to read (if FILE)
    label: str = ""                    # display name
    category: str = "general"          # grouping
    notes: str = ""                    # user memo
    typing_delay_ms: int | None = None # per-entry override
    hold_delay_ms: int | None = None   # per-entry override

    @property
    def entry_type(self) -> EntryType:
        return EntryType.FILE if self.filename else EntryType.STRING

@dataclass
class Settings:
    typing_delay_ms: int = 5
    hold_delay_ms: int = 5
    use_keyring_cache: bool = True
    keyring_timeout_min: int = 15      # 0 = never expire

@dataclass
class Config:
    version: int = 2
    entries: dict[str, Entry] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)
```

**Serialization:** Write `to_dict()` / `from_dict()` classmethods on each dataclass. JSON round-trip must be lossless. Write thorough tests for edge cases (empty strings, special characters, newlines in strings).

**constants.py:**
```python
CONFIG_DIR = Path.home() / ".config" / "ydoit"
DATA_FILE = CONFIG_DIR / "data.json.gpg"
BACKUP_SUFFIX = ".v1.bak"
APP_ID = "org.ydoit.app"
KEYRING_SCHEMA = "org.ydoit.gpg-passphrase"
CUSTOM_KEYBINDING_BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
YDOIT_SHORTCUT_PREFIX = "ydoit:"
```

**Tests:**
- Round-trip serialization for all dataclasses
- Default values
- `entry_type` property logic
- Invalid data handling (missing fields, wrong types)

---

### Day 3–4: Config Manager (GPG Encrypt/Decrypt)

**File:** `src/ydoit/config_manager.py`

**Responsibilities:**
1. Decrypt `data.json.gpg` → parse JSON → return `Config` object
2. Serialize `Config` → encrypt → write `data.json.gpg`
3. Handle first-run (no file exists → return empty `Config`)
4. File permission enforcement (`600` for file, `700` for dir)

**GPG interface — use `subprocess`**, not a Python GPG library. Keeps the dependency list minimal and matches the v1 approach.

```python
class ConfigManager:
    def __init__(self, config_dir: Path = None, passphrase_provider=None):
        self.config_dir = config_dir or constants.CONFIG_DIR
        self.data_file = self.config_dir / "data.json.gpg"
        self._passphrase_provider = passphrase_provider  # injected for testing

    def load(self, passphrase: str = None) -> Config:
        """Decrypt and load config. Returns empty Config if no file exists."""

    def save(self, config: Config, passphrase: str = None) -> None:
        """Encrypt and save config. Creates config dir if needed."""

    def _decrypt(self, passphrase: str) -> str:
        """Run gpg -d --batch --passphrase-fd 0, return plaintext JSON."""

    def _encrypt(self, plaintext: str, passphrase: str) -> None:
        """Run gpg --symmetric --cipher-algo AES256 --batch --passphrase-fd 0."""

    def _ensure_dir(self) -> None:
        """Create config dir with 700 permissions if missing."""

    def _enforce_permissions(self) -> None:
        """Verify and fix file/dir permissions."""

    def exists(self) -> bool:
        """Check if encrypted data file exists."""
```

**Key design decisions:**
- Passphrase passed via `--passphrase-fd 0` (stdin pipe), never via command-line argument (would be visible in `/proc`)
- Use `--batch` and `--yes` flags for non-interactive operation
- Catch `subprocess.CalledProcessError` and raise a custom `DecryptionError` or `EncryptionError` with a user-friendly message
- Temporary plaintext never written to disk — all in-memory via pipes

**Error classes (`exceptions.py`):**
```python
class YdoitError(Exception): ...
class DecryptionError(YdoitError): ...
class EncryptionError(YdoitError): ...
class EntryNotFoundError(YdoitError): ...
class ShortcutConflictError(YdoitError): ...
class YdotoolError(YdoitError): ...
```

**Tests (using tmp_path and monkeypatch):**
- Encrypt → decrypt round-trip with known passphrase
- Load returns empty Config when no file exists
- Load raises DecryptionError on wrong passphrase
- File permissions are enforced after save
- Config dir is created with correct permissions
- Large config files (100+ entries)
- Special characters in strings (unicode, newlines, backslashes)

---

### Day 5: v1 Migration

**File:** `src/ydoit/migration.py`

**Logic:**
```python
def detect_version(data: dict) -> int:
    """Returns 1 if flat format (no 'version' key), else data['version']."""

def migrate_v1_to_v2(data: dict) -> dict:
    """
    v1 format (flat):
      { "home1": { "keycombo": "...", "options": "...", "string": "...", "filename": "..." } }
    
    v2 format (structured):
      { "version": 2, "entries": { "home1": { ... } }, "settings": { ... } }
    
    Transforms:
    - Wrap entries under "entries" key
    - Parse "options" string (e.g. "-d 5 -H 5") into typing_delay_ms / hold_delay_ms
    - Set label = name (as a starting default)
    - Set category = "general"
    - Add version and settings blocks
    """

def parse_v1_options(options: str) -> tuple[int, int]:
    """Parse xdotool-style options: '-d 5 -H 5' → (5, 5)."""
```

**Backup:** Before migration, `ConfigManager` copies `data.json.gpg` to `data.json.gpg.v1.bak`.

**Integration with ConfigManager.load():**
```python
def load(self, passphrase):
    plaintext = self._decrypt(passphrase)
    raw = json.loads(plaintext)
    version = detect_version(raw)
    if version == 1:
        self._backup()
        raw = migrate_v1_to_v2(raw)
        # Save migrated version immediately
        self.save(Config.from_dict(raw), passphrase)
    return Config.from_dict(raw)
```

**Tests:**
- Migrate the exact v1 sample from `data.json` in the project files
- Options parsing: `-d 5 -H 5`, `-d 10`, empty string, malformed
- Backup file is created
- Migrated config round-trips correctly
- Already-v2 config passes through unchanged

---

### Day 6–7: Keyring Manager

**File:** `src/ydoit/keyring_manager.py`

**Uses libsecret via PyGObject** (gi.repository.Secret). No extra pip dependency.

```python
class KeyringManager:
    SCHEMA = Secret.Schema.new(
        constants.KEYRING_SCHEMA,
        Secret.SchemaFlags.NONE,
        {"application": Secret.SchemaAttributeType.STRING}
    )

    def store_passphrase(self, passphrase: str) -> bool:
        """Store passphrase in GNOME Keyring. Returns success."""

    def retrieve_passphrase(self) -> str | None:
        """Retrieve cached passphrase. Returns None if not found."""

    def clear_passphrase(self) -> bool:
        """Remove cached passphrase from keyring."""

    @staticmethod
    def is_available() -> bool:
        """Check if GNOME Keyring / Secret Service is running."""
```

**Timeout handling:** The `keyring_timeout_min` setting is enforced by storing the timestamp alongside the passphrase and checking it on retrieval. A value of 0 means never expire (skip the timestamp check, persist until `clear_passphrase` or session logout).

**Integration with ConfigManager:** The `passphrase_provider` callback injected into `ConfigManager` tries keyring first, falls back to a prompt:

```python
def get_passphrase(keyring: KeyringManager, settings: Settings) -> str:
    if settings.use_keyring_cache and keyring.is_available():
        cached = keyring.retrieve_passphrase()
        if cached:
            return cached
    # Fall back to terminal prompt (CLI) or dialog (GUI, Phase 2)
    passphrase = prompt_passphrase()
    if settings.use_keyring_cache and keyring.is_available():
        keyring.store_passphrase(passphrase)
    return passphrase
```

**Tests:**
- Store and retrieve round-trip (use mock Secret service in CI)
- Retrieve returns None when nothing stored
- Clear removes the passphrase
- Timeout expiry logic (mock timestamps)
- `is_available()` returns False gracefully when no keyring running
- 0-minute timeout never expires

---

## Week 2 — Typing Engine & Shortcut Manager

### Goals
ydotool integration, GNOME keybinding management, and the shortcut conflict resolution logic.

### Day 8–9: Typer (ydotool Integration)

**File:** `src/ydoit/typer.py`

**Responsibilities:** Take a string (or file path) and type it out via ydotool.

```python
class Typer:
    def __init__(self, typing_delay_ms: int = 5, hold_delay_ms: int = 5):
        self.typing_delay_ms = typing_delay_ms
        self.hold_delay_ms = hold_delay_ms

    def type_string(self, text: str) -> None:
        """Type a string using ydotool type."""

    def type_file(self, filepath: Path) -> None:
        """Read file contents and type them."""

    def type_entry(self, entry: Entry, default_settings: Settings) -> None:
        """Type an entry, using per-entry or default delays."""

    @staticmethod
    def check_daemon() -> bool:
        """Check if ydotoold is running."""

    @staticmethod
    def check_permissions() -> bool:
        """Check if current user can write to /dev/uinput."""
```

**ydotool command mapping:**
```bash
# Type a string with delay
ydotool type --key-delay <ms> --key-hold <ms> -- "<text>"

# Note: ydotool type reads from argument, not stdin
# For long strings or strings with special chars, use --file (if available)
# or chunk the input
```

**Edge cases to handle:**
- Newline characters (`\n`) in strings — ydotool handles these as Enter key
- Empty string entries (skip silently)
- File not found → raise `YdoitError` with clear message
- ydotoold not running → raise `YdotoolError` with instructions to start it
- Very long strings → chunk into segments to avoid argument length limits
- Special characters (tabs, unicode) — test ydotool behavior and document limitations

**Tests:**
- `type_string` calls ydotool with correct arguments (mock subprocess)
- `type_file` reads file and passes to `type_string`
- `type_entry` selects string vs file correctly
- Per-entry delay overrides default settings
- Missing file raises appropriate error
- Daemon check logic
- Permission check logic

---

### Day 10–12: Shortcut Manager

**File:** `src/ydoit/shortcut_manager.py`

This is the most complex module in Phase 1. It manages the bidirectional sync between ydoit entries and GNOME custom keybindings.

```python
@dataclass
class GnomeShortcut:
    path: str          # e.g. "/org/.../custom-keybindings/custom5/"
    name: str          # e.g. "ydoit: Home Password"
    command: str       # e.g. "ydoit type home1"
    binding: str       # e.g. "<Super>F11"

class ShortcutManager:
    def __init__(self):
        self._schema = "org.gnome.settings-daemon.plugins.media-keys"
        self._base_path = constants.CUSTOM_KEYBINDING_BASE

    # --- Read operations ---

    def get_all_custom_shortcuts(self) -> list[GnomeShortcut]:
        """Read all GNOME custom keybindings."""

    def get_ydoit_shortcuts(self) -> list[GnomeShortcut]:
        """Filter to ydoit-owned shortcuts (name starts with 'ydoit:')."""

    def get_non_ydoit_shortcuts(self) -> list[GnomeShortcut]:
        """All custom shortcuts NOT owned by ydoit."""

    def get_builtin_shortcuts(self) -> dict[str, str]:
        """Read built-in GNOME shortcuts (for conflict detection)."""

    # --- Conflict detection ---

    def find_conflict(self, keycombo: str, exclude_entry: str = None) 
            -> GnomeShortcut | tuple[str, str] | None:
        """
        Check if keycombo conflicts with any existing shortcut.
        Returns:
          - GnomeShortcut if conflicts with a custom shortcut
          - (schema_key, description) if conflicts with a built-in shortcut
          - None if no conflict
        Excludes the named entry from the check (for updates).
        """

    # --- Write operations ---

    def sync(self, config: Config) -> SyncResult:
        """
        Full sync: make GNOME shortcuts match config entries.
        Returns SyncResult with added/updated/removed counts.
        """

    def register_shortcut(self, entry: Entry) -> None:
        """Add or update a single GNOME shortcut for an entry."""

    def unregister_shortcut(self, entry_name: str) -> None:
        """Remove GNOME shortcut for an entry."""

    def clear_all_ydoit_shortcuts(self) -> int:
        """Remove all ydoit shortcuts. Returns count removed."""

    # --- Format conversion ---

    @staticmethod
    def to_gnome_binding(keycombo: str) -> str:
        """'Super+F11' → '<Super>F11'"""

    @staticmethod
    def from_gnome_binding(binding: str) -> str:
        """'<Super>F11' → 'Super+F11'"""

    @staticmethod
    def make_command(entry_name: str) -> str:
        """'home1' → 'ydoit type home1'"""
```

**gsettings interaction — use `Gio.Settings` via PyGObject**, not subprocess calls to `gsettings`. This is faster, handles types correctly, and works within the GTK event loop (important for Phase 2).

```python
from gi.repository import Gio

# Read the master keybinding list
settings = Gio.Settings.new(self._schema)
paths = settings.get_strv("custom-keybindings")

# Read a specific shortcut
shortcut_settings = Gio.Settings.new_with_path(
    self._schema + ".custom-keybinding",
    path
)
name = shortcut_settings.get_string("name")
command = shortcut_settings.get_string("command")
binding = shortcut_settings.get_string("binding")
```

**Sync algorithm:**

```
1. current_ydoit = get_ydoit_shortcuts()  → dict[entry_name → GnomeShortcut]
2. desired = config.entries                → dict[entry_name → Entry]

3. to_add    = desired.keys() - current_ydoit.keys()
4. to_remove = current_ydoit.keys() - desired.keys()
5. to_update = {name for name in desired.keys() & current_ydoit.keys()
                if shortcut_differs(current_ydoit[name], desired[name])}

6. For each in to_remove: delete the dconf path, remove from master list
7. For each in to_add: find next free customN slot, write name/command/binding, add to master list
8. For each in to_update: update binding and/or command in place

9. Write updated master list
```

**Conflict resolution data (for GUI in Phase 2, exposed now for CLI):**
```python
@dataclass
class ConflictInfo:
    keycombo: str
    existing_name: str         # what currently holds this binding
    existing_source: str       # "ydoit", "custom", or "builtin"
    existing_path: str | None  # dconf path if custom/ydoit
```

**Key combo format translation table:**

| User input | GNOME binding |
|---|---|
| `Super+F11` | `<Super>F11` |
| `Ctrl+Alt+P` | `<Primary><Alt>p` |
| `Shift+Super+S` | `<Shift><Super>s` |
| `Ctrl+Shift+1` | `<Primary><Shift>1` |

Note: GNOME uses `<Primary>` not `<Ctrl>`. Alpha keys are lowercase in bindings.

**Tests:**
- `to_gnome_binding` / `from_gnome_binding` round-trip for all modifier combos
- Sync adds new shortcuts correctly
- Sync removes deleted shortcuts
- Sync updates changed bindings
- Sync is idempotent (running twice produces same state)
- Conflict detection finds ydoit-owned conflicts
- Conflict detection finds non-ydoit custom conflicts
- Conflict detection finds built-in shortcut conflicts
- `clear_all_ydoit_shortcuts` removes all and only ydoit shortcuts
- Free slot allocation skips occupied customN paths (even non-ydoit ones)

**Testing strategy:** Use a temporary dconf profile via `DCONF_PROFILE` env var so tests don't touch the real desktop. Set up in `conftest.py`:

```python
@pytest.fixture
def isolated_dconf(tmp_path, monkeypatch):
    """Run tests against an isolated dconf database."""
    profile = tmp_path / "profile"
    profile.write_text(f"user-db:file={tmp_path / 'user'}\n")
    monkeypatch.setenv("DCONF_PROFILE", str(profile))
    yield
```

---

## Week 3 — CLI & Integration

### Goals
Wire everything together with a polished CLI, integration tests, and developer docs.

### Day 13–14: CLI Dispatcher

**File:** `src/ydoit/cli.py`

**Uses `argparse`** with subcommands. Clean, colored terminal output via ANSI codes (no external dependency).

```python
def main():
    parser = argparse.ArgumentParser(
        prog="ydoit",
        description="Keyboard shortcut auto-typer for GNOME/Wayland"
    )
    subparsers = parser.add_subparsers(dest="command")

    # ydoit type <name>
    type_parser = subparsers.add_parser("type", help="Type an entry")
    type_parser.add_argument("name", help="Entry name to type")

    # ydoit list
    subparsers.add_parser("list", help="List all entries")

    # ydoit add <name>
    add_parser = subparsers.add_parser("add", help="Add a new entry")
    add_parser.add_argument("name", help="Entry name")
    add_parser.add_argument("--keycombo", required=True)
    add_parser.add_argument("--string", default="")
    add_parser.add_argument("--file", default="", dest="filename")
    add_parser.add_argument("--label", default="")
    add_parser.add_argument("--category", default="general")

    # ydoit remove <name>
    remove_parser = subparsers.add_parser("remove", help="Remove an entry")
    remove_parser.add_argument("name")
    remove_parser.add_argument("--yes", action="store_true", help="Skip confirmation")

    # ydoit sync-shortcuts
    subparsers.add_parser("sync-shortcuts", help="Sync GNOME keybindings")

    # ydoit export
    export_parser = subparsers.add_parser("export", help="Export config")
    export_parser.add_argument("file", help="Output file path")
    export_parser.add_argument("--plain", action="store_true")

    # ydoit import
    import_parser = subparsers.add_parser("import", help="Import config")
    import_parser.add_argument("file", help="Input file path")

    # ydoit status
    subparsers.add_parser("status", help="Show system status")

    # ydoit version
    subparsers.add_parser("version", help="Print version")

    args = parser.parse_args()
    # dispatch to handler functions...
```

**Command implementations:**

| Command | Flow |
|---|---|
| `type <n>` | get passphrase → decrypt → find entry → type via ydotool |
| `list` | get passphrase → decrypt → print table of entries |
| `add <n>` | get passphrase → decrypt → validate no duplicate → check shortcut conflict → add entry → save → sync shortcuts |
| `remove <n>` | get passphrase → decrypt → confirm → remove → save → sync shortcuts |
| `sync-shortcuts` | get passphrase → decrypt → sync all shortcuts → print report |
| `export` | get passphrase → decrypt → write JSON (plain or re-encrypted) |
| `import` | read file → decrypt if needed → merge or replace → save → sync shortcuts |
| `status` | check ydotoold, check /dev/uinput, check config file, check keyring |
| `version` | print version string |

**`status` output example:**
```
ydoit v2.0.0

Config:   ~/.config/ydoit/data.json.gpg (exists, 3 entries)
ydotoold: running (pid 1234)
uinput:   accessible (/dev/uinput)
Keyring:  available (passphrase cached)
Shortcuts: 3 registered, 0 stale
```

**`list` output example:**
```
Name        Label                  Shortcut     Type
──────────────────────────────────────────────────────
home1       Home Password          Super+F11    string
setnet      Network Setup Script   Super+F8     file
tmpfile     tmpfile                Super+F9     file
```

**Exit codes:**
- 0: success
- 1: general error
- 2: decryption failed (wrong passphrase)
- 3: ydotoold not running
- 4: entry not found
- 5: shortcut conflict (on add, unless user confirms reassignment)

---

### Day 15–16: Integration Tests

**File:** `tests/test_integration.py`

End-to-end tests that exercise the full stack (minus actual ydotool keystrokes — those are mocked at the subprocess boundary).

**Test scenarios:**

1. **Fresh start:** No config exists → `add` creates config dir, encrypts, registers shortcut
2. **Full lifecycle:** Add → list → type → modify → remove → verify cleanup
3. **v1 migration:** Place a v1-format encrypted file → load → verify v2 structure + backup
4. **Shortcut sync:** Add 5 entries → verify 5 GNOME shortcuts → remove 2 → verify 3 remain → verify no stale shortcuts
5. **Conflict handling:** Add entry with Super+F5 → add second entry with Super+F5 → verify conflict error with info
6. **Export/import round-trip:** Export plain → wipe → import → verify identical
7. **Concurrent access:** Simulate two CLI invocations — verify file locking or graceful error
8. **Error recovery:** Corrupt the GPG file → verify helpful error message
9. **Passphrase change:** Export → re-encrypt with new passphrase → verify load works

**Test infrastructure:**
- All tests use `tmp_path` for config directory
- Isolated dconf profile (no real desktop changes)
- Mock `ydotool` subprocess calls — verify correct arguments passed
- Mock `getpass.getpass` for passphrase input
- Test fixture that creates a pre-populated v1 config

---

### Day 17: Error Handling & Edge Cases

Harden all modules against real-world conditions:

- **GPG not installed:** Detect at startup, clear error message
- **ydotoold stops mid-type:** Catch and report, don't leave config unlocked
- **Disk full on save:** Atomic write (write to `.tmp`, rename) so we never corrupt the existing file
- **Interrupted migration:** Ensure backup exists before overwriting
- **Unicode in entry names:** Validate entry names are ASCII alphanumeric + underscore (CLI-friendly)
- **File locking:** Use `fcntl.flock` on the `.gpg` file during write to prevent concurrent corruption

**Atomic save pattern:**
```python
def save(self, config, passphrase):
    tmp_file = self.data_file.with_suffix(".gpg.tmp")
    self._encrypt(config.to_json(), passphrase, output=tmp_file)
    tmp_file.rename(self.data_file)  # atomic on same filesystem
    self._enforce_permissions()
```

---

### Day 18–19: Developer Documentation & Cleanup

**Files to write:**

1. **README.md** — project overview, quick start for developers, architecture diagram
2. **docs/CONTRIBUTING.md** — how to set up a dev environment:
   ```bash
   git clone ...
   cd ydoit
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   pytest
   ```
3. **docs/ARCHITECTURE.md** — module dependency graph, data flow, design decisions
4. **Inline docstrings** — every public method gets a docstring
5. **Type hints** — full type annotations, verify with `mypy --strict`

**Code quality pass:**
- Run `ruff` linter, fix all issues
- Run `mypy --strict`, fix type errors
- Verify test coverage ≥ 90% on core modules
- Review all TODO/FIXME comments

---

## Phase 1 Exit Criteria

Before moving to Phase 2 (GUI), all of the following must be true:

| # | Criterion | Verification |
|---|---|---|
| 1 | `ydoit add` creates encrypted entry and registers GNOME shortcut | Manual test on Fedora 42 |
| 2 | `ydoit type` decrypts and types via ydotool on Wayland | Manual test in GNOME/Wayland session |
| 3 | `ydoit list` shows all entries with correct info | Automated test |
| 4 | `ydoit remove` cleans up entry and GNOME shortcut | Automated test |
| 5 | `ydoit sync-shortcuts` makes GNOME match config | Automated test |
| 6 | `ydoit status` reports system health accurately | Manual test |
| 7 | v1 config file is auto-migrated on first load | Automated test with sample data |
| 8 | Keyring caching stores/retrieves/expires passphrase | Automated test (mocked keyring in CI) |
| 9 | Shortcut conflicts are detected and reported | Automated test |
| 10 | All unit tests pass | `pytest` green |
| 11 | Integration tests pass | `pytest tests/test_integration.py` green |
| 12 | Test coverage ≥ 90% on src/ydoit/ | `pytest --cov` |
| 13 | Type checking passes | `mypy --strict src/` |
| 14 | Linting passes | `ruff check src/ tests/` |
| 15 | Developer can set up and run from README alone | Peer review |

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| ydotool type has character escaping bugs | Typed output is garbled | Build a test harness that types into a text editor and verifies via clipboard; document known limitations |
| gsettings API differs between GNOME versions | Shortcuts don't register on some distros | Test on GNOME 44, 45, 46; use version detection if needed |
| libsecret not available in headless CI | Keyring tests fail | Mock Secret service; run real keyring tests only in VM-based CI |
| GPG passphrase via stdin fails on some gpg-agent configs | Decryption fails | Use `--pinentry-mode loopback` flag; document gpg-agent config requirements |
| dconf isolation in tests is imperfect | Tests pollute desktop shortcuts | Use dedicated `DCONF_PROFILE`; CI runs in containers with no GNOME session |
