"""Tests for the ``remnant2-saves`` CLI."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from remnant2_save_toolkit.cli import main


def test_find_json_on_fake_trees(steam_home: Path, wgs_packages: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "find",
            "--user-profile",
            str(steam_home),
            "--packages-dir",
            str(wgs_packages),
            "--json",
        ]
    )
    assert code == 0
    locations = json.loads(capsys.readouterr().out)
    assert [item["platform"] for item in locations] == ["steam", "xbox-wgs"]
    assert locations[0]["path"].endswith("76561198000000001")
    assert len(locations[0]["files"]) == 2


def test_find_text_when_nothing_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "find",
            "--user-profile",
            str(tmp_path / "empty"),
            "--packages-dir",
            str(tmp_path / "Packages"),
        ]
    )
    assert code == 0
    assert "No save locations found." in capsys.readouterr().out


def test_inspect_json(save_source: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(save_source), "--json"]) == 0
    location = json.loads(capsys.readouterr().out)
    assert location["platform"] == "unknown"
    assert len(location["files"]) == 1  # only direct children are listed


def test_inspect_missing_directory_returns_2(tmp_path: Path) -> None:
    assert main(["inspect", str(tmp_path / "nope")]) == 2


def test_backup_cli_end_to_end(save_source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    backup_root = tmp_path / "backups"
    code = main(
        [
            "backup",
            str(save_source),
            "--backup-root",
            str(backup_root),
            "--timestamp",
            "20260101-120000",
        ]
    )
    assert code == 0
    assert "hash-verified" in capsys.readouterr().out
    destination = backup_root / "save-set-20260101-120000"
    assert (destination / "backup_manifest.json").is_file()
    assert (destination / "nested" / "save_0.sav").is_file()


def test_backup_cli_dry_run(save_source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    backup_root = tmp_path / "backups"
    code = main(["backup", str(save_source), "--backup-root", str(backup_root), "--dry-run"])
    assert code == 0
    assert "Would back up" in capsys.readouterr().out
    assert not backup_root.exists()


def test_backup_cli_missing_source_returns_2(tmp_path: Path) -> None:
    code = main(["backup", str(tmp_path / "nope"), "--backup-root", str(tmp_path / "backups")])
    assert code == 2


@pytest.mark.skipif(
    importlib.util.find_spec("PyQt6") is not None,
    reason="PyQt6 is installed, so the missing-GUI path cannot be exercised here.",
)
def test_gui_command_without_pyqt6_reports_install_hint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["gui"]) == 2
    assert "PyQt6" in capsys.readouterr().err
