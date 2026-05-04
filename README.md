# ydoit v2

Keyboard shortcut auto-typer for GNOME/Wayland.

Map keyboard shortcuts to auto-type actions — type out strings, passwords, or file contents on demand. Uses `ydotool` for Wayland-native input simulation and GPG symmetric encryption (AES-256) for secure config storage.

Very useful for pasting into systems that can't be pasted into.  (iLOs, some VMs, etc.)


## Quick Start

### Fedora

```bash
sudo dnf install gnupg2 ydotool python3-gobject gtk4 libadwaita
systemctl --user enable --now ydotoold
git clone https://github.com/dlewis7444/ydoit
cd ydoit
./scripts/build-rpm.sh
```

### Ubuntu / Debian

```bash
sudo apt install gnupg ydotool python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libsecret-1-0 meson
systemctl --user enable --now ydotoold
git clone https://github.com/dlewis7444/ydoit
cd ydoit
meson setup --prefix=/usr/local builddir
sudo meson install -C builddir
```

After install: launch **ydoit Manager** from the application grid, or run `ydoit` / `ydoit-gui` from a terminal.

## CLI Usage

```bash
ydoit status                              # Check system status
ydoit add mypass -k Super+F11 -s "secret" # Add a string entry
ydoit add myscript -k Super+F8 -f /path   # Add a file entry
ydoit list                                # List all entries
ydoit type mypass                         # Type an entry
ydoit sync-shortcuts                      # Sync GNOME keybindings
ydoit export backup.json --plain          # Export unencrypted
ydoit import backup.json                  # Import entries
ydoit remove mypass                       # Remove an entry
```

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

## License

MIT
