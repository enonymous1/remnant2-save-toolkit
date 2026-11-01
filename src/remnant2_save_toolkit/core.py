"""Find Remnant 2 save locations on disk.

This module only *finds* saves. It never copies, renames, or converts
anything. Copying is handled by :mod:`remnant2_save_toolkit.backup`, and
there is deliberately no Steam <-> Xbox save conversion anywhere in this
package: nothing in the original project proved the two formats are
interchangeable, so v2 does not claim they are.

Two layouts are supported:

* Steam: ``%USERPROFILE%\\Saved Games\\Remnant2\\Steam\\<steam-id>\\`` and,
  as a fallback, ``<Steam>/userdata/<user-id>/1282100/remote/`` (including
  ``remote/SAVED/SaveGames``). Custom Steam libraries are discovered by
  parsing ``libraryfolders.vdf``.
* Microsoft Store / Xbox (WGS): ``%LOCALAPPDATA%\\Packages\\`` folders
  containing ``PerfectWorldEntertainment``, under
  ``SystemAppData\\wgs``. WGS save sets are the child directories of each
  container directory (every subdirectory except ``t``). No save set is
  labelled "profile" or "game" by size or any other heuristic: the caller
  gets paths, file lists, and sizes, and decides for itself.

A directory is only reported as a location when it actually holds save
files. An empty Steam account folder, an empty userdata ``remote``, or
an empty WGS set is not a location; reporting it as one would make
"found" mean "a folder exists", which is useless to a user deciding
what to back up.
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

STEAM_APP_ID = "1282100"
STEAM_GAME_FOLDER = "Remnant2"
WGS_PACKAGE_KEYWORD = "PerfectWorldEntertainment"

Platform = Literal["steam", "xbox-wgs", "unknown"]


@dataclass(frozen=True)
class SaveFile:
    """One file inside a save location."""

    path: Path
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"path": str(self.path), "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class SaveLocation:
    """A directory that holds one set of Remnant 2 saves.

    ``files`` are the files listed for the location. ``total_size_bytes``
    is set when the finder knows a recursive total that differs from the
    sum of ``files`` (WGS sets, whose listed files are only the
    top-level extensionless blobs while the set may hold nested files).
    When it is ``None``, ``size_bytes`` is simply the sum of ``files``,
    so a Steam location and a WGS location never report two different
    sizes for the same set through different entry points.
    """

    platform: Platform
    path: Path
    files: tuple[SaveFile, ...] = ()
    total_size_bytes: int | None = None

    @property
    def size_bytes(self) -> int:
        if self.total_size_bytes is not None:
            return self.total_size_bytes
        return sum(item.size_bytes for item in self.files)

    def to_dict(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "files": [item.to_dict() for item in self.files],
        }


@dataclass(frozen=True)
class WgsSaveSet:
    """One child directory of a WGS container directory.

    ``files`` are the top-level files with no extension, which is how WGS
    stores save blobs. ``size_bytes`` walks the whole directory, so the
    two counts can legitimately disagree when a set has nested files.
    There is no ``label`` field on purpose: v1 guessed "profile_save"
    for the smallest set, which was never verified.
    """

    path: Path
    files: tuple[SaveFile, ...] = ()
    size_bytes: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "files": [item.to_dict() for item in self.files],
        }


@dataclass(frozen=True)
class WgsContainer:
    """A container directory inside a ``wgs`` directory."""

    path: Path
    save_sets: tuple[WgsSaveSet, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {"path": str(self.path), "save_sets": [item.to_dict() for item in self.save_sets]}


def _safe_listdir(path: Path) -> list[Path]:
    """Sorted children of *path*, or ``[]`` when it cannot be listed.

    A missing directory is silent: callers probe candidate paths, and
    "not there" is an ordinary answer. A permission error is logged as
    a warning instead, because it means a location was *skipped*, not
    that no saves exist, and silently returning ``[]`` would make the
    two indistinguishable.
    """
    try:
        return sorted(path.iterdir())
    except PermissionError:
        logger.warning("Cannot list directory (permission denied): %s", path)
        return []
    except OSError:
        return []


def _safe_file_size(path: Path) -> int:
    """Size of *path*, or ``0`` when it disappears or cannot be read."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _directory_size(path: Path) -> int:
    """Recursive size of *path*, for display only.

    Used for WGS sets, whose blobs can nest below the top level. A
    listing failure returns 0 for the whole directory, so callers must
    not treat this as an exact accounting figure.
    """
    total = 0
    try:
        entries = list(path.rglob("*"))
    except OSError:
        return 0
    for entry in entries:
        if entry.is_file():
            total += _safe_file_size(entry)
    return total


