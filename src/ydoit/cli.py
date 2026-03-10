"""CLI entry point for ydoit."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from ydoit import __version__, constants
from ydoit.config_manager import ConfigManager
from ydoit.exceptions import (
    DecryptionError,
    EntryNotFoundError,
    GioNotAvailableError,
    GpgNotFoundError,
    InvalidEntryTriggerError,
    YdoitError,
    YdotoolError,
)
from ydoit.models import Config, Entry
from ydoit.shortcut_manager import ShortcutManager
from ydoit.typer import Typer


# --- ANSI colors ---
class _Colors:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    RESET = "\033[0m"


class _NoColors:
    BOLD = ""
    DIM = ""
    GREEN = ""
    YELLOW = ""
    RED = ""
    CYAN = ""
    RESET = ""


def _supports_color() -> bool:
    """Check if the terminal supports color output."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


C = _Colors() if _supports_color() else _NoColors()


# --- Passphrase handling ---


def _prompt_passphrase(confirm: bool = False) -> str:
    """Prompt for GPG passphrase on the terminal."""
    passphrase = getpass.getpass("GPG passphrase: ")
    if confirm:
        confirm_pass = getpass.getpass("Confirm passphrase: ")
        if passphrase != confirm_pass:
            _error("Passphrases do not match")
            sys.exit(constants.EXIT_ERROR)
    return passphrase


def _get_passphrase_provider(new_file: bool = False) -> Callable[[], str]:
    """Return a passphrase provider callback."""

    def provider() -> str:
        # Try keyring first
        try:
            from ydoit.keyring_manager import KeyringManager

            km = KeyringManager()
            if km.is_available():
                cached = km.retrieve_passphrase()
                if cached:
                    return cached
        except Exception:
            pass

        passphrase = _prompt_passphrase(confirm=new_file)

        # Cache in keyring
        try:
            from ydoit.keyring_manager import KeyringManager

            km = KeyringManager()
            if km.is_available():
                km.store_passphrase(passphrase)
        except Exception:
            pass

        return passphrase

    return provider


# --- Output helpers ---


def _info(msg: str) -> None:
    print(f"{C.GREEN}✓{C.RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"{C.YELLOW}!{C.RESET} {msg}", file=sys.stderr)


def _error(msg: str) -> None:
    print(f"{C.RED}✗{C.RESET} {msg}", file=sys.stderr)


# --- Command handlers ---


def _cmd_type(args: argparse.Namespace) -> int:
    """Handle 'ydoit type <trigger>'."""
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider())
    config = cm.load()

    try:
        entry = config.get_entry(args.trigger)
    except EntryNotFoundError as e:
        _error(str(e))
        return constants.EXIT_ENTRY_NOT_FOUND

    typer = Typer(
        typing_delay_ms=config.settings.typing_delay_ms,
        hold_delay_ms=config.settings.hold_delay_ms,
    )

    try:
        typer.type_entry(entry, config.settings)
    except YdotoolError as e:
        _error(str(e))
        return constants.EXIT_YDOTOOL_NOT_RUNNING

    return constants.EXIT_OK


def _cmd_list(args: argparse.Namespace) -> int:
    """Handle 'ydoit list'."""
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider())

    if not cm.exists():
        _warn("No config file found. Run 'ydoit add' to create your first entry.")
        return constants.EXIT_OK

    config = cm.load()

    if not config.entries:
        _warn("No entries found. Run 'ydoit add' to create your first entry.")
        return constants.EXIT_OK

    # Calculate column widths
    trigger_w = max(len(e.trigger) for e in config.entries.values())
    label_w = max(len(e.display_label) for e in config.entries.values())
    key_w = max(len(e.keycombo) for e in config.entries.values())
    trigger_w = max(trigger_w, 7)
    label_w = max(label_w, 5)
    key_w = max(key_w, 8)

    # Header
    header = (
        f"{'Trigger':<{trigger_w}}  {'Label':<{label_w}}  "
        f"{'Shortcut':<{key_w}}  Type"
    )
    print(f"{C.BOLD}{header}{C.RESET}")
    print("─" * len(header))

    # Group by category
    categories: dict[str, list[Entry]] = {}
    for entry in config.entries.values():
        cat = entry.category or constants.DEFAULT_CATEGORY
        categories.setdefault(cat, []).append(entry)

    for cat_name in sorted(categories):
        entries = sorted(categories[cat_name], key=lambda e: e.trigger)
        if len(categories) > 1:
            print(f"\n{C.DIM}[{cat_name}]{C.RESET}")
        for entry in entries:
            type_str = "file" if entry.filename else "string"
            print(
                f"  {entry.trigger:<{trigger_w}}  {entry.display_label:<{label_w}}  "
                f"{entry.keycombo:<{key_w}}  {type_str}"
            )

    print(f"\n{C.DIM}{len(config.entries)} entries{C.RESET}")
    return constants.EXIT_OK


