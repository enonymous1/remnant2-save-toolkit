"""Verified, never-overwriting backups of a save directory.

A backup is a full copy of one save directory into a new, timestamped
directory under a backup root. Every copied file is hashed before and
after the copy, and a ``backup_manifest.json`` is written only after
every hash matches. An existing backup directory is never overwritten:
a colliding timestamp gets a ``-2``, ``-3``, ... suffix instead.

This replaces v1's ``.old`` behaviour, which copied or renamed over a
single ``<name>.old`` file in place, silently destroying the previous
backup on a second run.
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
_CHUNK_SIZE = 1024 * 1024


class BackupError(ValueError):
    """A backup was refused or failed verification."""


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
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def validate_timestamp(timestamp: str) -> str:
    """Reject timestamps that could escape the backup root as a path."""
    if not timestamp or timestamp in {".", ".."} or not _TIMESTAMP_RE.match(timestamp):
        raise BackupError(f"Invalid timestamp {timestamp!r}: use letters, digits, '.', '_' or '-' only.")
    return timestamp


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_files(source: Path) -> list[Path]:
    return sorted(
        (entry for entry in source.rglob("*") if entry.is_file()),
        key=lambda entry: entry.relative_to(source).as_posix(),
    )


def _destination_for(backup_root: Path, source: Path, timestamp: str) -> Path:
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
            raise BackupError(f"Too many existing backups for timestamp {timestamp!r}.")


def backup_directory(
    source: Path,
    backup_root: Path,
    timestamp: str | None = None,
    *,
    dry_run: bool = False,
) -> BackupResult:
    """Copy *source* into a new timestamped directory under *backup_root*.

    Raises :class:`BackupError` when the source is not a directory, the
    backup root sits inside the source, or a copied file fails hash
    verification (in which case the partial destination is removed).
    """
    stamp = validate_timestamp(timestamp if timestamp is not None else default_timestamp())
    if not source.is_dir():
        raise BackupError(f"Save directory not found: {source}")
    try:
        source_resolved = source.resolve()
        root_resolved = backup_root.resolve()
    except OSError as exc:
        raise BackupError(f"Cannot resolve backup paths: {exc}") from exc
    if root_resolved == source_resolved or root_resolved.is_relative_to(source_resolved):
        raise BackupError("Backup root must not be inside the save directory being backed up.")

    source_files = _collect_files(source)
    hashed = tuple(
        BackedUpFile(
            relative_path=entry.relative_to(source).as_posix(),
            size_bytes=entry.stat().st_size,
            sha256=sha256_file(entry),
        )
        for entry in source_files
    )
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

    destination.mkdir(parents=True, exist_ok=False)
    try:
        shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=shutil.copy2)
        for backed_up in hashed:
            copied = destination / backed_up.relative_path
            if not copied.is_file() or sha256_file(copied) != backed_up.sha256:
                raise BackupError(f"Hash verification failed for {backed_up.relative_path}.")
    except (OSError, BackupError):
        shutil.rmtree(destination, ignore_errors=True)
        raise
    manifest = {
        "source": str(source),
        "destination": str(destination),
        "timestamp": stamp,
        "verified": True,
        "files": [item.to_dict() for item in hashed],
    }
    (destination / _MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return BackupResult(
        source=source,
        destination=destination,
        timestamp=stamp,
        files=hashed,
        verified=True,
        dry_run=False,
    )
