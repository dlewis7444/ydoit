# ydoit v2 — Application Plan

## 1. Executive Summary

**ydoit** is a GNOME utility that maps keyboard shortcuts to auto-type actions — typing out strings, passwords, or file contents on demand. The current version is a pair of shell scripts managing a GPG-encrypted JSON config and using `xdotool` for keystroke simulation.

**ydoit v2** is a full rewrite as a modern, packaged Linux desktop app with:

- A polished GTK4/libadwaita GUI for managing entries
- Wayland-native input simulation via `ydotool`
- Automatic GNOME custom-keybinding registration via `dconf`/`gsettings`
- Encryption at rest via GPG symmetric (AES-256), with optional GNOME Keyring integration for passphrase caching
- Distribution as RPM, DEB, and Flatpak

---

## 2. Technology Choices & Rationale

### 2.1 Language: Python 3.10+

**Why:** Python is the de facto language for GNOME desktop tooling. PyGObject bindings are first-class, well-documented, and let us use GTK4 + libadwaita directly. The entire GNOME ecosystem (GNOME Settings, GNOME Tweaks, etc.) is built this way. Packaging for RPM/DEB/Flatpak is straightforward with Python.

### 2.2 UI Toolkit: GTK4 + libadwaita

**Why:** Native GNOME look and feel out of the box — adaptive layouts, dark mode support, the modern GNOME header bar style, and proper HiDPI scaling. libadwaita gives us polished widgets (AdwPreferencesPage, AdwActionRow, AdwEntryRow, AdwToastOverlay) that make configuration UIs look professional with minimal effort. This is the recommended toolkit for GNOME 42+ apps.

### 2.3 Input Simulation: ydotool

**Why:** Most mature Wayland-compatible input simulator. Works by writing to `/dev/uinput` via a background daemon (`ydotoold`). Supports typing strings, key combos, and delays. Available in Fedora, Debian/Ubuntu, and Arch repos.

**Trade-offs:** Requires `ydotoold` running (systemd user service). Needs `input` group membership or appropriate udev rules. The install process will handle this automatically.

### 2.4 Encryption: GPG Symmetric (AES-256) + Keyring Passphrase Cache

**Recommendation:** Keep GPG symmetric encryption for the data file (backward compatible, proven, portable). Add **optional** GNOME Keyring / libsecret integration to cache the GPG passphrase for the session so the user isn't prompted every time they edit or the daemon reloads. This gives the best of both worlds:

- Data at rest is GPG-encrypted (auditable, standard tooling)
- Runtime UX is smooth (unlock once per session)
- Users who prefer manual GPG passphrase entry every time can disable keyring caching

### 2.5 Keybinding Management: gsettings / dconf

GNOME custom keybindings live under `org.gnome.settings-daemon.plugins.media-keys`. ydoit will programmatically register/unregister keybindings that call its dispatcher. The dispatcher is a lightweight CLI (`ydoit type <entry-name>`) invoked by each shortcut.

---

## 3. Architecture

```
┌──────────────────────────────────────────────┐
│                  ydoit GUI                    │
│          (GTK4 + libadwaita app)             │
│                                               │
│  ┌─────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ Entry   │  │ Shortcut │  │ GPG Config  │ │
│  │ Editor  │  │ Manager  │  │ Manager     │ │
│  └────┬────┘  └────┬─────┘  └──────┬──────┘ │
│       │             │               │         │
└───────┼─────────────┼───────────────┼─────────┘
        │             │               │
        ▼             ▼               ▼
   data.json     gsettings/      ~/.config/ydoit/
   (in memory)   dconf            data.json.gpg
        │
        ▼
┌──────────────────┐      ┌──────────────────┐
│  ydoit CLI       │      │  ydotoold        │
│  (dispatcher)    │─────▶│  (daemon)        │
│                  │      │                  │
│  ydoit type home1│      │  /dev/uinput     │
└──────────────────┘      └──────────────────┘
        ▲
        │
   GNOME shortcut
   (Super+F11)
```

### 3.1 Component Breakdown