def _cmd_add(args: argparse.Namespace) -> int:
    """Handle 'ydoit add <trigger>'."""
    # Validate entry trigger
    try:
        Entry.validate_trigger(args.trigger)
    except InvalidEntryTriggerError as e:
        _error(str(e))
        return constants.EXIT_ERROR

    is_new = not ConfigManager().exists()
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider(new_file=is_new))

    config = cm.load()

    # Check for duplicate
    if args.trigger in config.entries:
        _error(f"Entry {args.trigger!r} already exists. Use 'ydoit edit' to modify it.")
        return constants.EXIT_ERROR

    # Check for shortcut conflict — must happen before saving
    if args.keycombo:
        sm = ShortcutManager()
        try:
            conflict = sm.find_conflict(args.keycombo)
        except GioNotAvailableError as e:
            _error(str(e))
            return constants.EXIT_ERROR
        if conflict:
            _warn(
                f"Shortcut {args.keycombo!r} conflicts with "
                f"{conflict.existing_source} shortcut {conflict.existing_name!r}"
                " — registering anyway"
            )

    entry = Entry(
        trigger=args.trigger,
        keycombo=args.keycombo or "",
        string=args.string or "",
        filename=args.filename or "",
        label=args.label or args.trigger,
        category=args.category or constants.DEFAULT_CATEGORY,
    )

    config.add_entry(entry)

    passphrase = _get_passphrase_provider()()
    cm.save(config, passphrase)

    # Sync shortcuts
    if entry.keycombo:
        sm.register_shortcut(entry)
        _info(f"Registered shortcut {entry.keycombo}")

    _info(f"Added entry {args.trigger!r}")
    return constants.EXIT_OK


def _cmd_remove(args: argparse.Namespace) -> int:
    """Handle 'ydoit remove <trigger>'."""
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider())
    config = cm.load()

    try:
        entry = config.get_entry(args.trigger)
    except EntryNotFoundError as e:
        _error(str(e))
        return constants.EXIT_ENTRY_NOT_FOUND

    # Confirm unless --yes
    if not args.yes:
        response = input(
            f"Remove entry {args.trigger!r} ({entry.display_label})? [y/N] "
        )
        if response.lower() not in ("y", "yes"):
            print("Cancelled")
            return constants.EXIT_OK

    config.remove_entry(args.trigger)

    passphrase = _get_passphrase_provider()()
    cm.save(config, passphrase)

    # Remove shortcut
    sm = ShortcutManager()
    sm.unregister_shortcut(args.trigger)

    _info(f"Removed entry {args.trigger!r}")
    return constants.EXIT_OK


def _cmd_sync_shortcuts(args: argparse.Namespace) -> int:
    """Handle 'ydoit sync-shortcuts'."""
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider())

    if not cm.exists():
        _warn("No config file found.")
        return constants.EXIT_OK

    config = cm.load()
    sm = ShortcutManager()
    try:
        result = sm.sync(config)
    except GioNotAvailableError as e:
        _error(str(e))
        return constants.EXIT_ERROR

    if result.total_changes == 0 and not result.errors:
        _info("Shortcuts are in sync")
    elif result.errors:
        _error(f"Sync complete: {result}")
    else:
        _info(f"Sync complete: {result}")

    for error in result.errors:
        _error(error)

    return constants.EXIT_OK if not result.errors else constants.EXIT_ERROR


def _cmd_export(args: argparse.Namespace) -> int:
    """Handle 'ydoit export'."""
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider())

    if not cm.exists():
        _error("No config file found.")
        return constants.EXIT_ERROR

    config = cm.load()
    output_path = Path(args.file)

    if args.plain:
        output_path.write_text(config.to_json(), encoding="utf-8")
        _info(f"Exported {len(config.entries)} entries to {output_path} (unencrypted)")
        _warn("This file contains sensitive data. Handle with care!")
    else:
        passphrase = _prompt_passphrase(confirm=True)
        export_cm = ConfigManager(config_dir=output_path.parent)
        export_cm.data_file = output_path
        export_cm.save(config, passphrase)
        _info(f"Exported {len(config.entries)} entries to {output_path} (encrypted)")

    return constants.EXIT_OK


def _cmd_import(args: argparse.Namespace) -> int:
    """Handle 'ydoit import'."""
    input_path = Path(args.file)
    if not input_path.is_file():
        _error(f"File not found: {input_path}")
        return constants.EXIT_ERROR

    # Detect format
    try:
        raw = input_path.read_text(encoding="utf-8")
        import_config = Config.from_json(raw)
        _info("Detected unencrypted JSON file")
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Try as encrypted
        import_passphrase = getpass.getpass("Import file passphrase: ")
        import_cm = ConfigManager(config_dir=input_path.parent)
        import_cm.data_file = input_path
        try:
            import_config = import_cm.load(import_passphrase)
        except DecryptionError:
            _error("Cannot decrypt import file")
            return constants.EXIT_DECRYPTION_FAILED

    is_new = not ConfigManager().exists()
    cm = ConfigManager(passphrase_provider=_get_passphrase_provider(new_file=is_new))

    if cm.exists():
        existing = cm.load()
        # Merge: imported entries override existing
        for trigger, entry in import_config.entries.items():
            existing.entries[trigger] = entry
        config = existing
        _info(f"Merged {len(import_config.entries)} entries into existing config")
    else:
        config = import_config
        _info(f"Imported {len(config.entries)} entries")

    passphrase = _get_passphrase_provider()()
    cm.save(config, passphrase)

    # Sync shortcuts
    sm = ShortcutManager()
    result = sm.sync(config)
    if result.total_changes:
        _info(f"Shortcuts: {result}")

    return constants.EXIT_OK


