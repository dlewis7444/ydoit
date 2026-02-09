"""Migration from v1 config format to v2."""

from __future__ import annotations

import re
from typing import Any

from ydoit import constants


def detect_version(data: dict[str, Any]) -> int:
    """Detect config file version.

    v1: flat dict of entries (no 'version' key).
    v2: has 'version' key with int value.

    Returns:
        Version number (1 or 2+).
    """
    if "version" in data:
        return int(data["version"])
    return 1


def parse_v1_options(options: str) -> tuple[int, int]:
    """Parse xdotool-style options string into delay values.

    Supported flags:
        -d <ms>  typing delay (--delay)
        -H <ms>  hold delay (--clearmodifiers was -H in some versions)

    Args:
        options: Raw options string, e.g. "-d 5 -H 5"

    Returns:
        Tuple of (typing_delay_ms, hold_delay_ms).
    """
    typing_delay = constants.DEFAULT_TYPING_DELAY_MS
    hold_delay = constants.DEFAULT_HOLD_DELAY_MS

    if not options or not options.strip():
        return typing_delay, hold_delay

    # Match -d <number> or --delay <number>
    delay_match = re.search(r"-d\s+(\d+)", options)
    if delay_match:
        typing_delay = int(delay_match.group(1))

    # Match -H <number>
    hold_match = re.search(r"-H\s+(\d+)", options)
    if hold_match:
        hold_delay = int(hold_match.group(1))

    return typing_delay, hold_delay


def migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate a v1-format config dict to v2 format.

    v1 format (flat dict of entries):
        {
            "home1": {
                "keycombo": "Super+F11",
                "options": "-d 5 -H 5",
                "string": "password\\n",
                "filename": ""
            }
        }

    v2 format (structured):
        {
            "version": 2,
            "entries": {
                "home1": {
                    "keycombo": "Super+F11",
                    "string": "password\\n",
                    "filename": "",
                    "label": "home1",
                    "category": "general",
                    "notes": "",
                    "typing_delay_ms": 5,
                    "hold_delay_ms": 5
                }
            },
            "settings": { ... }
        }

    Args:
        data: v1 format dictionary.

    Returns:
        v2 format dictionary.
    """
    entries: dict[str, Any] = {}
    all_typing_delays: list[int] = []
    all_hold_delays: list[int] = []

    for name, v1_entry in data.items():
        if not isinstance(v1_entry, dict):
            continue

        options = v1_entry.get("options", "")
        typing_delay, hold_delay = parse_v1_options(options)
        all_typing_delays.append(typing_delay)
        all_hold_delays.append(hold_delay)

        # Determine a sensible category based on content
        filename = v1_entry.get("filename", "")
        string = v1_entry.get("string", "")
        if filename:
            category = "scripts"
        elif string:
            category = "passwords"
        else:
            category = constants.DEFAULT_CATEGORY

        entries[name] = {
            "keycombo": v1_entry.get("keycombo", ""),
            "string": string,
            "filename": filename,
            "label": name,
            "category": category,
            "notes": f"Migrated from v1. Original options: {options}" if options else "",
            "typing_delay_ms": typing_delay,
            "hold_delay_ms": hold_delay,
        }

    # Use the most common delay values as the global defaults
    global_typing = _most_common(all_typing_delays, constants.DEFAULT_TYPING_DELAY_MS)
    global_hold = _most_common(all_hold_delays, constants.DEFAULT_HOLD_DELAY_MS)

    # Clear per-entry overrides if they match the global default
    for entry in entries.values():
        if entry["typing_delay_ms"] == global_typing:
            del entry["typing_delay_ms"]
        if entry["hold_delay_ms"] == global_hold:
            del entry["hold_delay_ms"]

    return {
        "version": 2,
        "entries": entries,
        "settings": {
            "typing_delay_ms": global_typing,
            "hold_delay_ms": global_hold,
            "use_keyring_cache": True,
            "keyring_timeout_min": constants.DEFAULT_KEYRING_TIMEOUT_MIN,
        },
    }


def _most_common(values: list[int], default: int) -> int:
    """Return the most common value in a list, or default if empty."""
    if not values:
        return default
    return max(set(values), key=values.count)