def _save_files(directory: Path) -> tuple[SaveFile, ...]:
    """Direct-child files of *directory*, sorted by name."""
    found: list[SaveFile] = []
    for entry in _safe_listdir(directory):
        if entry.is_file():
            found.append(SaveFile(path=entry, size_bytes=_safe_file_size(entry)))
    return tuple(found)


def _dedupe_by_path(locations: list[SaveLocation]) -> list[SaveLocation]:
    """Drop duplicate locations that name the same directory.

    Deduplication is by path, not by full dataclass equality: the same
    directory reached through two routes (or re-scanned after a file
    changed) is one location, even if its file list differs. On Windows
    the key is case-folded, because ``Steam`` and ``steam`` are the same
    folder there and different folders elsewhere.
    """
    seen: set[str] = set()
    unique: list[SaveLocation] = []
    for location in locations:
        key = os.path.normcase(str(location.path)) if os.name == "nt" else str(location.path)
        if key not in seen:
            seen.add(key)
            unique.append(location)
    return unique


def default_user_profile() -> Path:
    """The current user's home directory (``%USERPROFILE%`` on Windows)."""
    return Path.home()


def _registry_steam_path() -> Path | None:
    """Steam's install path from the Windows registry, when available.

    ``winreg`` is loaded through :func:`importlib.import_module` so
    static checking on non-Windows platforms does not need its
    Windows-only attribute stubs.
    """
    if os.name != "nt":
        return None
    try:
        winreg = importlib.import_module("winreg")
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            value, _ = winreg.QueryValueEx(key, "SteamPath")
    except OSError:
        return None
    if isinstance(value, str) and value:
        return Path(value)
    return None


def default_steam_roots() -> list[Path]:
    """Candidate Steam install roots, in the order they should be tried."""
    roots: list[Path] = []
    if os.name == "nt":
        # Uppercase names: Windows environment lookup is case-insensitive,
        # so these resolve the same variables as the mixed-case spellings.
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        program_files = os.environ.get("PROGRAMW6432", r"C:\Program Files")
        roots.append(Path(program_files_x86) / "Steam")
        roots.append(Path(program_files) / "Steam")
        registry_path = _registry_steam_path()
        if registry_path is not None:
            roots.append(registry_path)
    else:
        home = Path.home()
        roots.append(home / ".steam" / "steam")
        roots.append(home / ".local" / "share" / "Steam")
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique.append(root)
    return unique


def default_packages_dir() -> Path | None:
    """``%LOCALAPPDATA%\\Packages`` on Windows, else ``None``."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / "Packages"


# --- libraryfolders.vdf -------------------------------------------------

_MAX_VDF_DEPTH = 64


def _vdf_tokens(text: str) -> list[str]:
    """Tokenise a VDF document into quoted strings and braces.

    Returns ``[]`` for anything unexpected (an unterminated string, a
    stray character): the caller treats that as "unparseable" rather
    than raising, so a malformed file never takes down discovery.
    ``//`` comments are skipped.
    """
    tokens: list[str] = []
    i = 0
    while i < len(text):
        char = text[i]
        if char.isspace():
            i += 1
        elif char in "{}":
            tokens.append(char)
            i += 1
        elif char == '"':
            end = text.find('"', i + 1)
            if end == -1:
                return []
            tokens.append(text[i + 1 : end])
            i = end + 1
        elif char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
        else:
            return []
    return tokens


def _parse_vdf_object(tokens: list[str], pos: int, depth: int = 0) -> tuple[dict[str, object], int]:
    """Parse one VDF object starting after its opening brace.

    The depth cap exists because this parser is recursive: a hostile
    or corrupted file with thousands of nested objects would otherwise
    crash discovery with ``RecursionError`` instead of being ignored.
    """
    if depth > _MAX_VDF_DEPTH:
        raise ValueError("VDF nesting too deep")
    result: dict[str, object] = {}
    while pos < len(tokens) and tokens[pos] != "}":
        key = tokens[pos]
        pos += 1
        if pos >= len(tokens):
            break
        if tokens[pos] == "{":
            value, pos = _parse_vdf_object(tokens, pos + 1, depth + 1)
            if pos < len(tokens) and tokens[pos] == "}":
                pos += 1
            result[key] = value
        else:
            result[key] = tokens[pos]
            pos += 1
    return result, pos


def parse_libraryfolders_vdf(text: str) -> dict[str, object]:
    """Parse a ``libraryfolders.vdf`` document, tolerantly.

    Returns an empty dict for anything unparseable instead of raising:
    a malformed VDF file must never take down save discovery.
    """
    tokens = _vdf_tokens(text)
    if len(tokens) < 2 or tokens[0] != "libraryfolders" or tokens[1] != "{":
        return {}
    try:
        parsed, _ = _parse_vdf_object(tokens, 2)
    except (RecursionError, ValueError):
        return {}
    return parsed


def _collect_vdf_paths(node: object, collected: list[str]) -> None:
    """Collect every ``"path"`` value in a parsed VDF tree, in order."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "path" and isinstance(value, str) and value:
                collected.append(value)
            else:
                _collect_vdf_paths(value, collected)


