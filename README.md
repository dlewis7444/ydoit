# ydoit v2

Keyboard shortcut auto-typer for GNOME/Wayland.

Map keyboard shortcuts to auto-type actions — type out strings, passwords, or file contents on demand. Uses `ydotool` (local seat) or **Mutter RemoteDesktop** (GNOME Remote Desktop / RDP sessions) for Wayland-native input simulation, and GPG symmetric encryption (AES-256) for secure config storage.

Very useful for pasting into systems that can't be pasted into.  (iLOs, some VMs, etc.)


## Quick Start

Grab the latest release from https://github.com/dlewis7444/ydoit/releases/latest.

### Fedora 43+

```bash
sudo dnf install ./ydoit-*.noarch.rpm
systemctl --user enable --now ydotoold
```

### Debian 13 / Ubuntu 24.04+

```bash
sudo apt install ./ydoit_*_all.deb
systemctl --user enable --now ydotoold
```

Then launch **ydoit Manager** from the application grid, or run `ydoit` / `ydoit-gui` from a terminal.

## CLI Usage

```bash
ydoit status                              # Check system status
ydoit add mypass -k Super+F11 -s "secret" # Add a string entry
ydoit add myscript -k Super+F8 -f /path   # Add a file entry
ydoit list                                # List all entries
ydoit type mypass                         # Type an entry
ydoit type mypass --backend mutter        # Force Mutter for this run
ydoit sync-shortcuts                      # Sync GNOME keybindings
ydoit export backup.json --plain          # Export unencrypted
ydoit import backup.json                  # Import entries
ydoit remove mypass                       # Remove an entry
```

## Input backends

ydoit can inject keystrokes two ways:

| Backend | When to use |
|---------|-------------|
| **auto** (default) | Local physical seat → ydotool when `ydotoold` is healthy. GNOME Remote Desktop / remote-like sessions → Mutter. Falls back to Mutter if ydotool is unavailable. |
| **mutter** | Always use GNOME Mutter RemoteDesktop (`NotifyKeyboardKeysym`). Required for reliable typing *inside* a gnome-rdp session (uinput/ydotool is orphaned there: exit 0, no keys). |
| **ydotool** | Always use `ydotool` / `ydotoold` / `/dev/uinput` (classic local Wayland path). |

Configure in **ydoit Manager → Settings → Input backend**, or override for one shot:

```bash
ydoit type mypass --backend auto|mutter|ydotool
YDOIT_INPUT_BACKEND=mutter ydoit type mypass   # debug override
```

`ydoit status` shows **configured** vs **effective** backend, plus Mutter / remote / ydotoold / uinput.

### GNOME Remote Desktop / RDP

On a **GNOME Remote Desktop** (system RDP) session, kernel uinput injection does not reach the focused app. Use **Auto** or **Mutter**. If typing is silent with Auto, set backend to **Mutter** explicitly (or set `YDOIT_SESSION_REMOTE=1` for debugging remote detection).

Client-side ydoit on the FreeRDP host is awkward under fullscreen key grab; run shortcuts / `ydoit type` **on the remote session**.

## Building from source

Helper scripts produce RPM and DEB artifacts from `git HEAD`:

```bash
git clone https://github.com/dlewis7444/ydoit
cd ydoit
./scripts/build-rpm.sh   # Fedora — builds, then sudo dnf installs
./scripts/build-deb.sh   # Any Linux with podman — builds in a debian:13 container
```

Outputs land in `~/rpmbuild/RPMS/noarch/` and `dist/` respectively.

## Development

```bash
git clone https://github.com/dlewis7444/ydoit
cd ydoit
python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

`--system-site-packages` is required because PyGObject, GTK4, and libsecret are system packages, not on PyPI.

System packages (Fedora): `gnupg2 ydotool python3-gobject python3-dbus gtk4 libadwaita`.

## License

MIT