| Component | Description |
|---|---|
| **ydoit (GUI)** | Main application window. List view of entries, add/edit/delete, import/export. Writes changes back to encrypted file and syncs keybindings. |
| **ydoit CLI** | Lightweight command-line interface. `ydoit type <name>` decrypts + types. `ydoit list` shows entries. `ydoit export/import` for backup. Called by GNOME shortcuts. |
| **Config Manager** | Handles GPG encrypt/decrypt of `data.json.gpg`. Optionally caches passphrase via libsecret/GNOME Keyring. |
| **Shortcut Manager** | Reads/writes GNOME custom keybindings via `gsettings`. Ensures bindings point to `ydoit type <name>`. Cleans up stale bindings on entry deletion. |
| **ydotoold** | System service (not ours, installed as dependency). Provides the input simulation backend. |

### 3.2 Data Flow

**User edits an entry in the GUI:**
1. GUI updates in-memory data model
2. Config Manager encrypts updated JSON → writes `~/.config/ydoit/data.json.gpg`
3. Shortcut Manager syncs GNOME keybindings via `gsettings`
4. Toast notification confirms save

**User presses a shortcut (e.g., Super+F11):**
1. GNOME calls `ydoit type home1`
2. CLI reads + decrypts `data.json.gpg` (passphrase from keyring cache or prompt)
3. CLI sends keystrokes to `ydotool` (string or file contents)
4. Target application receives typed input

---

## 4. Data Model

### 4.1 Config File Format (v2)

Backward-compatible with v1, with optional new fields:

```json
{
  "version": 2,
  "entries": {
    "home1": {
      "label": "Home Password",
      "keycombo": "Super+F11",
      "options": "-d 5 -H 5",
      "string": "supersecretpassword!\n",
      "filename": "",
      "category": "passwords",
      "notes": "Main home server login"
    },
    "setnet": {
      "label": "Network Setup Script",
      "keycombo": "Super+F8",
      "options": "-d 5 -H 5",
      "string": "",
      "filename": "/home/user/subdir/setnet.sh",
      "category": "scripts",
      "notes": ""
    }
  },
  "settings": {
    "typing_delay_ms": 5,
    "hold_delay_ms": 5,
    "use_keyring_cache": true
  }
}
```

New fields: `version`, `label` (display name), `category` (for grouping in UI), `notes` (user memo), and a `settings` block for global defaults.

### 4.2 Migration

On first launch, if a v1-format file is detected (flat object, no `version` key), the app auto-migrates to v2 format. Original `.gpg` file is backed up as `data.json.gpg.v1.bak`.

---

## 5. User Interface Design

### 5.1 Design Philosophy

Upbeat, clean, and friendly. Uses libadwaita's design language — rounded corners, generous spacing, subtle animations. The app should feel like a native GNOME utility, not a developer tool.

### 5.2 Main Window

```
┌──────────────────────────────────────────────────┐
│  ⌨ ydoit                              ─  □  ✕   │
│──────────────────────────────────────────────────│
│  🔍 Search entries...                    [+ Add] │
│──────────────────────────────────────────────────│
│                                                   │
│  PASSWORDS                                        │
│  ┌──────────────────────────────────────────────┐│
│  │ 🔑 Home Password                  Super+F11  ││
│  │    Types a password string                    ││
│  └──────────────────────────────────────────────┘│
│                                                   │
│  SCRIPTS                                          │
│  ┌──────────────────────────────────────────────┐│
│  │ 📄 Network Setup Script            Super+F8  ││
│  │    Types contents of setnet.sh                ││
│  ├──────────────────────────────────────────────┤│
│  │ 📄 Temp File Typer                 Super+F9  ││
│  │    Types contents of /tmp/ydoitmpfile         ││
│  └──────────────────────────────────────────────┘│
│                                                   │
│──────────────────────────────────────────────────│
│  ⚙ Settings              📥 Import  📤 Export   │
└──────────────────────────────────────────────────┘
```

**Key UI elements:**
- **AdwNavigationView** — main list → entry detail as a push navigation
- **AdwPreferencesGroup** — grouped by category with section headers
- **AdwActionRow** — each entry shows label, shortcut badge, and brief description
- **AdwToastOverlay** — non-intrusive confirmations ("Saved ✓", "Shortcut updated")
- **Search bar** — filters entries in real time

### 5.3 Entry Editor (Detail View)

