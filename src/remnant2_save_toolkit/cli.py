"""Command line interface: find saves, inspect a directory, back it up."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from remnant2_save_toolkit import __version__
from remnant2_save_toolkit.backup import BackupError, backup_directory
from remnant2_save_toolkit.core import (
    SaveLocation,
    find_all_locations,
    inspect_directory,
)


def _print_location(location: SaveLocation) -> None:
    print(f"[{location.platform}] {location.path} ({len(location.files)} files, {location.size_bytes} bytes)")
    for item in location.files:
        print(f"    {item.path.name} ({item.size_bytes} bytes)")


def _cmd_find(args: argparse.Namespace) -> int:
    locations = find_all_locations(
        user_profile=args.user_profile,
        steam_roots=args.steam_root if args.steam_root else None,
        packages_dir=args.packages_dir,
    )
    if args.json:
        print(json.dumps([item.to_dict() for item in locations], indent=2))
        return 0
    if not locations:
        print("No save locations found.")
        return 0
    for location in locations:
        _print_location(location)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        location = inspect_directory(args.path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(location.to_dict(), indent=2))
        return 0
    _print_location(location)
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
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
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    if result.dry_run:
        print(f"Would back up {result.source} to {result.destination} ({len(result.files)} files).")
    else:
        print(f"Backed up {result.source} to {result.destination} ({len(result.files)} files, hash-verified).")
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    try:
        from remnant2_save_toolkit.gui import run_gui  # noqa: PLC0415 - optional dep
    except ImportError:
        print(
            'Error: the GUI needs PyQt6, which is not installed.\nInstall it with: pip install ".[gui]"',
            file=sys.stderr,
        )
        return 2
    return run_gui(
        user_profile=args.user_profile,
        steam_roots=args.steam_root if args.steam_root else None,
        packages_dir=args.packages_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remnant2-saves",
        description="Find and back up Remnant 2 saves. Does not convert saves between platforms.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    find_parser = subparsers.add_parser("find", help="Find Steam and Xbox/WGS save locations.")
    find_parser.add_argument("--user-profile", type=Path, default=None)
    find_parser.add_argument("--steam-root", type=Path, action="append", default=[])
    find_parser.add_argument("--packages-dir", type=Path, default=None)
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
    gui_parser.add_argument("--user-profile", type=Path, default=None)
    gui_parser.add_argument("--steam-root", type=Path, action="append", default=[])
    gui_parser.add_argument("--packages-dir", type=Path, default=None)
    gui_parser.set_defaults(func=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
