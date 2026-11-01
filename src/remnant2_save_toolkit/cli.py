"""Command line interface: find saves, inspect a directory, back it up.

Exit codes: ``0`` for success, including ``find`` with no locations
found; ``2`` for a refused or failed ``inspect``/``backup`` or a GUI
that cannot start. ``argparse`` errors are ``2`` as usual. JSON output
carries ``schema_version`` so consumers can detect format changes.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from remnant2_save_toolkit import __version__
from remnant2_save_toolkit.backup import BackupError, backup_directory
from remnant2_save_toolkit.core import (
    SaveLocation,
    find_all_locations,
    inspect_directory,
)

SCHEMA_VERSION = 1


def _print_location(location: SaveLocation) -> None:
    """Print one location and its files in human-readable form."""
    print(f"[{location.platform}] {location.path} ({len(location.files)} files, {location.size_bytes} bytes)")
    for item in location.files:
        print(f"    {item.path.name} ({item.size_bytes} bytes)")


def _cmd_find(args: argparse.Namespace) -> int:
    """List Steam and Xbox/WGS save locations."""
    locations = find_all_locations(
        user_profile=args.user_profile,
        steam_roots=args.steam_root if args.steam_root else None,
        packages_dir=args.packages_dir,
    )
    if args.json:
        print(
            json.dumps(
                {"schema_version": SCHEMA_VERSION, "locations": [item.to_dict() for item in locations]}, indent=2
            )
        )
        return 0
    if not locations:
        print("No save locations found.")
        return 0
    for location in locations:
        _print_location(location)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    """List the files in one save directory."""
    try:
        location = inspect_directory(args.path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({**location.to_dict(), "schema_version": SCHEMA_VERSION}, indent=2))
        return 0
    _print_location(location)
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    """Copy one save directory into a new hash-verified, timestamped backup."""
    try:
        result = backup_directory(
            args.source,
            args.backup_root,
            timestamp=args.timestamp,
            dry_run=args.dry_run,
        )
    except BackupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({**result.to_dict(), "schema_version": SCHEMA_VERSION}, indent=2))
        return 0
    if result.dry_run:
        print(f"Would back up {result.source} to {result.destination} ({len(result.files)} files).")
    else:
        print(f"Backed up {result.source} to {result.destination} ({len(result.files)} files, hash-verified).")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    """Open the graphical interface.

    PyQt6 is imported first, separately from the GUI module: a broken
    import *inside* ``gui.py`` must not be misreported as "PyQt6 is not
    installed".
    """
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        print(
            'Error: the GUI needs PyQt6, which is not installed.\nInstall it with: pip install ".[gui]"',
            file=sys.stderr,
        )
        return 2
    try:
        from remnant2_save_toolkit.gui import run_gui  # noqa: PLC0415 - optional dep
    except ImportError as exc:
        print(f"Error: the GUI could not be imported: {exc}", file=sys.stderr)
        return 2
    return run_gui(
        user_profile=args.user_profile,
        steam_roots=args.steam_root if args.steam_root else None,
        packages_dir=args.packages_dir,
    )


def _add_location_args(parser: argparse.ArgumentParser) -> None:
    """The shared ``--user-profile`` / ``--steam-root`` / ``--packages-dir`` options.

    Defined once and reused by ``find`` and ``gui``: the two commands
    previously defined these blocks separately, and a flag added to one
    would silently be missing from the other.
    """
    parser.add_argument("--user-profile", type=Path, default=None)
    parser.add_argument("--steam-root", type=Path, action="append", default=[])
    parser.add_argument("--packages-dir", type=Path, default=None)


def build_parser() -> argparse.ArgumentParser:
    """Build the ``remnant2-saves`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="remnant2-saves",
        description="Find and back up Remnant 2 saves. Does not convert saves between platforms.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show debug logging (warnings, including permission-denied skips, are shown by default).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress warnings; show errors only.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    find_parser = subparsers.add_parser("find", help="Find Steam and Xbox/WGS save locations.")
    _add_location_args(find_parser)
    find_parser.add_argument("--json", action="store_true")
    find_parser.set_defaults(func=_cmd_find)

    inspect_parser = subparsers.add_parser("inspect", help="List the files in one save directory.")
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.set_defaults(func=_cmd_inspect)

    backup_parser = subparsers.add_parser(
        "backup", help="Copy one save directory into a new hash-verified, timestamped backup."
    )
    backup_parser.add_argument("source", type=Path)
    backup_parser.add_argument("--backup-root", type=Path, required=True)
    backup_parser.add_argument("--timestamp", default=None)
    backup_parser.add_argument("--dry-run", action="store_true")
    backup_parser.add_argument("--json", action="store_true")
    backup_parser.set_defaults(func=_cmd_backup)

    gui_parser = subparsers.add_parser("gui", help="Open the graphical interface (needs PyQt6).")
    _add_location_args(gui_parser)
    gui_parser.set_defaults(func=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, configure logging, and dispatch to the subcommand."""
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    elif args.quiet:
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.WARNING)
    return int(args.func(args))