```
┌──────────────────────────────────────────────────┐
│  ← Back           Edit Entry                     │
│──────────────────────────────────────────────────│
│                                                   │
│  Name           [ home1                        ] │
│  Label          [ Home Password                ] │
│  Category       [ passwords              ▾     ] │
│                                                   │
│  ── What to Type ──────────────────────────────  │
│                                                   │
│  ○ Type a string     ● (selected)                │
│  ┌─────────────────────────────────────────────┐ │
│  │ ••••••••••••••••••••  👁                     │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ○ Type file contents                            │
│  [ /path/to/file                      📁 Browse] │
│                                                   │
│  ── Shortcut ──────────────────────────────────  │
│                                                   │
│  Key Combo      [ Super+F11     🎹 Record ]      │
│                                                   │
│  ── Advanced ──────────────────────────────────  │
│                                                   │
│  Typing delay       [  5 ] ms                    │
│  Hold delay         [  5 ] ms                    │
│  Notes        [ Main home server login         ] │
│                                                   │
│              [ Delete Entry ]    [ Save ]         │
└──────────────────────────────────────────────────┘
```

**Notable UX details:**
- **String field** shows as password dots with a reveal toggle (since entries are often secrets)
- **Shortcut recorder** — press the "Record" button then hit the desired key combo; validates against all existing GNOME shortcuts (both system and other ydoit entries). On conflict, shows a dialog identifying the conflicting shortcut and offers to reassign it (swap or clear the existing binding) or cancel
- **File browser** uses the native GTK file chooser portal (Wayland-safe)
- **Delete** requires confirmation via an AdwAlertDialog

### 5.4 Settings Page

```
┌──────────────────────────────────────────────────┐
│  ← Back           Settings                       │
│──────────────────────────────────────────────────│
│                                                   │
│  ── Typing Defaults ───────────────────────────  │
│  Default typing delay       [  5 ] ms            │
│  Default hold delay         [  5 ] ms            │
│                                                   │
│  ── Security ──────────────────────────────────  │
│  Cache passphrase in Keyring    [ ON  🔘      ]  │
│  Passphrase cache timeout       [ 15 ] min       │
│    (0 = never expire)                             │
│  Lock entries on screen lock    [ ON  🔘      ]  │
│                                                   │
│  ── Data ──────────────────────────────────────  │
│  Config location    ~/.config/ydoit/             │
│  [ Change GPG Passphrase ]                       │
│  [ Export Unencrypted Backup... ]                │
│                                                   │
│  ── About ─────────────────────────────────────  │
│  ydoit v2.0.0                                    │
│  License: GPL-3.0                                │
│  🌐 Project Homepage                             │
└──────────────────────────────────────────────────┘
```

---

## 6. GNOME Keybinding Integration

### 6.1 How It Works

GNOME stores custom shortcuts under:
```
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/
```

Each shortcut is a child path like `.../custom0/`, `.../custom1/`, etc., with three keys:
- `name` — display name (e.g., "ydoit: Home Password")
- `command` — the command to run (e.g., `ydoit type home1`)
- `binding` — the key combo (e.g., `<Super>F11`)

ydoit manages a range of these entries, namespaced by prefixing the `name` with `ydoit:`.

### 6.2 Sync Logic

On every save from the GUI or CLI:

1. Read all current custom keybindings
2. Identify ydoit-owned bindings (name starts with `ydoit:`)
3. Diff against current entries in data.json
4. Add new bindings, update changed ones, remove deleted ones
5. Update the master keybinding list

### 6.3 Key Combo Translation

| User-facing | GNOME dconf format |
|---|---|
| `Super+F11` | `<Super>F11` |
| `Ctrl+Alt+P` | `<Primary><Alt>p` |
| `Shift+Super+S` | `<Shift><Super>s` |

The GUI translates bidirectionally and validates for conflicts. When a conflict is detected, the user is shown which shortcut currently holds that binding and offered the choice to reassign (clearing or swapping the existing binding) or pick a different combo.

---

## 7. Security Model

### 7.1 Data at Rest

- Config file encrypted with GPG symmetric AES-256 (same as v1)
- File permissions: `600` on `data.json.gpg`
- Directory permissions: `700` on `~/.config/ydoit/`

### 7.2 Data in Memory

- Decrypted data held in memory only while the GUI is open or during a CLI `type` invocation
- GUI clears decrypted data from memory on window close (or optionally on screen lock)
- Python `mlock` via `ctypes` to prevent decrypted passwords from being swapped to disk (best-effort)

### 7.3 Passphrase Caching (Optional)

- Uses libsecret to store GPG passphrase in GNOME Keyring
- Stored with schema `org.ydoit.gpg-passphrase`
- Cleared on session logout or configurable timeout (0 = never expire, persists until logout)
- Can be disabled entirely in settings

