import random
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter,QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget
)

from backlog import unplayed_games, started_games
from game_updates import update_achievements, update_hltb, update_metadata
from storage.database import get_database_steam_id, save_game, set_database_steam_id, delete_database, delete_games_not_in
from storage.image_cache import get_game_image, clear_image_cache
from api.steam_api import get_owned_games

BATCH_SIZE = 5


class MainWindow(QMainWindow):
    def __init__(self, games, steam_api_key):
        super().__init__()

        self.games = games
        self.filtered_games = games
        self.steam_api_key = steam_api_key
        self.steam_id = None

        self.setWindowTitle("Steam Backlog")
        self.resize(1100, 700)

        self.create_filter_controls()
        self.create_update_controls()
        self.create_game_table()
        self.create_game_details()
        self.create_tabs()

        self.update_hltb_status()
        self.update_metadata_status()
        self.update_achievement_status()
        self.apply_filters()

        if not self.games:
            QTimer.singleShot(0, self.first_run_setup)

    def create_filter_controls(self):
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search games...")
        self.search_box.textChanged.connect(self.apply_filters)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Unplayed", "Started"])
        self.status_filter.currentTextChanged.connect(self.apply_filters)

        self.time_filter = QComboBox()
        self.time_filter.addItems([
            "Any Length",
            "Under 5 Hours",
            "Under 10 Hours",
            "Under 25 Hours",
            "Under 50 Hours"
        ])
        self.time_filter.currentTextChanged.connect(self.apply_filters)

        self.sort_filter = QComboBox()
        self.sort_filter.addItems([
            "Name",
            "Shortest HLTB",
            "Longest HLTB",
            "Most Played",
            "Least Played"
        ])
        self.sort_filter.currentTextChanged.connect(self.apply_filters)

        self.pick_button = QPushButton("Pick Something For Me")
        self.pick_button.clicked.connect(self.pick_random_game)

    def create_update_controls(self):
        self.library_status = QLabel()
        self.library_button = QPushButton("Refresh Steam Library")
        self.library_button.clicked.connect(self.refresh_library)

        self.hltb_status = QLabel()
        self.hltb_button = QPushButton("Update HLTB Data")
        self.hltb_button.clicked.connect(self.update_hltb_batch)

        self.metadata_status = QLabel()
        self.metadata_button = QPushButton("Update Genre / Tag Data")
        self.metadata_button.clicked.connect(self.update_metadata_batch)

        self.achievement_status = QLabel()
        self.achievement_button = QPushButton("Update Achievement Data")
        self.achievement_button.clicked.connect(self.update_achievement_batch)

    def create_game_table(self):
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Game",
            "Steam Playtime",
            "HLTB Time",
            "Achievements"
        ])

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.show_selected_game)

        self.table.setColumnWidth(0, 350)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 100)
        self.table.horizontalHeader().setStretchLastSection(True)

    def create_game_details(self):
        self.game_image = QLabel("Select a game")
        self.game_image.setFixedSize(360, 170)
        self.game_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.game_title = QLabel("No game selected")
        self.game_title.setWordWrap(True)
        self.game_title.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.game_details = QLabel("")
        self.game_details.setWordWrap(True)
        self.game_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def create_tabs(self):
        self.tabs = QTabWidget()

        self.library_tab = QWidget()
        self.updates_tab = QWidget()
        self.settings_tab = QWidget()

        self.create_library_layout()
        self.create_updates_layout()
        self.create_settings_layout()

        self.tabs.addTab(self.library_tab, "Library")
        self.tabs.addTab(self.updates_tab, "Data Updates")
        self.tabs.addTab(self.settings_tab, "Settings")

        self.setCentralWidget(self.tabs)


    def create_library_layout(self):
        layout = QVBoxLayout(self.library_tab)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.pick_button)

        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("Status:"))
        filter_row.addWidget(self.status_filter)

        filter_row.addWidget(QLabel("Length:"))
        filter_row.addWidget(self.time_filter)

        filter_row.addWidget(QLabel("Sort:"))
        filter_row.addWidget(self.sort_filter)

        filter_row.addStretch()

        details_panel = QWidget()
        details_layout = QVBoxLayout(details_panel)

        details_layout.addWidget(
            self.game_image,
            alignment=Qt.AlignmentFlag.AlignHCenter
        )

        details_layout.addWidget(self.game_title)
        details_layout.addWidget(self.game_details)
        details_layout.addStretch()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(details_panel)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([700, 350])

        layout.addLayout(search_row)
        layout.addLayout(filter_row)
        layout.addWidget(splitter, 1)

    def create_updates_layout(self):
        layout = QGridLayout(self.updates_tab)

        layout.addWidget(self.library_status, 0, 0)
        layout.addWidget(self.library_button, 0, 1)

        layout.addWidget(self.hltb_status, 1, 0)
        layout.addWidget(self.hltb_button, 1, 1)

        layout.addWidget(self.metadata_status, 2, 0)
        layout.addWidget(self.metadata_button, 2, 1)

        layout.addWidget(self.achievement_status, 3, 0)
        layout.addWidget(self.achievement_button, 3, 1)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(4, 1)

    def create_settings_layout(self):
        layout = QVBoxLayout(self.settings_tab)

        steam_id = get_database_steam_id()

        if steam_id is None:
            account_text = "Steam account: Not set"
        else:
            account_text = f"Steam account: {steam_id}"

        self.account_label = QLabel(account_text)

        self.clear_images_button = QPushButton("Clear Image Cache")
        self.clear_images_button.clicked.connect(self.clear_cached_images)

        self.reset_database_button = QPushButton("Reset Local Database")
        self.reset_database_button.clicked.connect(self.reset_database)

        layout.addWidget(self.account_label)
        layout.addWidget(self.clear_images_button)
        layout.addWidget(self.reset_database_button)
        layout.addStretch()

    def set_controls_enabled(self, enabled):
        self.search_box.setEnabled(enabled)
        self.status_filter.setEnabled(enabled)
        self.time_filter.setEnabled(enabled)
        self.sort_filter.setEnabled(enabled)
        self.pick_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

        self.hltb_button.setEnabled(enabled)
        self.metadata_button.setEnabled(enabled)
        self.achievement_button.setEnabled(enabled)

        self.tabs.tabBar().setEnabled(enabled)

    def apply_filters(self):
        filtered_games = self.games

        selected_status = self.status_filter.currentText()

        if selected_status == "Unplayed":
            filtered_games = unplayed_games(filtered_games)
        elif selected_status == "Started":
            filtered_games = started_games(filtered_games)

        selected_time = self.time_filter.currentText()

        time_limits = {
            "Under 5 Hours": 5,
            "Under 10 Hours": 10,
            "Under 25 Hours": 25,
            "Under 50 Hours": 50
        }

        if selected_time in time_limits:
            max_hours = time_limits[selected_time]
            filtered_games = [game for game in filtered_games if game.preferred_hltb_time() is not None and game.preferred_hltb_time() <= max_hours]

        search_text = self.search_box.text().strip().lower()

        if search_text:
            filtered_games = [game for game in filtered_games if search_text in game.name.lower()]

        selected_sort = self.sort_filter.currentText()

        if selected_sort == "Name":
            filtered_games = sorted(filtered_games, key=lambda game: game.name.lower())

        elif selected_sort == "Shortest HLTB":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.preferred_hltb_time() if game.preferred_hltb_time() is not None else float("inf")
            )

        elif selected_sort == "Longest HLTB":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.preferred_hltb_time() if game.preferred_hltb_time() is not None else -1,
                reverse=True
            )

        elif selected_sort == "Most Played":
            filtered_games = sorted(filtered_games, key=lambda game: game.playtime_minutes, reverse=True)

        elif selected_sort == "Least Played":
            filtered_games = sorted(filtered_games, key=lambda game: game.playtime_minutes)

        self.filtered_games = filtered_games
        self.load_games(filtered_games)

    def load_games(self, games):
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(games))

        for row, game in enumerate(games):
            playtime_hours = game.playtime_minutes / 60
            hltb_time = game.preferred_hltb_time()

            if hltb_time is None:
                hltb_text = "Unknown"
            else:
                hltb_text = f"{hltb_time:.1f} h"

            if game.achievement_total is None or game.achievements_unlocked is None:
                achievement_text = "Unknown"
            elif game.achievement_total == 0:
                achievement_text = "None"
            else:
                achievement_text = f"{game.achievements_unlocked}/{game.achievement_total}"

            self.table.setItem(row, 0, QTableWidgetItem(game.name))
            self.table.setItem(row, 1, QTableWidgetItem(f"{playtime_hours:.1f} h"))
            self.table.setItem(row, 2, QTableWidgetItem(hltb_text))
            self.table.setItem(row, 3, QTableWidgetItem(achievement_text))

        self.table.setUpdatesEnabled(True)

    def show_selected_game(self):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.filtered_games):
            return

        game = self.filtered_games[row]

        self.game_title.setText(game.name)

        playtime_hours = game.playtime_minutes / 60
        hltb_time = game.preferred_hltb_time()

        if hltb_time is None:
            hltb_text = "Unknown"
        else:
            hltb_text = f"{hltb_time:.1f} hours"

        if game.achievement_total is None or game.achievements_unlocked is None:
            achievement_text = "Unknown"
        elif game.achievement_total == 0:
            achievement_text = "None"
        else:
            achievement_text = f"{game.achievements_unlocked}/{game.achievement_total}"

        genres = ", ".join(game.genres) if game.genres else "Unknown"

        sorted_tags = sorted(game.tags.items(), key=lambda item: item[1], reverse=True)
        tag_names = [tag for tag, weight in sorted_tags[:8]]
        tags = ", ".join(tag_names) if tag_names else "Unknown"

        self.game_details.setText(
            f"Steam Playtime: {playtime_hours:.1f} hours\n"
            f"HLTB: {hltb_text}\n"
            f"Achievements: {achievement_text}\n\n"
            f"Genres: {genres}\n\n"
            f"Tags: {tags}"
        )

        try:
            image_path = get_game_image(game.app_id)
            pixmap = QPixmap(str(image_path))

            if pixmap.isNull():
                raise ValueError("Image could not be loaded.")

            pixmap = pixmap.scaled(
                self.game_image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            self.game_image.setText("")
            self.game_image.setPixmap(pixmap)

        except Exception as error:
            self.game_image.setPixmap(QPixmap())
            self.game_image.setText("Image unavailable")
            print(f"Image failed for {game.name}: {error}")

    def pick_random_game(self):
        if not self.filtered_games:
            QMessageBox.information(self, "No Games", "No games match the current filters.")
            return

        game = random.choice(self.filtered_games)
        hltb_time = game.preferred_hltb_time()

        if hltb_time is None:
            time_text = "Unknown completion time"
        else:
            time_text = f"{hltb_time:.1f} hours"

        QMessageBox.information(self, "Play This", f"{game.name}\n\n{time_text}")

    def run_update_batch(self, games, updater, show_status, error_name):
        batch = games[:BATCH_SIZE]

        self.set_controls_enabled(False)
        QApplication.processEvents()

        try:
            for game in batch:
                show_status(game)
                QApplication.processEvents()

                try:
                    updater(game)
                    save_game(game)
                except Exception as error:
                    print(f"{error_name} failed for {game.name}: {error}")

            self.apply_filters()

        finally:
            QApplication.processEvents()
            self.set_controls_enabled(True)

    def update_hltb_status(self):
        checked = sum(1 for game in self.games if game.hltb_checked)
        total = len(self.games)
        self.hltb_status.setText(f"HLTB: {checked} / {total} checked")

    def update_hltb_batch(self):
        games = [game for game in self.games if not game.hltb_checked]

        if not games:
            QMessageBox.information(self, "HLTB", "All games have already been checked.")
            return

        self.run_update_batch(
            games,
            update_hltb,
            lambda game: self.hltb_status.setText(f"Searching HLTB for {game.name}..."),
            "HLTB"
        )

        self.update_hltb_status()

    def update_metadata_status(self):
        checked = sum(1 for game in self.games if game.metadata_checked)
        total = len(self.games)
        self.metadata_status.setText(f"Genre / Tag Data: {checked} / {total}")

    def update_metadata_batch(self):
        games = [game for game in self.games if not game.metadata_checked]

        if not games:
            QMessageBox.information(self, "Metadata", "All games already have genre/tag data.")
            return

        self.run_update_batch(
            games,
            update_metadata,
            lambda game: self.metadata_status.setText(f"Getting metadata for {game.name}..."),
            "Metadata"
        )

        self.update_metadata_status()

    def update_achievement_status(self):
        checked = sum(1 for game in self.games if game.achievements_checked)
        total = len(self.games)
        self.achievement_status.setText(f"Achievements: {checked} / {total} checked")

    def get_steam_id(self):
        if self.steam_id is not None:
            return self.steam_id

        saved_steam_id = get_database_steam_id()

        if saved_steam_id is not None:
            self.steam_id = saved_steam_id
            return self.steam_id

        steam_id, accepted = QInputDialog.getText(
            self,
            "Steam ID",
            "Enter your SteamID64:"
        )

        if not accepted:
            return None

        steam_id = steam_id.strip()

        if not steam_id.isdigit():
            QMessageBox.warning(
                self,
                "Invalid Steam ID",
                "SteamID64 must contain only numbers."
            )
            return None

        try:
            set_database_steam_id(steam_id)
        except ValueError as error:
            QMessageBox.warning(self, "Steam Account", str(error))
            return None

        self.steam_id = steam_id
        self.account_label.setText(f"Steam account: {steam_id}")
        return self.steam_id

    def update_achievement_batch(self):
        games = [game for game in self.games if not game.achievements_checked]

        if not games:
            QMessageBox.information(
                self,
                "Achievements",
                "There are no games that need achievement data."
            )
            return

        steam_id = self.get_steam_id()

        if steam_id is None:
            return

        self.run_update_batch(
            games,
            lambda game: update_achievements(game, steam_id, self.steam_api_key),
            lambda game: self.achievement_status.setText(
                f"Checking achievements for {game.name}..."
            ),
            "Achievements"
        )

        self.update_achievement_status()

    def clear_cached_images(self):
        clear_image_cache()

        QMessageBox.information(
            self,
            "Image Cache",
            "Cached game images have been deleted."
        )

    def reset_database(self):
        result = QMessageBox.question(
            self,
            "Reset Local Database",
            "Delete all locally collected Steam, HLTB, SteamSpy, achievement, and cached image data?"
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        clear_image_cache()
        delete_database()

        QMessageBox.information(
            self,
            "Database Reset",
            "Local data has been deleted. The application will now close."
        )

        QApplication.quit()

    def refresh_library(self):
        steam_id = self.get_steam_id()

        if steam_id is None:
            return

        try:
            steam_games = get_owned_games(steam_id, self.steam_api_key)

            existing_games = {
                game.app_id: game
                for game in self.games
            }

            merged_games = []

            for steam_game in steam_games:
                existing_game = existing_games.get(steam_game.app_id)

                if existing_game is not None:
                    existing_game.name = steam_game.name
                    existing_game.playtime_minutes = steam_game.playtime_minutes

                    game = existing_game
                else:
                    game = steam_game

                save_game(game)
                merged_games.append(game)

            delete_games_not_in(
                game.app_id
                for game in merged_games
            )

            self.games = merged_games
            self.apply_filters()

            self.update_hltb_status()
            self.update_metadata_status()
            self.update_achievement_status()

            self.library_status.setText(
                f"Steam Library: {len(self.games)} games"
            )

        except Exception as error:
            QMessageBox.warning(
                self,
                "Steam Library",
                f"Library refresh failed:\n{error}"
            )
            
    def first_run_setup(self):
        result = QMessageBox.question(
            self,
            "Steam Library",
            "Your local library is empty. Import your Steam library now?"
        )

        if result == QMessageBox.StandardButton.Yes:
            self.refresh_library()

def run_gui(games, steam_api_key):
    app = QApplication(sys.argv)
    window = MainWindow(games, steam_api_key)
    window.show()
    app.exec()