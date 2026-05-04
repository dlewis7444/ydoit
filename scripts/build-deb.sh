#!/usr/bin/env bash
set -euo pipefail

SKIP_GIT_CHECK=0
for arg in "$@"; do
    [[ "$arg" == "--skip-git-check" ]] && SKIP_GIT_CHECK=1
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=$(awk '/^Version:/ {print $2}' "$REPO_ROOT/packaging/rpm/ydoit.spec")
DEB="$REPO_ROOT/dist/ydoit_${VERSION}_all.deb"

if [[ "$SKIP_GIT_CHECK" -eq 0 ]]; then
    if ! git -C "$REPO_ROOT" diff --quiet || ! git -C "$REPO_ROOT" diff --cached --quiet; then
        echo "ERROR: Uncommitted changes detected. The deb is built from git HEAD," >&2
        echo "       so uncommitted changes will not be included." >&2
        echo "       Commit your changes first, or use --skip-git-check to bypass." >&2
        exit 1
    fi
fi

mkdir -p "$REPO_ROOT/dist"

echo "==> Building deb in debian:13 container..."
podman run --rm \
    -v "$REPO_ROOT":/src:Z \
    -e VERSION="$VERSION" \
    -w /src \
    debian:13 \
    bash -euxc '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y --no-install-recommends \
            meson ninja-build python3 dpkg-dev fakeroot

        rm -rf /tmp/builddir /tmp/staging
        meson setup --prefix=/usr -Dpython.platlibdir=lib/python3/dist-packages -Dpython.purelibdir=lib/python3/dist-packages /tmp/builddir
        DESTDIR=/tmp/staging meson install -C /tmp/builddir

        mkdir -p /tmp/staging/DEBIAN
        cat > /tmp/staging/DEBIAN/control <<EOF
Package: ydoit
Version: ${VERSION}
Architecture: all
Maintainer: David Lewis <david@lewisit.com>
Section: utils
Priority: optional
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, libsecret-1-0, gnupg, ydotool
Homepage: https://github.com/dlewis7444/ydoit
Description: Keyboard shortcut auto-typer for GNOME/Wayland
 ydoit lets you bind GNOME keyboard shortcuts that automatically type
 predefined strings into the active window. It stores entries in a
 GPG-encrypted configuration file, syncs keybindings with GNOME, and
 delivers keystrokes natively on Wayland via ydotool.
EOF

        cat > /tmp/staging/DEBIAN/postinst <<"POSTINST"
#!/bin/sh
set -e
update-desktop-database -q /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true
POSTINST
        chmod 755 /tmp/staging/DEBIAN/postinst

        cat > /tmp/staging/DEBIAN/postrm <<"POSTRM"
#!/bin/sh
set -e
update-desktop-database -q /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true
POSTRM
        chmod 755 /tmp/staging/DEBIAN/postrm

        dpkg-deb --root-owner-group -b /tmp/staging /src/dist/ydoit_${VERSION}_all.deb
    '

echo "==> Built: $DEB"
ls -la "$DEB"
