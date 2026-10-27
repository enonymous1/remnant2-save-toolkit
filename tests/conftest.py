"""Shared fake Steam / WGS trees for the test suite.

Every file here is fictional demo data. Nothing is a real Remnant 2 save.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def steam_home(tmp_path: Path) -> Path:
    """A fake user profile holding one Steam save set."""
    home = tmp_path / "home"
    _write(
        home / "Saved Games" / "Remnant2" / "Steam" / "76561198000000001" / "profile.sav",
        "FAKE STEAM PROFILE SAVE - NOT A REAL REMNANT 2 SAVE\n",
    )
    _write(
        home / "Saved Games" / "Remnant2" / "Steam" / "76561198000000001" / "save_0.sav",
        "FAKE STEAM GAME SAVE - NOT A REAL REMNANT 2 SAVE\n",
    )
    return home


@pytest.fixture()
def wgs_packages(tmp_path: Path) -> Path:
    """A fake ``Packages`` tree holding one WGS container with one save set."""
    packages = tmp_path / "Packages"
    save_set = (
        packages
        / "PerfectWorldEntertainment.Remnant2_8wekyb3d8bbwe"
        / "SystemAppData"
        / "wgs"
        / "000901F4A1B2C3D4"
        / "11111111-2222-3333-4444-555555555555"
    )
    _write(save_set / "A1B2C3D4E5F6", "FAKE WGS SAVE BLOB - NOT A REAL REMNANT 2 SAVE\n")
    _write(save_set / "F6E5D4C3B2A1", "FAKE WGS SAVE BLOB - NOT A REAL REMNANT 2 SAVE\n")
    _write(
        packages / "PerfectWorldEntertainment.Remnant2_8wekyb3d8bbwe" / "SystemAppData" / "wgs" / "t" / "index.dat",
        "fake index\n",
    )
    return packages


@pytest.fixture()
def save_source(tmp_path: Path) -> Path:
    """A small nested directory used as a backup source."""
    source = tmp_path / "save-set"
    _write(source / "profile.sav", "fake profile\n")
    _write(source / "nested" / "save_0.sav", "fake game save\n")
    return source
