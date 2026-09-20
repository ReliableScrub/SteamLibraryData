import random
import sys

from PySide6.QtWidgets import (QApplication, QComboBox, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget
)

from backlog import unplayed_games, started_games
from game_updates import update_achievements, update_hltb, update_metadata
from storage.cache import save_games


class MainWindow(QMainWindow):
    def __init__(self, games, steam_api_key):
        super().__init__()

        self.games = games
        self.filtered_games = games
        self.steam_api_key = steam_api_key
        self.steam_id = None

        self.setWindowTitle("Steam Backlog")
        self.resize(900, 600)

        self.create_filter_controls()
        self.create_update_controls()
        self.create_game_table()
        self.create_layout()

        self.update_hltb_status()
        self.update_metadata_status()
        self.update_achievement_status()
        self.apply_filters()

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

    def create_layout(self):
        layout = QVBoxLayout()

        layout.addWidget(self.search_box)
        layout.addWidget(self.status_filter)
        layout.addWidget(self.time_filter)
        layout.addWidget(self.sort_filter)

        layout.addWidget(self.hltb_status)
        layout.addWidget(self.hltb_button)

        layout.addWidget(self.metadata_status)
        layout.addWidget(self.metadata_button)

        layout.addWidget(self.achievement_status)
        layout.addWidget(self.achievement_button)

        layout.addWidget(self.pick_button)
        layout.addWidget(self.table)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def set_controls_enabled(self, enabled):
        self.search_box.setEnabled(enabled)
        self.status_filter.setEnabled(enabled)
        self.time_filter.setEnabled(enabled)
        self.sort_filter.setEnabled(enabled)
        self.pick_button.setEnabled(enabled)
        self.hltb_button.setEnabled(enabled)
        self.metadata_button.setEnabled(enabled)
        self.achievement_button.setEnabled(enabled)

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
        batch = games[:5]

        self.set_controls_enabled(False)
        QApplication.processEvents()

        try:
            for game in batch:
                show_status(game)
                QApplication.processEvents()

                try:
                    updater(game)
                except Exception as error:
                    print(f"{error_name} failed for {game.name}: {error}")

            save_games(self.games)
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

        steam_id, accepted = QInputDialog.getText(self, "Steam ID", "Enter your SteamID64:")

        if not accepted:
            return None

        steam_id = steam_id.strip()

        if not steam_id:
            return None

        self.steam_id = steam_id
        return self.steam_id

    def update_achievement_batch(self):
        steam_id = self.get_steam_id()

        if steam_id is None:
            return

        games = [game for game in self.games if not game.achievements_checked]

        if not games:
            QMessageBox.information(self, "Achievements", "All games have already been checked.")
            return

        self.run_update_batch(
            games,
            lambda game: update_achievements(game, steam_id, self.steam_api_key),
            lambda game: self.achievement_status.setText(f"Checking achievements for {game.name}..."),
            "Achievements"
        )

        self.update_achievement_status()


def run_gui(games, steam_api_key):
    app = QApplication(sys.argv)
    window = MainWindow(games, steam_api_key)
    window.show()
    app.exec()