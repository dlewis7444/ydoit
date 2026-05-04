#!/usr/bin/env bash
set -euo pipefail

SKIP_GIT_CHECK=0
for arg in "$@"; do
    [[ "$arg" == "--skip-git-check" ]] && SKIP_GIT_CHECK=1
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC="$HOME/rpmbuild/SPECS/ydoit.spec"
VERSION=$(grep '^Version:' "$REPO_ROOT/packaging/rpm/ydoit.spec" | awk '{print $2}')
TARBALL="$HOME/rpmbuild/SOURCES/ydoit-${VERSION}.tar.gz"
RPM="$HOME/rpmbuild/RPMS/noarch/ydoit-${VERSION}-1.fc43.noarch.rpm"

if [[ "$SKIP_GIT_CHECK" -eq 0 ]]; then
    if ! git -C "$REPO_ROOT" diff --quiet || ! git -C "$REPO_ROOT" diff --cached --quiet; then
        echo "ERROR: Uncommitted changes detected. The RPM is built from git HEAD," >&2
        echo "       so uncommitted changes will not be included." >&2
        echo "       Commit your changes first, or use --skip-git-check to bypass." >&2
        exit 1
    fi
fi

echo "==> Archiving HEAD (version ${VERSION})..."
git -C "$REPO_ROOT" archive --format=tar.gz --prefix="ydoit-${VERSION}/" HEAD -o "$TARBALL"

echo "==> Copying spec..."
cp "$REPO_ROOT/packaging/rpm/ydoit.spec" "$SPEC"

echo "==> Building RPM..."
rpmbuild -bb "$SPEC"

echo "==> Installing with dnf..."
if rpm -q ydoit &>/dev/null; then
    sudo dnf reinstall -y "$RPM"
else
    sudo dnf install -y --allowerasing "$RPM"
fi

echo "==> Done. Installed ydoit ${VERSION}."
