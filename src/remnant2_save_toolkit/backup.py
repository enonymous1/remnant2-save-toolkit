"""Verified, never-overwriting backups of a save directory.

A backup is a full copy of one save directory into a new, timestamped
directory under a backup root. Every copied file is hashed before and
after the copy, and a ``backup_manifest.json`` is written only after
every hash matches. An existing backup directory is never overwritten:
a colliding timestamp gets a ``-2``, ``-3``, ... suffix instead.

This replaces v1's ``.old`` behaviour, which copied or renamed over a
single ``<name>.old`` file in place, silently destroying the previous
backup on a second run.

Every failure in this module is a :class:`BackupError` (or a subclass),
never a bare ``OSError`` or traceback: the CLI catches ``BackupError``
and reports it as a failed backup, and a partial destination is always
removed before the error propagates. A backup taken while the game is
running can still capture a half-written save pair; hash verification
proves the copy matches the source at copy time, not that the source
was stable. Close the game first.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_MANIFEST_NAME = "backup_manifest.json"
_TIMESTAMP_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_TIMESTAMP_LENGTH = 64
_CHUNK_SIZE = 1024 * 1024


class BackupError(Exception):
    """A backup was refused or failed. The CLI reports this, not a traceback."""


class InvalidBackupError(BackupError):
    """Bad input: missing source, bad timestamp, unsafe destination, symlink."""


class BackupVerificationError(BackupError):
    """A copied file failed hash verification; the partial backup was removed."""


@dataclass(frozen=True)
class BackedUpFile:
    """One file in a backup, with its verified hash."""

    relative_path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class BackupResult:
    """The outcome of :func:`backup_directory`."""

    source: Path
    destination: Path
    timestamp: str
    files: tuple[BackedUpFile, ...]
    verified: bool
    dry_run: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "destination": str(self.destination),
            "timestamp": self.timestamp,
            "verified": self.verified,
            "dry_run": self.dry_run,
            "files": [item.to_dict() for item in self.files],
        }


def default_timestamp() -> str:
    """Local-time label for a backup folder name, not a clock.

    Second resolution is enough because collisions get a ``-2`` suffix.
    Never sort backups from different machines by this string alone:
    it carries no timezone, so ordering across machines is not defined.
    """
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def validate_timestamp(timestamp: str) -> str:
    """Reject timestamps that could escape the backup root as a path.

    The character allowlist blocks ``/`` and ``..`` tricks; the length
    cap exists because an over-long name fails later at ``mkdir`` with
    an uncaught ``OSError``, and this module promises ``BackupError``
    for every refusal.
    """
    if (
        not timestamp
        or timestamp in {".", ".."}
        or len(timestamp) > _MAX_TIMESTAMP_LENGTH
        or not _TIMESTAMP_RE.match(timestamp)
    ):
        raise InvalidBackupError(
            f"Invalid timestamp {timestamp!r}: use up to {_MAX_TIMESTAMP_LENGTH} letters, digits, '.', '_' or '-' only."
        )
    return timestamp


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, streamed in 1 MiB chunks so large saves are fine."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_files(source: Path) -> list[Path]:
    """All files under *source*, sorted by relative path.

    Symlinks are refused, not followed: a symlink inside a save folder
    could point anywhere on disk, and a backup tool that silently
    copies the target's contents is exfiltrating whatever it points at.
    The source directory itself being a symlink is refused for the same
    reason.
    """
    if source.is_symlink():
        raise InvalidBackupError(f"Refusing to back up a symlinked directory: {source}")
    collected: list[Path] = []
    for entry in source.rglob("*"):
        if entry.is_symlink():
            raise InvalidBackupError(f"Refusing to back up symlinked file: {entry}")
        if entry.is_file():
            collected.append(entry)
    return sorted(collected, key=lambda entry: entry.relative_to(source).as_posix())


def _copy_no_symlink(source: str, destination: str) -> None:
    """Copy one file, refusing symlinks a second time at copy time.

    ``_collect_files`` already refuses symlinks, but the copy phase
    must not depend on that: a file swapped for a symlink between the
    two phases would otherwise be followed by ``copytree``. The
    parameters are ``str`` because that is what ``shutil.copytree``
    passes to its ``copy_function``.
    """
    if Path(source).is_symlink():
        raise InvalidBackupError(f"Refusing to back up symlinked file: {source}")
    shutil.copy2(source, destination)


def _destination_for(backup_root: Path, source: Path, timestamp: str) -> Path:
    """A fresh destination under *backup_root*, never an existing folder.

    A colliding timestamp gets a ``-2``, ``-3``, ... suffix. The cap of
    100 exists so a backup root full of colliding folders fails loudly
    instead of looping forever.
    """
    base = backup_root / f"{source.name}-{timestamp}"
    if not base.exists():
        return base
    counter = 2
    while True:
        candidate = backup_root / f"{source.name}-{timestamp}-{counter}"
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 100:
            raise InvalidBackupError(f"Too many existing backups for timestamp {timestamp!r}.")


def backup_directory(
    source: Path,
    backup_root: Path,
    timestamp: str | None = None,
    *,
    dry_run: bool = False,
) -> BackupResult:
    """Copy *source* into a new timestamped directory under *backup_root*.

    Raises :class:`BackupError` when the source is not a directory, the
    backup root sits inside the source, a timestamp or path is invalid,
    or a copied file fails hash verification (in which case the partial
    destination is removed). Every ``OSError`` from the filesystem is
    converted to ``BackupError`` here, so callers never see a traceback
    for an ordinary filesystem failure.
    """
    stamp = validate_timestamp(timestamp if timestamp is not None else default_timestamp())
    if not source.is_dir():
        raise InvalidBackupError(f"Save directory not found: {source}")
    try:
        source_resolved = source.resolve()
        root_resolved = backup_root.resolve()
    except OSError as exc:
        raise InvalidBackupError(f"Cannot resolve backup paths: {exc}") from exc
    if root_resolved == source_resolved or root_resolved.is_relative_to(source_resolved):
        raise InvalidBackupError("Backup root must not be inside the save directory being backed up.")

    try:
        source_files = _collect_files(source)
        hashed = tuple(
            BackedUpFile(
                relative_path=entry.relative_to(source).as_posix(),
                size_bytes=entry.stat().st_size,
                sha256=sha256_file(entry),
            )
            for entry in source_files
        )
    except OSError as exc:
        raise BackupError(f"Could not read source files: {exc}") from exc
    destination = _destination_for(backup_root, source, stamp)
    result = BackupResult(
        source=source,
        destination=destination,
        timestamp=stamp,
        files=hashed,
        verified=False,
        dry_run=dry_run,
    )
    if dry_run:
        return result

    try:
        destination.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise InvalidBackupError(f"Cannot create backup directory {destination}: {exc}") from exc
    try:
        shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=_copy_no_symlink)
        for backed_up in hashed:
            copied = destination / backed_up.relative_path
            if not copied.is_file() or sha256_file(copied) != backed_up.sha256:
                raise BackupVerificationError(f"Hash verification failed for {backed_up.relative_path}.")
    except BackupError:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise BackupError(f"Backup copy failed: {exc}") from exc
    manifest = {
        "source": str(source),
        "destination": str(destination),
        "timestamp": stamp,
        "verified": True,
        "files": [item.to_dict() for item in hashed],
    }
    try:
        (destination / _MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise BackupError(f"Could not write backup manifest: {exc}") from exc
    return BackupResult(
        source=source,
        destination=destination,
        timestamp=stamp,
        files=hashed,
        verified=True,
        dry_run=False,
    )
