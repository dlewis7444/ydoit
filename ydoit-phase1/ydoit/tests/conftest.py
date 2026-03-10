"""Shared test fixtures for ydoit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ydoit.models import Config, Entry

if TYPE_CHECKING:
    from pathlib import Path

# --- Sample v1 data (matches the project's data.json) ---

V1_SAMPLE_DATA = {
    "home1": {
        "keycombo": "Super+F11",
        "options": "-d 5 -H 5",
        "string": "supersecretpassword!\\n",
        "filename": "",
    },
    "setnet": {
        "keycombo": "Super+F8",
        "options": "-d 5 -H 5",
        "string": "",
        "filename": "/home/user/subdir/setnet.sh",
    },
    "tmpfile": {
        "keycombo": "Super+F9",
        "options": "-d 5 -H 5",
        "string": "",
        "filename": "/tmp/ydoitmpfile",
    },
}


@pytest.fixture
def v1_data() -> dict:
    """Return sample v1 format config data."""
    return V1_SAMPLE_DATA.copy()


@pytest.fixture
def sample_config() -> Config:
    """Return a sample v2 Config with test entries."""
    config = Config()
    config.entries = {
        "home1": Entry(
            trigger="home1",
            keycombo="Super+F11",
            string="supersecretpassword!\n",
            label="Home Password",
            category="passwords",
        ),
        "setnet": Entry(
            trigger="setnet",
            keycombo="Super+F8",
            filename="/home/user/subdir/setnet.sh",
            label="Network Setup Script",
            category="scripts",
        ),
        "tmpfile": Entry(
            trigger="tmpfile",
            keycombo="Super+F9",
            filename="/tmp/ydoitmpfile",
            label="Temp File Typer",
            category="scripts",
        ),
    }
    return config


@pytest.fixture
def sample_passphrase() -> str:
    """Return a test passphrase."""
    return "test-passphrase-12345"


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Return a temporary config directory."""
    d = tmp_path / ".config" / "ydoit"
    d.mkdir(parents=True)
    return d
