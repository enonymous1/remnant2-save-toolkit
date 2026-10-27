"""Tests for verified, never-overwriting backups."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from remnant2_save_toolkit.backup import (
    BackupError,
    backup_directory,
    sha256_file,
    validate_timestamp,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_backup_copies_tree_and_verifies(save_source: Path, tmp_path: Path) -> None:
    backup_root = tmp_path / "backups"
    result = backup_directory(save_source, backup_root, timestamp="20260101-120000")
    assert result.verified is True
    assert result.dry_run is False
    assert result.destination == backup_root / "save-set-20260101-120000"
    assert len(result.files) == 2
    for backed_up in result.files:
        copied = result.destination / backed_up.relative_path
        assert copied.is_file()
        assert _hash(copied) == backed_up.sha256
        assert copied.read_bytes() == (save_source / backed_up.relative_path).read_bytes()
    manifest = json.loads((result.destination / "backup_manifest.json").read_text(encoding="utf-8"))
    assert manifest["verified"] is True
    assert manifest["source"] == str(save_source)
    assert len(manifest["files"]) == 2


def test_backup_never_overwrites_existing_timestamp(save_source: Path, tmp_path: Path) -> None:
    backup_root = tmp_path / "backups"
    first = backup_directory(save_source, backup_root, timestamp="20260101-120000")
    (first.destination / "profile.sav").write_text("MUTATED BY TEST\n", encoding="utf-8")
    second = backup_directory(save_source, backup_root, timestamp="20260101-120000")
    assert second.destination != first.destination
    assert second.destination.name == "save-set-20260101-120000-2"
    assert (first.destination / "profile.sav").read_text(encoding="utf-8") == "MUTATED BY TEST\n"
    assert (second.destination / "profile.sav").read_text(encoding="utf-8") == "fake profile\n"


def test_backup_dry_run_writes_nothing(save_source: Path, tmp_path: Path) -> None:
    backup_root = tmp_path / "backups"
    result = backup_directory(save_source, backup_root, timestamp="20260101-120000", dry_run=True)
    assert result.dry_run is True
    assert result.verified is False
    assert not backup_root.exists()
    assert len(result.files) == 2


def test_backup_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(BackupError):
        backup_directory(tmp_path / "nope", tmp_path / "backups")


def test_backup_root_inside_source_refused(save_source: Path) -> None:
    with pytest.raises(BackupError):
        backup_directory(save_source, save_source / "backups")


def test_backup_root_equal_to_source_refused(save_source: Path) -> None:
    with pytest.raises(BackupError):
        backup_directory(save_source, save_source)


def test_validate_timestamp_rejects_path_escape() -> None:
    for bad in ["", ".", "..", "../evil", "a/b", "a\\b", "has space", "semi;colon"]:
        with pytest.raises(BackupError):
            validate_timestamp(bad)
    assert validate_timestamp("20260101-120000") == "20260101-120000"
    assert validate_timestamp("manual_1") == "manual_1"


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    target.write_bytes(b"hello world")
    assert sha256_file(target) == hashlib.sha256(b"hello world").hexdigest()
