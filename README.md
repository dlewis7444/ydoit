# ydoit v2

Keyboard shortcut auto-typer for GNOME/Wayland.

Map keyboard shortcuts to auto-type actions — type out strings, passwords, or file contents on demand. Uses `ydotool` for Wayland-native input simulation and GPG symmetric encryption (AES-256) for secure config storage.

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
ydoit sync-shortcuts                      # Sync GNOME keybindings
ydoit export backup.json --plain          # Export unencrypted
ydoit import backup.json                  # Import entries
ydoit remove mypass                       # Remove an entry
```

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

## License

MIT