def _cmd_status(args: argparse.Namespace) -> int:
    """Handle 'ydoit status'."""
    print(f"{C.BOLD}ydoit v{__version__}{C.RESET}")
    print()

    # Config
    cm = ConfigManager()
    if cm.exists():
        # We can't show entry count without decrypting
        print(f"  Config:    {cm.data_file} {C.GREEN}(exists){C.RESET}")
    else:
        print(f"  Config:    {cm.data_file} {C.DIM}(not found){C.RESET}")

    # ydotoold
    if Typer.check_daemon():
        print(f"  ydotoold:  {C.GREEN}running{C.RESET}")
    else:
        print(f"  ydotoold:  {C.RED}not running{C.RESET}")

    # /dev/uinput
    if Typer.check_permissions():
        print(f"  uinput:    {C.GREEN}accessible{C.RESET}")
    else:
        print(f"  uinput:    {C.RED}not accessible{C.RESET}")

    # Keyring
    try:
        from ydoit.keyring_manager import KeyringManager

        km = KeyringManager()
        if km.is_available():
            cached = km.retrieve_passphrase()
            if cached:
                print(f"  Keyring:   {C.GREEN}available (passphrase cached){C.RESET}")
            else:
                print(f"  Keyring:   {C.GREEN}available (no cached passphrase){C.RESET}")
        else:
            print(f"  Keyring:   {C.YELLOW}not available{C.RESET}")
    except Exception:
        print(f"  Keyring:   {C.YELLOW}not available{C.RESET}")

    # Shortcuts
    sm = ShortcutManager()
    ydoit_shortcuts = sm.get_ydoit_shortcuts()
    print(f"  Shortcuts: {len(ydoit_shortcuts)} registered")

    print()
    return constants.EXIT_OK


def _cmd_version(args: argparse.Namespace) -> int:
    """Handle 'ydoit version'."""
    print(f"ydoit {__version__}")
    return constants.EXIT_OK


# --- Argument parser ---


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="ydoit",
        description="Keyboard shortcut auto-typer for GNOME/Wayland",
    )
    parser.add_argument(
        "--version", action="version", version=f"ydoit {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # type
    type_p = subparsers.add_parser("type", help="Type an entry's content")
    type_p.add_argument("trigger", help="Entry trigger to type")

    # list
    subparsers.add_parser("list", help="List all entries")

    # add
    add_p = subparsers.add_parser("add", help="Add a new entry")
    add_p.add_argument("trigger", help="Entry trigger (letters, digits, underscores, hyphens)")
    add_p.add_argument("--keycombo", "-k", required=True, help="Key combo (e.g. Super+F11)")
    add_p.add_argument("--string", "-s", default="", help="String to type")
    add_p.add_argument("--file", "-f", default="", dest="filename", help="File to type contents of")
    add_p.add_argument("--label", "-l", default="", help="Display label")
    add_p.add_argument("--category", "-c", default="", help="Category for grouping")
    # remove
    remove_p = subparsers.add_parser("remove", help="Remove an entry")
    remove_p.add_argument("trigger", help="Entry trigger to remove")
    remove_p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    # sync-shortcuts
    subparsers.add_parser("sync-shortcuts", help="Sync GNOME keybindings to match config")

    # export
    export_p = subparsers.add_parser("export", help="Export config to a file")
    export_p.add_argument("file", help="Output file path")
    export_p.add_argument("--plain", action="store_true", help="Export as unencrypted JSON")

    # import
    import_p = subparsers.add_parser("import", help="Import config from a file")
    import_p.add_argument("file", help="Input file path")

    # status
    subparsers.add_parser("status", help="Show system status")

    # version
    subparsers.add_parser("version", help="Print version")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # No subcommand: show help (GUI launch will be added in Phase 2)
        parser.print_help()
        return constants.EXIT_OK

    handlers = {
        "type": _cmd_type,
        "list": _cmd_list,
        "add": _cmd_add,
        "remove": _cmd_remove,
        "sync-shortcuts": _cmd_sync_shortcuts,
        "export": _cmd_export,
        "import": _cmd_import,
        "status": _cmd_status,
        "version": _cmd_version,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return constants.EXIT_ERROR

    try:
        return handler(args)
    except DecryptionError as e:
        _error(str(e))
        return constants.EXIT_DECRYPTION_FAILED
    except GpgNotFoundError as e:
        _error(str(e))
        return constants.EXIT_ERROR
    except YdotoolError as e:
        _error(str(e))
        return constants.EXIT_YDOTOOL_NOT_RUNNING
    except YdoitError as e:
        _error(str(e))
        return constants.EXIT_ERROR
    except KeyboardInterrupt:
        print()
        return constants.EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
