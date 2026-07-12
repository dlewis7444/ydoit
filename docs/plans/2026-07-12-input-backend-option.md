# Plan: Input backend option (Mutter RemoteDesktop vs ydotool)

**Status:** Ready for implementation  
**Target version:** 2.0.2  
**Date:** 2026-07-12  
**Context:** Virtual desktop (vd1) over GNOME Remote Desktop / FreeRDP; ydoit must type *inside* that session.

---

## 0. Current status (what we already did)

### Problem
On a **GNOME Remote Desktop** session (system RDP on vd1), `ydoit type` appeared to succeed (`exit 0`) but **typed nothing**. GNOME shortcuts fired (e.g. Super opened dash), but injected keys never reached the focused app.

### Root cause
`ydotool` → `ydotoold` → `/dev/uinput` injects at the **kernel input** layer. A gnome-rdp session consumes input primarily via the **RDP / Mutter RemoteDesktop** path. Local uinput devices are effectively **orphaned** for that session (same class of issue previously documented for headless g-r-d: do not keep “fixing” ydotoold permissions alone).

`wtype` fails differently: *“Compositor does not support the virtual keyboard protocol.”*

### Fix already implemented (code + live patch on vd1)
**File:** `src/ydoit/typer.py` (also hand-copied to  
`/usr/lib/python3.14/site-packages/ydoit/typer.py` on vd1 until 2.0.2 ships)

1. **Mutter RemoteDesktop backend**  
   - D-Bus: `org.gnome.Mutter.RemoteDesktop`  
   - `CreateSession` → `Start` → `NotifyKeyboardKeysym` per character → `Stop`  
   - Same injection family gnome-remote-desktop uses.

2. **Escape expansion** for the Mutter path (match ydotool CLI default `--escape=1`):  
   `\n` → Enter (Return keysym), `\t` tab, `\r`, `\b`, `\\`.  
   Without this, stored `…\n` was typed as the two characters `\` and `n`.

3. **Backend selection today (implicit, not user-facing):**  
   - Prefer Mutter if `org.gnome.Mutter.RemoteDesktop` is on the session bus.  
   - Else ydotool if `ydotoold` is running.  
   - Else error.

4. **vd1 packaging note:** RPM is still 2.0.1; site-packages patch will be **overwritten** by `dnf reinstall ydoit` until this work is released.

5. **Out of scope for that emergency fix:** GUI setting, CLI flag, tests, version bump, clean packaging.

### Working usage on vd1
- Fullscreen FreeRDP, keys owned by remote session.  
- Shortcuts / `ydoit type` run **on vd1** with Mutter backend.  
- Client-side ydoit is **not** required for this topology (and is awkward with fullscreen grab).

---

## 1. Product goal

Expose **input backend** as an explicit option:

| Value | Behavior |
|-------|----------|
| `auto` | Smart selection (see §2 — **not** “Mutter if D-Bus exists”) |
| `mutter` | Always use Mutter RemoteDesktop keysym injection |
| `ydotool` | Always use ydotool/ydotoold |

Surfaces:

1. **Persisted setting** in encrypted config (`Settings`).  
2. **Manager (GUI)** — combo under Typing Defaults.  
3. **CLI** — one-shot override on `ydoit type` (and show effective backend on `ydoit status`).

---

## 2. Default: should it be Mutter?

### Short answer
**Default the *setting* to `auto`, not hard-coded `mutter`.**  
Do **not** implement auto as “if Mutter D-Bus is present → Mutter.”

### Why not “prefer Mutter whenever available”?
On a normal local GNOME seat (e.g. davidnote):

- `org.gnome.Mutter.RemoteDesktop` is **almost always** on the session bus.  
- That would flip **all** local users from battle-tested **ydotool** to creating a **RemoteDesktop session for every type**.

Risks / unknowns of always-Mutter on local desktops:

- Possible “session being controlled” / accessibility / security UX.  
- Interaction with an **active** gnome-remote-desktop connection (second RemoteDesktop session).  
- Slightly higher latency / D-Bus chatter per type.  
- ydotool remains the right tool for physical seat0 + uinput on a normal workstation.

### Recommended `auto` policy
```
if settings.input_backend == "mutter":
    use mutter (error if unavailable)
