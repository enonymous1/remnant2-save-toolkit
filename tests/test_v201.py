"""Regression tests for the v2.0.1 staff-review fixes."""

from __future__ import annotations

import json
import os
import shutil
import sys
import types
from pathlib import Path

import pytest

from remnant2_save_toolkit import core
from remnant2_save_toolkit.backup import (
    BackupError,
    backup_directory,
    validate_timestamp,
)
from remnant2_save_toolkit.cli import main
from remnant2_save_toolkit.core import (
    SaveFile,
    SaveLocation,
    _dedupe_by_path,
    discover_steam_roots,
    find_steam_saved_games_locations,
    find_steam_userdata_locations,
    find_wgs_containers,
    find_wgs_locations,
    parse_libraryfolders_vdf,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs privileges on Windows.")
def test_symlinked_file_is_refused_not_followed(save_source: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("NOT A SAVE - SHOULD NOT LEAK\n", encoding="utf-8")
    (save_source / "profile.sav").unlink()
    (save_source / "profile.sav").symlink_to(outside)
    with pytest.raises(BackupError, match="symlink"):
        backup_directory(save_source, tmp_path / "backups", timestamp="20260101-120000")
    assert not (tmp_path / "backups").exists()


@pytest.mark.skipif(os.name == "nt", reason="Symlink creation needs privileges on Windows.")
def test_symlinked_directory_is_refused(save_source: Path, tmp_path: Path) -> None:
    link = tmp_path / "linked-set"
    link.symlink_to(save_source, target_is_directory=True)
    with pytest.raises(BackupError, match="symlink"):
        backup_directory(link, tmp_path / "backups", timestamp="20260101-120000")


def test_copy_failure_is_backup_error_and_cleans_up(
    save_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _failing_copytree(*args: object, **kwargs: object) -> None:
        raise OSError("disk full (simulated)")

    monkeypatch.setattr(shutil, "copytree", _failing_copytree)
    backup_root = tmp_path / "backups"
    with pytest.raises(BackupError, match="Backup copy failed"):
        backup_directory(save_source, backup_root, timestamp="20260101-120000")
    assert not (backup_root / "save-set-20260101-120000").exists()


def test_manifest_failure_is_backup_error_and_cleans_up(
    save_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write_text = Path.write_text

    def _failing_write_text(self: Path, data: object, *args: object, **kwargs: object) -> int:
        if self.name == "backup_manifest.json":
            raise OSError("disk full (simulated)")
        return original_write_text(self, data, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", _failing_write_text)
    backup_root = tmp_path / "backups"
    with pytest.raises(BackupError, match="backup manifest"):
        backup_directory(save_source, backup_root, timestamp="20260101-120000")
    assert not (backup_root / "save-set-20260101-120000").exists()


def test_timestamp_length_cap() -> None:
    with pytest.raises(BackupError):
        validate_timestamp("x" * 65)
    assert validate_timestamp("x" * 64) == "x" * 64


def test_deeply_nested_vdf_is_ignored_not_a_crash() -> None:
    deep = '"libraryfolders"\n{\n' + '"a"\n{\n' * 2000 + "}\n" * 2000 + "}\n"
    assert parse_libraryfolders_vdf(deep) == {}


def test_steam_root_is_additive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "default_steam_roots", lambda: [Path("/def1"), Path("/def2")])
    roots = discover_steam_roots([Path("/custom")])
    assert roots[0] == Path("/custom")
    assert Path("/def1") in roots
    assert Path("/def2") in roots


def test_empty_steam_directories_are_not_locations(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "Saved Games" / "Remnant2" / "Steam").mkdir(parents=True)
    assert find_steam_saved_games_locations(home) == []
    (home / "Saved Games" / "Remnant2" / "Steam" / "76561198000000001").mkdir()
    assert find_steam_saved_games_locations(home) == []
    steam_root = tmp_path / "steam"
    (steam_root / "userdata" / "123" / "1282100" / "remote").mkdir(parents=True)
    assert find_steam_userdata_locations([steam_root]) == []


def test_wgs_size_agrees_between_container_and_find_views(tmp_path: Path) -> None:
    packages = tmp_path / "Packages"
    save_set = packages / "PerfectWorldEntertainment.Remnant2" / "SystemAppData" / "wgs" / "C1" / "SET1"
    _write(save_set / "BLOB1", "x" * 10)
    _write(save_set / "nested" / "deep.bin", "y" * 100)
    (container,) = find_wgs_containers(packages)
    (location,) = find_wgs_locations(packages)
    assert container.save_sets[0].size_bytes == 110
    assert location.size_bytes == 110
    assert len(location.files) == 1  # only the top-level blob is listed


def test_second_wgs_package_is_not_dropped(tmp_path: Path) -> None:
    packages = tmp_path / "Packages"
    for package in ("PerfectWorldEntertainment.Remnant2_A", "PerfectWorldEntertainment.Remnant2_B"):
        _write(
            packages / package / "SystemAppData" / "wgs" / "C1" / "SET1" / "BLOB1",
            "fake\n",
        )
    assert len(find_wgs_containers(packages)) == 2
    assert len(find_wgs_locations(packages)) == 2


def test_dedupe_by_path_ignores_file_list_differences() -> None:
    path = Path("/saves/set")
    first = SaveLocation(platform="steam", path=path, files=(SaveFile(path=path / "a.sav", size_bytes=1),))
    second = SaveLocation(platform="steam", path=path, files=())
    assert _dedupe_by_path([first, second]) == [first]


def test_registry_path_via_fake_winreg(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeKey:
        def __enter__(self) -> _FakeKey:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=0,
        OpenKey=lambda *args: _FakeKey(),
        QueryValueEx=lambda key, name: (r"C:\Steam", 1),
    )
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert core._registry_steam_path() == Path(r"C:\Steam")


def test_backup_json_carries_schema_version(
    save_source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["backup", str(save_source), "--backup-root", str(tmp_path / "backups"), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["verified"] is True


def test_backup_cli_failure_returns_2_not_traceback(
    save_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(shutil, "copytree", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    code = main(["backup", str(save_source), "--backup-root", str(tmp_path / "backups")])
    assert code == 2
    assert "Error:" in capsys.readouterr().err
