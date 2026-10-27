"""Tests for Steam / WGS discovery and the libraryfolders.vdf parser."""

from __future__ import annotations

from pathlib import Path

from remnant2_save_toolkit.core import (
    find_all_locations,
    find_steam_locations,
    find_steam_saved_games_locations,
    find_steam_userdata_locations,
    find_wgs_containers,
    find_wgs_directory,
    find_wgs_locations,
    inspect_directory,
    library_paths_from_vdf,
    list_wgs_containers,
    parse_libraryfolders_vdf,
)


def test_saved_games_finds_numeric_subdirectory(steam_home: Path) -> None:
    locations = find_steam_saved_games_locations(steam_home)
    assert len(locations) == 1
    location = locations[0]
    assert location.platform == "steam"
    assert location.path.name == "76561198000000001"
    assert "Saved Games" in location.path.parts
    assert sorted(item.path.name for item in location.files) == ["profile.sav", "save_0.sav"]
    assert location.size_bytes > 0


def test_saved_games_path_is_not_doubled(steam_home: Path) -> None:
    """Regression: v1's GUI joined 'Saved Games' onto a path that already had it."""
    (location,) = find_steam_locations(user_profile=steam_home, steam_roots=[])
    text = location.path.as_posix()
    assert text.count("Saved Games") == 1
    assert text.endswith("Saved Games/Remnant2/Steam/76561198000000001")


def test_saved_games_missing_returns_empty(tmp_path: Path) -> None:
    assert find_steam_saved_games_locations(tmp_path / "empty-home") == []


def test_saved_games_without_numeric_child_uses_folder_itself(tmp_path: Path) -> None:
    steam_dir = tmp_path / "Saved Games" / "Remnant2" / "Steam"
    (steam_dir / "profile.sav").parent.mkdir(parents=True)
    (steam_dir / "profile.sav").write_text("fake\n", encoding="utf-8")
    (location,) = find_steam_saved_games_locations(tmp_path)
    assert location.path == steam_dir
    assert [item.path.name for item in location.files] == ["profile.sav"]


def test_userdata_remote_saved_games(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    nested = steam_root / "userdata" / "12345" / "1282100" / "remote" / "SAVED" / "SaveGames"
    nested.mkdir(parents=True)
    (nested / "profile.sav").write_text("fake\n", encoding="utf-8")
    (location,) = find_steam_userdata_locations([steam_root])
    assert location.path == nested


def test_userdata_remote_without_nested_folder(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    remote = steam_root / "userdata" / "12345" / "1282100" / "remote"
    remote.mkdir(parents=True)
    (remote / "profile.sav").write_text("fake\n", encoding="utf-8")
    (location,) = find_steam_userdata_locations([steam_root])
    assert location.path == remote


def test_userdata_ignores_non_numeric_user_dirs(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    remote = steam_root / "userdata" / "not-a-user" / "1282100" / "remote"
    remote.mkdir(parents=True)
    (remote / "profile.sav").write_text("fake\n", encoding="utf-8")
    assert find_steam_userdata_locations([steam_root]) == []


def test_userdata_missing_returns_empty(tmp_path: Path) -> None:
    assert find_steam_userdata_locations([tmp_path / "no-steam-here"]) == []


def test_wgs_directory_found_case_insensitively(wgs_packages: Path) -> None:
    found = find_wgs_directory(wgs_packages)
    assert found is not None
    assert found.name == "wgs"
    assert "SystemAppData" in found.parts


def test_wgs_directory_missing_returns_none(tmp_path: Path) -> None:
    assert find_wgs_directory(tmp_path / "Packages") is None


def test_wgs_directory_prefers_package_with_containers(tmp_path: Path) -> None:
    """A matching package holding only a ``t`` folder must not shadow the real one."""
    packages = tmp_path / "Packages"
    empty_wgs = packages / "PerfectWorldEntertainment.OtherGame_1" / "SystemAppData" / "wgs" / "t"
    empty_wgs.mkdir(parents=True)
    real_wgs = packages / "PerfectWorldEntertainment.Remnant2_2" / "SystemAppData" / "wgs" / "CONTAINER1"
    real_wgs.mkdir(parents=True)
    found = find_wgs_directory(packages)
    assert found is not None
    assert found.parent.parent.name.startswith("PerfectWorldEntertainment.Remnant2")


def test_wgs_containers_exclude_t_folder(wgs_packages: Path) -> None:
    found = find_wgs_directory(wgs_packages)
    assert found is not None
    containers = list_wgs_containers(found)
    assert [item.name for item in containers] == ["000901F4A1B2C3D4"]


def test_wgs_save_sets_have_no_inferred_label(wgs_packages: Path) -> None:
    (container,) = find_wgs_containers(wgs_packages)
    (save_set,) = container.save_sets
    assert not hasattr(save_set, "label")
    assert sorted(item.path.name for item in save_set.files) == ["A1B2C3D4E5F6", "F6E5D4C3B2A1"]
    assert save_set.size_bytes > 0


def test_wgs_locations_share_save_location_shape(wgs_packages: Path) -> None:
    (location,) = find_wgs_locations(wgs_packages)
    assert location.platform == "xbox-wgs"
    assert len(location.files) == 2


def test_find_all_combines_steam_then_wgs(steam_home: Path, wgs_packages: Path) -> None:
    locations = find_all_locations(user_profile=steam_home, steam_roots=[], packages_dir=wgs_packages)
    assert [item.platform for item in locations] == ["steam", "xbox-wgs"]


def test_inspect_directory(tmp_path: Path) -> None:
    target = tmp_path / "saves"
    target.mkdir()
    (target / "profile.sav").write_text("fake\n", encoding="utf-8")
    location = inspect_directory(target)
    assert location.platform == "unknown"
    assert [item.path.name for item in location.files] == ["profile.sav"]


def test_parse_libraryfolders_vdf_new_format() -> None:
    text = """"libraryfolders"
{
    "0"
    {
        "path"        "C:\\Program Files (x86)\\Steam"
        "label"        ""
    }
    "1"
    {
        "path"        "D:\\Games\\SteamLibrary"
    }
}
"""
    parsed = parse_libraryfolders_vdf(text)
    assert isinstance(parsed, dict)
    assert parsed["0"]["path"] == r"C:\Program Files (x86)\Steam"  # type: ignore[index]
    assert parsed["1"]["path"] == r"D:\Games\SteamLibrary"  # type: ignore[index]


def test_parse_libraryfolders_vdf_old_format() -> None:
    text = """"libraryfolders"
{
    "0"        "C:\\Program Files (x86)\\Steam"
    "1"        "D:\\Games\\SteamLibrary"
}
"""
    parsed = parse_libraryfolders_vdf(text)
    assert parsed["0"] == r"C:\Program Files (x86)\Steam"
    assert parsed["1"] == r"D:\Games\SteamLibrary"


def test_parse_libraryfolders_vdf_malformed_returns_empty() -> None:
    assert parse_libraryfolders_vdf("this is not vdf {") == {}
    assert parse_libraryfolders_vdf("") == {}
    assert parse_libraryfolders_vdf('"something-else"\n{\n}') == {}


def test_library_paths_from_vdf(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    vdf_dir = steam_root / "steamapps"
    vdf_dir.mkdir(parents=True)
    (vdf_dir / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"D:\\Games"\n\t}\n}\n',
        encoding="utf-8",
    )
    assert library_paths_from_vdf(steam_root) == [Path(r"D:\Games")]


def test_library_paths_from_vdf_missing_file(tmp_path: Path) -> None:
    assert library_paths_from_vdf(tmp_path / "Steam") == []
