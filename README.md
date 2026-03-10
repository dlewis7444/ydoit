# ydoit v2

Keyboard shortcut auto-typer for GNOME/Wayland.

Map keyboard shortcuts to auto-type actions — type out strings, passwords, or file contents on demand. Uses `ydotool` for Wayland-native input simulation and GPG symmetric encryption (AES-256) for secure config storage.

## Quick Start (Development)

```bash
git clone <repo-url>
cd ydoit
python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

### System Dependencies

```bash
# Fedora 42+
sudo dnf install gnupg2 ydotool python3-gobject gtk4 libadwaita

# Ubuntu 24.04+
sudo apt install gnupg ydotool python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

### Enable ydotoold

```bash
systemctl --user enable --now ydotoold
```

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

## License

GPL-3.0-or-later