elif settings.input_backend == "ydotool":
    use ydotool (error if ydotoold/uinput bad)
else:  # auto
    if _session_looks_remote() and _mutter_available():
        use mutter
    elif _ydotool_ready():
        use ydotool
    elif _mutter_available():
        use mutter   # last resort (e.g. RDP where ydotool is dead)
    else:
        error with clear message
```

**`_session_looks_remote()`** (best-effort, no hard dependency on loginctl parsing perfection):

- `XDG_SESSION_TYPE` + remote: e.g. `loginctl show-session $XDG_SESSION_ID -p Remote` → `yes`, **or**
- env already used by g-r-d sessions, **or**
- heuristic: `Remote=yes` on the graphical session.

Document that `auto` on vd1-class hosts → Mutter; on davidnote local → ydotool.

**Optional env override (nice, tiny):** `YDOIT_INPUT_BACKEND=auto|mutter|ydotool` overrides settings for debugging (document in README).

---

## 3. Other ways to do it (if not a setting)

| Approach | Pros | Cons |
|----------|------|------|
| **CLI-only** `--backend` | Tiny PR | Easy to forget; shortcuts always use config/default |
| **Env only** | Good for scripts | Invisible in Manager |
| **Always auto, no UI** | Zero UI work | Power users can’t force ydotool on RDP experiments or Mutter on odd seats |
| **Clipboard + Ctrl+V** | Avoids keysym map | Needs focus paste; bad for some secure fields; still needs *some* key injection for paste chord on pure Wayland |
| **libei `ConnectToEIS`** | More “modern” input path | Heavier; more code; keysym path already works |
| **Client-side ydoit** | No server change | Breaks fullscreen key-grab topology David wants |

**Recommendation:** setting + CLI override + smart `auto` (this plan). Not libei unless keysym path regresses.

---

## 4. Availability checks (toggle / CLI)

When the user **selects** a backend (GUI toggle/combo) or **passes** `--backend`:

| Backend | Check | If fail |
|---------|--------|---------|
| `ydotool` | `shutil.which("ydotool")`, `Typer.check_daemon()`, optionally `check_permissions()` | Dialog / CLI error: install ydotool, `systemctl --user start ydotoold`, uinput udev |
| `mutter` | Session bus name `org.gnome.Mutter.RemoteDesktop` (same as `_mutter_available()`) | Error: only on GNOME/Mutter; not available in this session |
| `auto` | No hard fail at toggle time; `status` lists what would be chosen |

GUI: `Adw.ComboRow` with three options; on change, **probe** and set subtitle warning if chosen backend is unavailable (still allow saving so config syncs across machines — e.g. set `mutter` on laptop, only works when on vd1).

Alternatively: still save, but show a non-blocking banner “Mutter not available here; typing will fail until you’re on a GNOME session that exports RemoteDesktop.”

**Do not** require ydotool binary when backend is `mutter` or when `auto` resolves to mutter.

---

## 5. Implementation plan (for implementing agent)

### 5.1 Constants & model
- `constants.py`:  
  `INPUT_BACKEND_AUTO = "auto"`, `MUTTER = "mutter"`, `YDOTOOL = "ydotool"`  
  `DEFAULT_INPUT_BACKEND = "auto"`  
  `VALID_INPUT_BACKENDS = frozenset({...})`
- `models.Settings`: add `input_backend: str = DEFAULT_INPUT_BACKEND`  
  - `to_dict` / `from_dict`: validate; unknown → `"auto"`
- No migration script: missing key defaults cleanly.

### 5.2 Typer
- Constructor: accept `backend: str | None = None` (None → use settings when type_entry gets settings).
- `type_entry` / `type_string`: resolve backend from:
  1. explicit ctor / per-call override  
  2. else `default_settings.input_backend`  
  3. else `auto` policy (§2)
- Keep `_expand_ydotool_escapes` for **Mutter** path only (ydotool CLI already escapes).
- Keep `backend_status()` for diagnostics; extend to report **configured** vs **effective**.
- Unit-test:
  - `_expand_ydotool_escapes` (`\n`, `\\`, unknown escapes)
  - `_char_to_keysym` for `\n` → Return  
  - selection policy with mocks for mutter available / daemon running / remote flag

### 5.3 CLI
- `ydoit type`: add  
  `--backend {auto,mutter,ydotool}`  
  (default: use config settings, not force auto-ignore-config)
- `ydoit status`: print  
  - configured backend  
  - effective backend (what would be used now)  
  - mutter available yes/no  
  - ydotoold running / uinput  
- Optional: `YDOIT_INPUT_BACKEND` env overrides config when set (document).

### 5.4 GUI (`settings_page.py`)
- PreferencesGroup “Typing” (existing): add  
  `Adw.ComboRow` title **Input backend**  
  - Auto (recommended)  
  - Mutter (GNOME / Remote Desktop)  
  - ydotool  
- Subtitle explaining Auto: local seat → ydotool; GNOME RDP-style remote → Mutter.  
- On change: probe availability; set row subtitle or toast if unavailable.  
- Wire save via existing `settings-changed` / config save path (same as delay spins).

### 5.5 Packaging / version
- Bump `__version__` → **2.0.2**  
- `pyproject.toml` / RPM / DEB version strings  
- `python3-dbus` already needed for Mutter path (document Requires on Fedora: `python3-dbus`)  
- Changelog blurb: Mutter backend for gnome-rdp; escape fix; configurable backend.

### 5.6 Docs
- README: short “GNOME Remote Desktop / RDP” section — use backend Auto or Mutter; ydotool alone will not type into g-r-d sessions.  
- CLAUDE.md one-liner if architecture blurb exists.

### 5.7 Deploy note for vd1
After release: install 2.0.2 RPM on vd1 so site-packages is no longer hand-patched.  
Config: set `input_backend` to `auto` or `mutter` on vd1 if desired (auto should pick mutter when remote).

---

## 6. Acceptance criteria

1. Local GNOME (physical): `auto` uses **ydotool** when ydotoold is healthy (regression check on davidnote).  
2. GNOME RDP session (vd1): `auto` or `mutter` types into focused field; `\n` becomes Enter, not literal `\n`.  
3. `ydoit type --backend ydotool` on vd1 either errors clearly or no-ops visibly documented — must not silently “succeed” without typing if we can detect failure (optional stretch: not required for 2.0.2 if hard).  
4. Manager combo persists across restart (encrypted settings).  
5. `ydoit status` shows configured + effective backend.  
6. Tests pass; RPM/DEB build scripts still work.

---

## 7. Non-goals (this PR)

- libei / ConnectToEIS rewrite  
- Client-side ydoit-over-RDP as primary design  
- Fixing Super key capture on the FreeRDP **client** (separate issue; fullscreen grab is user’s topology)  
- Changing default keybindings in user data  

---

## 8. Answers to product questions (for the record)

### Q1: Default to Mutter? Why / why not?
**Default setting value: `auto`.**  
Effective choice under auto should **not** be “Mutter if D-Bus exists,” because that D-Bus name exists on ordinary local GNOME and would abandon ydotool for everyone.  
Prefer: remote-like session + Mutter → Mutter; else ydotool; else Mutter last resort.

### Q2: Another way?
Yes: CLI/env only; clipboard paste; libei; client-side ydoit. Setting + smart auto is the right balance for Manager + RDP.

### Q3: Check binary when toggled?
Yes: on combo change / CLI parse, probe **ydotool binary + daemon** for ydotool mode, **D-Bus name** for Mutter. Allow saving unavailable backend (multi-machine config) but warn.

---

## 9. Pushback / open questions for David (if implementing agent is blocked)

1. **Silent ydotool on RDP:** Today ydotool returns 0 with no keys. Should 2.0.2 try a cheap “did we type?” check, or only document “use Mutter on RDP”? (Recommend: document + status warning if remote session and backend is ydotool.)  
2. **Remote detection false positives:** If auto mis-detects, user forces backend in Settings — is that enough?  
3. **Per-entry backend?** Almost certainly no — global setting only.

---

## 10. Suggested commit / PR title

`feat: selectable input backend (Mutter RemoteDesktop + ydotool) for GNOME RDP`

Include escape-expansion + auto policy in the same release so vd1 is not a special snowflake.
