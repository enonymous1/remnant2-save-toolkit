"""PyQt6 graphical interface over the same finders and backup as the CLI.

The GUI is an optional extra (``pip install ".[gui]"``). Importing this
module requires PyQt6; importing the rest of the package does not.

Nothing here converts a save between platforms. Each screen finds one
platform's saves and can back a selected save directory up, with the
same hash verification as ``remnant2-saves backup``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from remnant2_save_toolkit.backup import BackupError, backup_directory
from remnant2_save_toolkit.core import (
    SaveLocation,
    find_all_locations,
    find_steam_locations,
    find_wgs_locations,
)

NO_CONVERSION_NOTE = (
    "This tool finds and backs up saves. It does not convert a Steam save "
    "to Xbox format, or an Xbox save to Steam format."
)
CLOSE_GAME_NOTE = (
    "Close the game before backing up a real save: a backup taken while "
    "the game is running can capture a half-written save pair."
)


def _populate_results(list_widget: QListWidget, locations: list[SaveLocation]) -> None:
    list_widget.clear()
    for location in locations:
        item = QListWidgetItem(
            f"[{location.platform}] {location.path} ({len(location.files)} files, {location.size_bytes} bytes)"
        )
        item.setData(Qt.ItemDataRole.UserRole, str(location.path))
        list_widget.addItem(item)


def _open_path(path_text: str) -> None:
    path = Path(path_text)
    if path.is_dir():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class FinderScreen(QWidget):
    """One platform's find-and-back-up screen."""

    def __init__(
        self,
        title: str,
        find_locations: Callable[[], list[SaveLocation]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._find_locations = find_locations

        layout = QVBoxLayout()
        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading_font = QFont()
        heading_font.setPointSize(14)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        layout.addWidget(heading)

        note = QLabel(NO_CONVERSION_NOTE)
        note.setWordWrap(True)
        layout.addWidget(note)

        close_game = QLabel(CLOSE_GAME_NOTE)
        close_game.setWordWrap(True)
        layout.addWidget(close_game)

        self.find_button = QPushButton("Find saves")
        self.find_button.clicked.connect(self._on_find)
        layout.addWidget(self.find_button)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(lambda item: _open_path(str(item.data(Qt.ItemDataRole.UserRole))))
        layout.addWidget(self.results)

        self.backup_button = QPushButton("Back up selected...")
        self.backup_button.clicked.connect(self._on_backup)
        layout.addWidget(self.backup_button)

        self.status_label = QLabel("No search run yet.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def _on_find(self) -> None:
        locations = self._find_locations()
        _populate_results(self.results, locations)
        if locations:
            self.status_label.setText(f"Found {len(locations)} save location(s).")
        else:
            self.status_label.setText("No save locations found.")

    def _on_backup(self) -> None:
        item = self.results.currentItem()
        if item is None:
            self.status_label.setText("Select a save location first, then back it up.")
            return
        source = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        backup_root_text = QFileDialog.getExistingDirectory(self, "Choose backup folder", str(Path.home()))
        if not backup_root_text:
            self.status_label.setText("Backup cancelled.")
            return
        try:
            result = backup_directory(source, Path(backup_root_text))
        except BackupError as exc:
            self.status_label.setText(f"Backup failed: {exc}")
            return
        self.status_label.setText(f"Backed up to {result.destination} ({len(result.files)} files, hash-verified).")


class MainWindow(QMainWindow):
    """Main window: navigation drawer plus Home / Xbox / Steam screens."""

    def __init__(
        self,
        user_profile: Path | None = None,
        steam_roots: list[Path] | None = None,
        packages_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._user_profile = user_profile
        self._steam_roots = steam_roots
        self._packages_dir = packages_dir

        self.setWindowTitle("Remnant 2 Save Toolkit")
        self.setGeometry(100, 100, 800, 600)

        splitter = QSplitter()
        self.setCentralWidget(splitter)

        self.nav_drawer = QListWidget()
        self.nav_drawer.setFixedWidth(150)
        self.nav_drawer.addItem("Home")
        self.nav_drawer.addItem("Xbox (WGS) saves")
        self.nav_drawer.addItem("Steam saves")
        self.nav_drawer.currentRowChanged.connect(self.navigate)
        splitter.addWidget(self.nav_drawer)
        splitter.setCollapsible(0, False)

        self.stacked_widget = QStackedWidget()
        splitter.addWidget(self.stacked_widget)

        self.main_screen = self._build_home_screen()
        self.stacked_widget.addWidget(self.main_screen)

        self.xbox_screen = FinderScreen(
            "Xbox (WGS) saves",
            lambda: find_wgs_locations(self._packages_dir),
        )
        self.stacked_widget.addWidget(self.xbox_screen)

        self.steam_screen = FinderScreen(
            "Steam saves",
            lambda: find_steam_locations(self._user_profile, self._steam_roots),
        )
        self.stacked_widget.addWidget(self.steam_screen)

    def _build_home_screen(self) -> QWidget:
        screen = QWidget()
        layout = QVBoxLayout()

        welcome_label = QLabel("Welcome to the Remnant 2 Save Toolkit!")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        welcome_label.setFont(font)
        layout.addWidget(welcome_label)

        note = QLabel(NO_CONVERSION_NOTE)
        note.setWordWrap(True)
        layout.addWidget(note)

        self.home_find_button = QPushButton("Find all saves")
        self.home_find_button.clicked.connect(self._on_home_find)
        layout.addWidget(self.home_find_button)

        self.home_results = QListWidget()
        self.home_results.itemDoubleClicked.connect(lambda item: _open_path(str(item.data(Qt.ItemDataRole.UserRole))))
        layout.addWidget(self.home_results)

        self.home_status_label = QLabel("No search run yet.")
        self.home_status_label.setWordWrap(True)
        layout.addWidget(self.home_status_label)

        screen.setLayout(layout)
        return screen

    def _on_home_find(self) -> None:
        locations = find_all_locations(self._user_profile, self._steam_roots, self._packages_dir)
        _populate_results(self.home_results, locations)
        if locations:
            self.home_status_label.setText(f"Found {len(locations)} save location(s).")
        else:
            self.home_status_label.setText("No save locations found.")

    def show_main_screen(self) -> None:
        self.stacked_widget.setCurrentWidget(self.main_screen)

    def show_xbox_screen(self) -> None:
        self.stacked_widget.setCurrentWidget(self.xbox_screen)

    def show_steam_screen(self) -> None:
        self.stacked_widget.setCurrentWidget(self.steam_screen)

    def navigate(self, index: int) -> None:
        if index == 0:
            self.show_main_screen()
        elif index == 1:
            self.show_xbox_screen()
        elif index == 2:
            self.show_steam_screen()


def run_gui(
    user_profile: Path | None = None,
    steam_roots: list[Path] | None = None,
    packages_dir: Path | None = None,
    argv: list[str] | None = None,
) -> int:
    """Create the application, show the main window, and run the event loop.

    ``argv`` defaults to ``sys.argv`` for the CLI, but is a parameter so
    tests and embedders can start the GUI without touching global state.
    Reuses an existing application instance instead of creating a
    second one, which Qt rejects.
    """
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    window = MainWindow(user_profile, steam_roots, packages_dir)
    window.show()
    return int(app.exec())
