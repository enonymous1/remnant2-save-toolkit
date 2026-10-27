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
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path

STEAM_APP_ID = "1282100"
STEAM_GAME_FOLDER = "Remnant2"
WGS_PACKAGE_KEYWORD = "PerfectWorldEntertainment"


@dataclass(frozen=True)
class SaveFile:
    """One file inside a save location."""

    path: Path
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"path": str(self.path), "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class SaveLocation:
    """A directory that holds one set of Remnant 2 saves."""

    platform: str  # "steam" or "xbox-wgs"
    path: Path
    files: tuple[SaveFile, ...] = ()

    @property
    def size_bytes(self) -> int:
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
    try:
        return sorted(path.iterdir())
    except OSError:
        return []


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _directory_size(path: Path) -> int:
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
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        program_files = os.environ.get("ProgramW6432", r"C:\Program Files")
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


def _vdf_tokens(text: str) -> list[str]:
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


def _parse_vdf_object(tokens: list[str], pos: int) -> tuple[dict[str, object], int]:
    result: dict[str, object] = {}
    while pos < len(tokens) and tokens[pos] != "}":
        key = tokens[pos]
        pos += 1
        if pos >= len(tokens):
            break
        if tokens[pos] == "{":
            value, pos = _parse_vdf_object(tokens, pos + 1)
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
    parsed, _ = _parse_vdf_object(tokens, 2)
    return parsed


def _collect_vdf_paths(node: object, collected: list[str]) -> None:
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
    """Default roots plus any libraries their VDF files declare."""
    roots = list(extra_roots) if extra_roots else default_steam_roots()
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

    Each numeric child directory (one per Steam account) is its own
    location. If there are no numeric children but the ``Steam`` folder
    itself holds save files, the folder itself is the location.
    """
    profile = user_profile if user_profile is not None else default_user_profile()
    steam_dir = profile / "Saved Games" / STEAM_GAME_FOLDER / "Steam"
    if not steam_dir.is_dir():
        return []
    locations: list[SaveLocation] = []
    for child in _safe_listdir(steam_dir):
        if child.is_dir() and child.name.isdigit():
            locations.append(SaveLocation(platform="steam", path=child, files=_save_files(child)))
    if not locations:
        files = _save_files(steam_dir)
        locations.append(SaveLocation(platform="steam", path=steam_dir, files=files))
    return locations


def _userdata_save_location(userdata_dir: Path, user_id: str) -> SaveLocation | None:
    remote = userdata_dir / user_id / STEAM_APP_ID / "remote"
    nested = remote / "SAVED" / "SaveGames"
    if nested.is_dir():
        return SaveLocation(platform="steam", path=nested, files=_save_files(nested))
    if remote.is_dir():
        files = _save_files(remote)
        if files or nested.exists():
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
                if location is not None and location not in locations:
                    locations.append(location)
    return locations


def find_steam_locations(
    user_profile: Path | None = None,
    steam_roots: list[Path] | None = None,
) -> list[SaveLocation]:
    """All Steam save locations, Saved Games first, then userdata."""
    found = find_steam_saved_games_locations(user_profile)
    for location in find_steam_userdata_locations(steam_roots):
        if location not in found:
            found.append(location)
    return found


# --- Xbox / WGS ----------------------------------------------------------


def find_wgs_directory(
    packages_dir: Path | None = None,
    keyword: str = WGS_PACKAGE_KEYWORD,
) -> Path | None:
    """The ``SystemAppData\\wgs`` directory for the Remnant 2 package.

    An explicitly given *packages_dir* is searched on any platform, so a
    copied ``Packages`` tree can be inspected on Linux or macOS. When
    no directory is given, the search only runs where WGS actually
    lives (Windows, via ``%LOCALAPPDATA%``).
    """
    if packages_dir is None:
        if os.name != "nt":
            return None
        packages_dir = default_packages_dir()
    if packages_dir is None or not packages_dir.is_dir():
        return None
    needle = keyword.lower()
    candidates: list[Path] = []
    for package_dir in _safe_listdir(packages_dir):
        if package_dir.is_dir() and needle in package_dir.name.lower():
            wgs_dir = package_dir / "SystemAppData" / "wgs"
            if wgs_dir.is_dir():
                candidates.append(wgs_dir)
    # Prefer a wgs directory that actually holds containers: another
    # Perfect World package with only a ``t`` folder must not shadow
    # the Remnant 2 one.
    for candidate in candidates:
        if list_wgs_containers(candidate):
            return candidate
    return candidates[0] if candidates else None


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
    """Inspected containers for the Remnant 2 WGS directory, if found."""
    wgs_directory = find_wgs_directory(packages_dir, keyword)
    if wgs_directory is None:
        return []
    return [inspect_wgs_container(path) for path in list_wgs_containers(wgs_directory)]


def find_wgs_locations(
    packages_dir: Path | None = None,
    keyword: str = WGS_PACKAGE_KEYWORD,
) -> list[SaveLocation]:
    """WGS save sets as :class:`SaveLocation` objects for shared display."""
    locations: list[SaveLocation] = []
    for container in find_wgs_containers(packages_dir, keyword):
        for save_set in container.save_sets:
            locations.append(SaveLocation(platform="xbox-wgs", path=save_set.path, files=save_set.files))
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