def library_paths_from_vdf(steam_root: Path) -> list[Path]:
    """Library paths declared in ``<steam_root>/steamapps/libraryfolders.vdf``."""
    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    parsed = parse_libraryfolders_vdf(text)
    collected: list[str] = []
    _collect_vdf_paths(parsed, collected)
    paths: list[Path] = []
    for raw in collected:
        candidate = Path(raw)
        if candidate not in paths:
            paths.append(candidate)
    return paths


def discover_steam_roots(extra_roots: list[Path] | None = None) -> list[Path]:
    """User-supplied roots first, then defaults, then VDF-declared libraries.

    Extra roots are *additive*: passing ``--steam-root`` for one custom
    library must never silently drop the Program Files, registry, and
    default locations a user did not mention.
    """
    roots: list[Path] = []
    for root in list(extra_roots or []) + default_steam_roots():
        if root not in roots:
            roots.append(root)
    expanded: list[Path] = []
    for root in roots:
        if root not in expanded:
            expanded.append(root)
        for library in library_paths_from_vdf(root):
            if library not in expanded:
                expanded.append(library)
    return expanded


# --- Steam ---------------------------------------------------------------


def find_steam_saved_games_locations(user_profile: Path | None = None) -> list[SaveLocation]:
    """Locations under ``Saved Games\\Remnant2\\Steam``.

    Each numeric child directory (one per Steam account) that holds
    files is its own location. If there are no numeric children with
    files but the ``Steam`` folder itself holds save files, the folder
    itself is the location. Empty folders are not locations.
    """
    profile = user_profile if user_profile is not None else default_user_profile()
    steam_dir = profile / "Saved Games" / STEAM_GAME_FOLDER / "Steam"
    if not steam_dir.is_dir():
        return []
    locations: list[SaveLocation] = []
    for child in _safe_listdir(steam_dir):
        if child.is_dir() and child.name.isdigit():
            files = _save_files(child)
            if files:
                locations.append(SaveLocation(platform="steam", path=child, files=files))
    if not locations:
        files = _save_files(steam_dir)
        if files:
            locations.append(SaveLocation(platform="steam", path=steam_dir, files=files))
    return locations


def _userdata_save_location(userdata_dir: Path, user_id: str) -> SaveLocation | None:
    """The save location for one userdata account, or ``None``.

    ``remote/SAVED/SaveGames`` wins when it holds files. Otherwise the
    ``remote`` folder itself is the location, but only when it holds
    files: an empty ``remote`` (or an empty nested folder) is not a
    location, even though the directory exists.
    """
    remote = userdata_dir / user_id / STEAM_APP_ID / "remote"
    nested = remote / "SAVED" / "SaveGames"
    if nested.is_dir():
        nested_files = _save_files(nested)
        if nested_files:
            return SaveLocation(platform="steam", path=nested, files=nested_files)
    if remote.is_dir():
        files = _save_files(remote)
        if files:
            return SaveLocation(platform="steam", path=remote, files=files)
    return None


def find_steam_userdata_locations(steam_roots: list[Path] | None = None) -> list[SaveLocation]:
    """Locations under ``<Steam>/userdata/<user-id>/1282100/remote``."""
    locations: list[SaveLocation] = []
    for root in discover_steam_roots(steam_roots):
        userdata_dir = root / "userdata"
        if not userdata_dir.is_dir():
            continue
        for user_dir in _safe_listdir(userdata_dir):
            if user_dir.is_dir() and user_dir.name.isdigit():
                location = _userdata_save_location(userdata_dir, user_dir.name)
                if location is not None:
                    locations.append(location)
    return _dedupe_by_path(locations)


def find_steam_locations(
    user_profile: Path | None = None,
    steam_roots: list[Path] | None = None,
) -> list[SaveLocation]:
    """All Steam save locations, Saved Games first, then userdata."""
    found = find_steam_saved_games_locations(user_profile)
    found.extend(find_steam_userdata_locations(steam_roots))
    return _dedupe_by_path(found)


# --- Xbox / WGS ----------------------------------------------------------