### 7.4 ydotool Security Considerations

- `ydotoold` requires access to `/dev/uinput` — this means any process with the right permissions can simulate input
- ydoit minimizes exposure: decrypts → types → discards
- The typed content is never logged or stored in shell history

---

## 8. CLI Reference

```
ydoit                         # Launch GUI
ydoit type <name>             # Decrypt and type the named entry
ydoit list                    # List all entry names
ydoit add <name>              # Add entry interactively
ydoit remove <name>           # Remove an entry
ydoit export [--plain] <file> # Export (encrypted or plain JSON)
ydoit import <file>           # Import from file
ydoit sync-shortcuts          # Force-sync GNOME keybindings
ydoit status                  # Show ydotoold status, config path, etc.
ydoit version                 # Print version
```

---

## 9. Packaging & Distribution

### 9.1 Project Structure

```
ydoit/
├── src/
│   ├── ydoit/
│   │   ├── __init__.py
│   │   ├── app.py              # GtkApplication subclass, main entry
│   │   ├── window.py           # Main window
│   │   ├── entry_editor.py     # Entry detail/edit view
│   │   ├── settings_page.py    # Settings view
│   │   ├── config_manager.py   # GPG encrypt/decrypt, data model
│   │   ├── shortcut_manager.py # gsettings keybinding sync
│   │   ├── keyring_manager.py  # libsecret passphrase cache
│   │   ├── typer.py            # ydotool interface
│   │   └── cli.py              # CLI entry point (argparse)
│   └── data/
│       ├── org.ydoit.app.desktop       # Desktop file
│       ├── org.ydoit.app.metainfo.xml  # AppStream metadata
│       ├── org.ydoit.app.svg           # App icon
│       └── org.ydoit.app.gschema.xml   # GSettings schema
├── packaging/
│   ├── rpm/
│   │   └── ydoit.spec
│   ├── deb/
│   │   ├── debian/control
│   │   ├── debian/rules
│   │   ├── debian/changelog
│   │   └── debian/postinst
│   └── flatpak/
│       └── org.ydoit.app.yml
├── tests/
│   ├── test_config_manager.py
│   ├── test_shortcut_manager.py
│   └── test_typer.py
├── docs/
│   ├── README.md
│   ├── INSTALL.md
│   ├── USAGE.md
│   ├── SECURITY.md
│   └── MIGRATION.md
├── scripts/
│   └── post-install.sh          # Setup defaults, enable ydotoold
├── pyproject.toml
├── meson.build                  # GNOME-standard build system
├── LICENSE                      # GPL-3.0
└── README.md
```

### 9.2 Build System: Meson

Standard for GNOME apps. Handles installing Python modules, desktop files, icons, GSettings schemas, and man pages.

### 9.3 RPM (Fedora / RHEL)

**Spec file highlights:**
- `BuildRequires`: meson, python3-devel, gtk4-devel, libadwaita-devel
- `Requires`: python3-gobject, gtk4, libadwaita, ydotool, gnupg2, libsecret
- `%post`: compile GSettings schemas, update icon cache, enable ydotoold user service

**Install:**
```bash
sudo dnf install ydoit-2.0.0-1.fc42.noarch.rpm
```

### 9.4 DEB (Ubuntu / Debian)

**Control file highlights:**
- `Depends`: python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, ydotool, gnupg2, libsecret-1-0
- `postinst`: same schema/icon/service setup

**Install:**
```bash
sudo apt install ./ydoit_2.0.0-1_all.deb
```

### 9.5 Flatpak

**Manifest (`org.ydoit.app.yml`):**
- Runtime: `org.gnome.Platform//46`
- SDK: `org.gnome.Sdk//46`
- Modules: Python deps, ydotool bundled
- Permissions: `--talk-name=org.gnome.SettingsDaemon`, `--device=input` (for ydotool), `--talk-name=org.freedesktop.secrets` (for keyring)

**Caveat:** Flatpak sandboxing complicates `ydotool` (needs `/dev/uinput` access) and `gsettings` (host dconf access). This will require `--device=input` and `--filesystem=xdg-config/dconf:ro` permissions, plus possibly a portal for shortcut registration. Flatpak is the most complex target and may ship slightly later.

**Install:**
```bash
flatpak install ydoit.flatpakref
```

---

