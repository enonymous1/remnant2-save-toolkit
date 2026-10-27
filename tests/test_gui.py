"""GUI tests, run offscreen and only when PyQt6 is installed."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError as _exc:  # PyQt6 missing, or its system libraries (e.g. libEGL) are absent.
    pytest.skip(f"PyQt6 cannot be imported in this environment: {_exc}", allow_module_level=True)

from remnant2_save_toolkit.gui import NO_CONVERSION_NOTE, MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    return QApplication([])


@pytest.fixture()
def window(app: QApplication, steam_home: Path, wgs_packages: Path) -> MainWindow:
    return MainWindow(user_profile=steam_home, steam_roots=[], packages_dir=wgs_packages)


def test_window_has_three_nav_items_and_status_labels(window: MainWindow) -> None:
    assert window.nav_drawer.count() == 3
    assert window.home_status_label.text() == "No search run yet."
    assert window.xbox_to_steam_screen.status_label.text() == "No search run yet."
    assert window.steam_to_xbox_screen.status_label.text() == "No search run yet."


def test_xbox_screen_finds_wgs_saves(window: MainWindow) -> None:
    window.xbox_to_steam_screen.find_button.click()
    assert window.xbox_to_steam_screen.results.count() == 1
    assert "Found 1 save location(s)." in window.xbox_to_steam_screen.status_label.text()


def test_steam_screen_finds_steam_saves(window: MainWindow) -> None:
    window.steam_to_xbox_screen.find_button.click()
    assert window.steam_to_xbox_screen.results.count() == 1
    assert "76561198000000001" in window.steam_to_xbox_screen.results.item(0).text()


def test_home_finds_both_platforms(window: MainWindow) -> None:
    window.home_find_button.click()
    assert window.home_results.count() == 2
    assert "Found 2 save location(s)." in window.home_status_label.text()


def test_navigate_switches_screens(window: MainWindow) -> None:
    window.navigate(1)
    assert window.stacked_widget.currentWidget() is window.xbox_to_steam_screen
    window.navigate(2)
    assert window.stacked_widget.currentWidget() is window.steam_to_xbox_screen
    window.navigate(0)
    assert window.stacked_widget.currentWidget() is window.main_screen


def test_backup_without_selection_asks_for_selection(window: MainWindow) -> None:
    window.steam_to_xbox_screen.backup_button.click()
    assert "Select a save location first" in window.steam_to_xbox_screen.status_label.text()


def test_backup_selected_creates_verified_backup(
    app: QApplication,
    window: MainWindow,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PyQt6.QtWidgets import QFileDialog

    backup_root = tmp_path / "backups"
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *args, **kwargs: str(backup_root)),
    )
    screen = window.steam_to_xbox_screen
    screen.find_button.click()
    screen.results.setCurrentRow(0)
    screen.backup_button.click()
    assert "hash-verified" in screen.status_label.text()
    destinations = list(backup_root.iterdir())
    assert len(destinations) == 1
    assert (destinations[0] / "backup_manifest.json").is_file()


def test_no_conversion_note_is_visible(window: MainWindow) -> None:
    from PyQt6.QtWidgets import QLabel

    for screen in (window.xbox_to_steam_screen, window.steam_to_xbox_screen):
        texts = [label.text() for label in screen.findChildren(QLabel)]
        assert any(NO_CONVERSION_NOTE in text for text in texts)