def find_wgs_directories(
    packages_dir: Path | None = None,
    keyword: str = WGS_PACKAGE_KEYWORD,
) -> list[Path]:
    """Every matching ``SystemAppData\\wgs`` directory, best first.

    An explicitly given *packages_dir* is searched on any platform, so a
    copied ``Packages`` tree can be inspected on Linux or macOS. When
    no directory is given, the search only runs where WGS actually
    lives (Windows, via ``%LOCALAPPDATA%``). Directories that actually
    hold containers come first, so another Perfect World package with
    only a ``t`` folder never shadows the Remnant 2 one, but no
    matching directory is dropped: callers that used to see only the
    first one were silently losing saves from a second package.
    """
    if packages_dir is None:
        if os.name != "nt":
            return []
        packages_dir = default_packages_dir()
    if packages_dir is None or not packages_dir.is_dir():
        return []
    needle = keyword.lower()
    candidates: list[Path] = []
    for package_dir in _safe_listdir(packages_dir):
        if package_dir.is_dir() and needle in package_dir.name.lower():
            wgs_dir = package_dir / "SystemAppData" / "wgs"
            if wgs_dir.is_dir():
                candidates.append(wgs_dir)
    with_containers = [candidate for candidate in candidates if list_wgs_containers(candidate)]
    without_containers = [candidate for candidate in candidates if candidate not in with_containers]
    return with_containers + without_containers


def find_wgs_directory(
    packages_dir: Path | None = None,
    keyword: str = WGS_PACKAGE_KEYWORD,
) -> Path | None:
    """The best matching ``SystemAppData\\wgs`` directory, or ``None``.

    Kept for backwards compatibility; prefer :func:`find_wgs_directories`
    when a second matching package may hold saves.
    """
    directories = find_wgs_directories(packages_dir, keyword)
    return directories[0] if directories else None


def list_wgs_containers(wgs_directory: Path) -> list[Path]:
    """Container directories: every subdirectory except ``t``, sorted."""
    if not wgs_directory.is_dir():
        return []
    return [entry for entry in _safe_listdir(wgs_directory) if entry.is_dir() and entry.name.lower() != "t"]


def inspect_wgs_container(container: Path) -> WgsContainer:
    """Save sets inside one container directory."""
    save_sets: list[WgsSaveSet] = []
    for child in _safe_listdir(container):
        if not child.is_dir():
            continue
        extensionless = tuple(item for item in _save_files(child) if not Path(item.path.name).suffix)
        save_sets.append(WgsSaveSet(path=child, files=extensionless, size_bytes=_directory_size(child)))
    return WgsContainer(path=container, save_sets=tuple(save_sets))


def find_wgs_containers(
    packages_dir: Path | None = None,
    keyword: str = WGS_PACKAGE_KEYWORD,
) -> list[WgsContainer]:
    """Inspected containers for every matching WGS directory, if found."""
    containers: list[WgsContainer] = []
    for wgs_directory in find_wgs_directories(packages_dir, keyword):
        containers.extend(inspect_wgs_container(path) for path in list_wgs_containers(wgs_directory))
    return containers


def find_wgs_locations(
    packages_dir: Path | None = None,
    keyword: str = WGS_PACKAGE_KEYWORD,
) -> list[SaveLocation]:
    """WGS save sets as :class:`SaveLocation` objects for shared display.

    ``size_bytes`` for a WGS location is the set's recursive total (via
    ``total_size_bytes``), matching the container view, even though
    ``files`` lists only the top-level extensionless blobs. A set with
    no listed files and a zero total is empty and is not reported.
    """
    locations: list[SaveLocation] = []
    for container in find_wgs_containers(packages_dir, keyword):
        for save_set in container.save_sets:
            if not save_set.files and save_set.size_bytes == 0:
                continue
            locations.append(
                SaveLocation(
                    platform="xbox-wgs",
                    path=save_set.path,
                    files=save_set.files,
                    total_size_bytes=save_set.size_bytes,
                )
            )
    return locations


def find_all_locations(
    user_profile: Path | None = None,
    steam_roots: list[Path] | None = None,
    packages_dir: Path | None = None,
) -> list[SaveLocation]:
    """Steam locations followed by Xbox/WGS locations."""
    return find_steam_locations(user_profile, steam_roots) + find_wgs_locations(packages_dir)


def inspect_directory(path: Path) -> SaveLocation:
    """Describe one directory as a save location without guessing its platform."""
    if not path.is_dir():
        raise FileNotFoundError(f"Not a directory: {path}")
    return SaveLocation(platform="unknown", path=path, files=_save_files(path))