## 10. Installation & Post-Install Setup

### 10.1 What the Installer Does Automatically

1. **Creates config directory:** `~/.config/ydoit/` with `700` permissions
2. **Enables ydotoold:** `systemctl --user enable --now ydotoold.service`
3. **Adds user to input group** (if needed): `sudo usermod -aG input $USER` — requires logout/login
4. **Compiles GSettings schemas** and updates icon/desktop caches
5. **Registers default shortcut folder:** Creates the ydoit namespace in GNOME custom keybindings (empty, ready for entries)
6. **Migrates v1 data:** If `~/.config/ydoit/data.json.gpg` exists in v1 format, backs up and migrates

### 10.2 Post-Install User Action

After install, the user may need to:
1. **Log out and back in** (if added to `input` group for ydotool)
2. **Run `ydoit`** to launch the GUI and set up their first entry or import existing data

---

## 11. Prerequisites

| Dependency | Version | Purpose | Package (Fedora) | Package (Ubuntu) |
|---|---|---|---|---|
| Python | ≥ 3.10 | Runtime | python3 | python3 |
| GTK4 | ≥ 4.10 | UI toolkit | gtk4 | libgtk-4-1 |
| libadwaita | ≥ 1.4 | GNOME widgets | libadwaita | libadwaita-1-0 |
| PyGObject | ≥ 3.42 | Python GTK bindings | python3-gobject | python3-gi |
| ydotool | ≥ 1.1.0 | Input simulation | ydotool | ydotool |
| GnuPG | ≥ 2.2 | Encryption | gnupg2 | gnupg |
| libsecret | ≥ 0.20 | Keyring access | libsecret | libsecret-1-0 |
| dconf | (system) | Keybinding storage | dconf | dconf-cli |

**OS Targets:** Fedora 42+, Ubuntu 23.10+ (or 24.04 LTS), GNOME 44+

---

## 12. Documentation Plan

| Document | Contents |
|---|---|
| **README.md** | Project overview, quick install, screenshot, badges |
| **INSTALL.md** | Detailed install for RPM, DEB, Flatpak, from source. Troubleshooting ydotool setup. Verifying prerequisites. |
| **USAGE.md** | GUI walkthrough with screenshots. CLI reference. Workflow examples (add a password, set up a script typer, change a shortcut). |
| **SECURITY.md** | Encryption details, threat model, ydotool security implications, passphrase caching behavior, memory handling. |
| **MIGRATION.md** | Upgrading from v1 shell scripts. Format changes. Backing up. |
| **CONTRIBUTING.md** | Dev setup, running tests, coding style, PR process. |
| **man page (ydoit.1)** | Standard man page for CLI usage |

---

## 13. Development Roadmap

### Phase 1 — Core (Weeks 1–3)
- Config manager (GPG encrypt/decrypt, v1 migration)
- CLI dispatcher (`ydoit type`, `ydoit list`)
- ydotool integration + typing engine
- Shortcut manager (gsettings read/write/sync)
- Unit tests for all core modules

### Phase 2 — GUI (Weeks 4–6)
- Main window with entry list (grouped by category)
- Entry editor with shortcut recorder
- Settings page
- Search/filter
- Toast notifications
- App icon and desktop file

### Phase 3 — Packaging (Weeks 7–8)
- Meson build system
- RPM spec + build on Fedora
- DEB packaging + build on Ubuntu
- Post-install scripts
- CI/CD pipeline (GitHub Actions with Fedora + Ubuntu containers)

### Phase 4 — Flatpak & Polish (Weeks 9–10)
- Flatpak manifest + sandbox permissions
- Flatpak testing
- AppStream metadata + Flathub submission
- Documentation finalization
- Beta testing

### Phase 5 — Release (Week 11)
- v2.0.0 release
- GitHub release with RPM/DEB artifacts
- Flathub listing
- Announcement

---

## 14. Future Considerations

- **Clipboard mode:** Option to copy to clipboard instead of typing (avoids ydotool dependency for some use cases)
- **Auto-lock:** Clear cached passphrase and lock entries on idle timeout
- **Multi-file support:** Multiple encrypted vaults
- **Sync:** Optional encrypted cloud sync (e.g., via Nextcloud/Syncthing)
- **GNOME Shell extension:** Status icon showing lock state and quick-type menu
- **X11 fallback:** Detect session type and use xdotool when on X11 (backward compat for older systems)
