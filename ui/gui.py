import random
import sys

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSplitter, QTabWidget, QVBoxLayout, QWidget, QTableView, QHeaderView
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from ui.game_table_model import GameTableModel

from game_updates import update_achievements, update_hltb, update_metadata
from storage.database import get_database_steam_id, save_game, set_database_steam_id, delete_database, delete_games_not_in
from storage.image_cache import get_game_image, clear_image_cache
from api.steam_api import get_owned_games
from api.store_api import get_trailer_url

BATCH_SIZE = 5


class MainWindow(QMainWindow):
    def __init__(self, games, steam_api_key):
        super().__init__()

        self.games = games
        self.filtered_games = games
        self.steam_api_key = steam_api_key
        self.steam_id = None
        self.selected_game = None
        self.current_game_pixmap = None

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
        self.status_filter.addItems([
            "All",
            "Backlog",
            "Playing",
            "On Hold",
            "Inactive",
            "Completed",
            "Dropped"
        ])
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
            "Least Played",
            "Status",
            "Last Played"
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
        self.table = QTableView()

        self.game_table_model = GameTableModel(self.filtered_games, self)
        self.table.setModel(self.game_table_model)

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.show_selected_game()
        )

        header = self.table.horizontalHeader()

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

    def create_game_details(self):
        self.game_image = QLabel("Select a game")
        self.game_image.setMinimumSize(0, 0)
        self.game_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.game_title = QLabel("No game selected")
        self.game_title.setWordWrap(True)
        self.game_title.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.status_value = QLabel("No game selected")
        self.status_value.setStyleSheet("font-size: 10pt;")

        self.manual_status_combo = QComboBox()
        self.manual_status_combo.addItems([
            "Automatic",
            "Completed",
            "On Hold",
            "Dropped"
        ])
        self.manual_status_combo.setEnabled(False)
        self.manual_status_combo.currentTextChanged.connect(self.change_manual_status)

        self.game_details = QLabel("")
        self.game_details.setWordWrap(True)
        self.game_details.setStyleSheet("font-size: 11pt;")
        self.game_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.steam_page_button = QPushButton("Steam Page")
        self.steam_page_button.setEnabled(False)
        self.steam_page_button.clicked.connect(self.open_selected_steam_page)

        self.trailer_button = QPushButton("Watch Trailer")
        self.trailer_button.setEnabled(False)
        self.trailer_button.clicked.connect(self.open_selected_trailer)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(0, 0)
        self.video_widget.setVisible(False)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)

        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setAudioOutput(self.audio_output)

        self.media_player.errorOccurred.connect(self.handle_video_error)

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

        self.details_panel = QWidget()
        self.details_panel.setMinimumWidth(220)
        details_layout = QVBoxLayout(self.details_panel)

        details_layout.addWidget(
            self.game_image,
            alignment=Qt.AlignmentFlag.AlignHCenter
        )

        details_layout.addWidget(self.game_title)

        self.status_label = QLabel("Status:")
        self.status_label.setStyleSheet("font-size: 10pt;")

        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.status_value)
        status_row.addSpacing(8)
        status_row.addWidget(self.manual_status_combo)
        status_row.addStretch()

        details_layout.addLayout(status_row)
        details_layout.addWidget(self.game_details)

        details_layout.addStretch()

        details_layout.addWidget(
            self.video_widget,
            alignment=Qt.AlignmentFlag.AlignHCenter
        )

        action_row = QHBoxLayout()
        action_row.addWidget(self.steam_page_button)
        action_row.addWidget(self.trailer_button)

        details_layout.addLayout(action_row)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.details_panel)

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([700, 350])

        self.splitter.splitterMoved.connect(self.update_media_sizes)

        layout.addLayout(search_row)
        layout.addLayout(filter_row)
        layout.addWidget(self.splitter, 1)

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

        if selected_status != "All":
            filtered_games = [
                game for game in filtered_games
                if game.effective_status() == selected_status
            ]

        selected_time = self.time_filter.currentText()

        time_limits = {
            "Under 5 Hours": 5,
            "Under 10 Hours": 10,
            "Under 25 Hours": 25,
            "Under 50 Hours": 50
        }

        if selected_time in time_limits:
            max_hours = time_limits[selected_time]
            filtered_games = [
                game for game in filtered_games
                if game.preferred_hltb_time() is not None
                and game.preferred_hltb_time() <= max_hours
            ]

        search_text = self.search_box.text().strip().lower()

        if search_text:
            filtered_games = [
                game for game in filtered_games
                if search_text in game.name.lower()
            ]

        selected_sort = self.sort_filter.currentText()

        if selected_sort == "Name":
            filtered_games = sorted(filtered_games, key=lambda game: game.name.lower())

        elif selected_sort == "Shortest HLTB":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.preferred_hltb_time()
                if game.preferred_hltb_time() is not None
                else float("inf")
            )

        elif selected_sort == "Longest HLTB":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.preferred_hltb_time()
                if game.preferred_hltb_time() is not None
                else -1,
                reverse=True
            )

        elif selected_sort == "Most Played":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.playtime_minutes,
                reverse=True
            )

        elif selected_sort == "Least Played":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.playtime_minutes
            )

        elif selected_sort == "Status":
            status_order = {
                "Backlog": 0,
                "Playing": 1,
                "On Hold": 2,
                "Inactive": 3,
                "Completed": 4,
                "Dropped": 5
            }

            filtered_games = sorted(
                filtered_games,
                key=lambda game: (
                    status_order.get(game.effective_status(), 99),
                    game.name.lower()
                )
            )

        elif selected_sort == "Last Played":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.last_played_timestamp or 0,
                reverse=True
            )

        self.filtered_games = filtered_games
        self.load_games(filtered_games)

    def load_games(self, games):
        self.game_table_model.set_games(games)

    def show_selected_game(self):
        row = self.table.currentIndex().row()

        if row < 0:
            return

        game = self.game_table_model.game_at(row)

        if game is None:
            return

        self.stop_trailer()

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

        status_text = game.effective_status()

        last_played_timestamp = game.last_played_timestamp or 0

        if last_played_timestamp > 0:
            last_played_text = datetime.fromtimestamp(last_played_timestamp).strftime("%b %d, %Y")
        else:
            last_played_text = "Never"

        recent_minutes = game.playtime_2weeks_minutes or 0

        if recent_minutes == 0:
            recent_activity_text = "No recorded playtime"
        elif recent_minutes >= 60:
            recent_activity_text = f"{recent_minutes / 60:.1f} hours"
        else:
            recent_activity_text = f"{recent_minutes} minutes"

        self.selected_game = game

        self.manual_status_combo.blockSignals(True)
        self.manual_status_combo.setStyleSheet("font-size: 10pt;")

        if game.manual_status is None:
            self.manual_status_combo.setCurrentText("Automatic")
        else:
            self.manual_status_combo.setCurrentText(game.manual_status)

        self.manual_status_combo.setEnabled(True)
        self.manual_status_combo.blockSignals(False)

        self.status_value.setFixedWidth(75)
        self.status_value.setText(status_text)

        self.game_details.setText(
            f"Last played: {last_played_text}\n"
            f"Last 2 weeks: {recent_activity_text}\n\n"
            f"Steam Playtime: {playtime_hours:.1f} hours\n"
            f"HLTB: {hltb_text}\n"
            f"Achievements: {achievement_text}\n\n"
            f"Genres: {genres}\n\n"
            f"Tags: {tags}"
)
        self.steam_page_button.setEnabled(True)
        self.trailer_button.setEnabled(True)

        try:
            image_path = get_game_image(game.app_id)
            pixmap = QPixmap(str(image_path))

            if pixmap.isNull():
                raise ValueError("Image could not be loaded.")

            self.current_game_pixmap = pixmap
            self.game_image.setText("")

            self.update_media_sizes()

        except Exception as error:
            self.current_game_pixmap = None
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
                    existing_game.playtime_2weeks_minutes = steam_game.playtime_2weeks_minutes
                    existing_game.last_played_timestamp = steam_game.last_played_timestamp

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

    def change_manual_status(self, selected_status):
        if self.selected_game is None:
            return

        game = self.selected_game

        if selected_status == "Automatic":
            game.manual_status = None
        else:
            game.manual_status = selected_status

        save_game(game)

        self.status_value.setText(game.effective_status())

        selected_app_id = game.app_id

        self.apply_filters()

        for row, filtered_game in enumerate(self.filtered_games):
            if filtered_game.app_id == selected_app_id:
                self.table.selectRow(row)
                return

        self.clear_game_details()

    def clear_game_details(self):
        self.selected_game = None
        
        self.stop_trailer()

        self.game_title.setText("No game selected")
        self.status_value.setText("No game selected")
        self.game_details.setText("")

        self.game_image.setPixmap(QPixmap())
        self.game_image.setText("Select a game")

        self.manual_status_combo.blockSignals(True)
        self.manual_status_combo.setCurrentText("Automatic")
        self.manual_status_combo.setEnabled(False)
        self.manual_status_combo.blockSignals(False)

        self.steam_page_button.setEnabled(False)
        self.trailer_button.setEnabled(False)

        self.current_game_pixmap = None

    def open_selected_steam_page(self):
        if self.selected_game is None:
            return

        url = QUrl(f"https://store.steampowered.com/app/{self.selected_game.app_id}/")
        QDesktopServices.openUrl(url)

    def open_selected_trailer(self):
        if self.selected_game is None:
            return

        if self.video_widget.isVisible():
            self.stop_trailer()
            return

        self.trailer_button.setEnabled(False)
        self.trailer_button.setText("Loading...")

        try:
            trailer_url = get_trailer_url(self.selected_game.app_id)

            if trailer_url is None:
                QMessageBox.information(
                    self,
                    "Trailer",
                    "No Steam trailer is available for this game."
                )
                self.trailer_button.setText("Watch Trailer")
                return

            self.video_widget.setVisible(True)
            self.media_player.setSource(QUrl(trailer_url))
            self.media_player.play()

            self.trailer_button.setText("Stop Trailer")

        except Exception as error:
            QMessageBox.warning(
                self,
                "Trailer",
                f"Could not load the trailer:\n{error}"
            )
            self.trailer_button.setText("Watch Trailer")

        finally:
            self.trailer_button.setEnabled(True)
    
    def handle_video_error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError:
            return

        self.stop_trailer()

        QMessageBox.warning(
            self,
            "Video Playback",
            f"The trailer could not be played:\n{error_string}"
        )

    def stop_trailer(self):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.video_widget.setVisible(False)
        self.trailer_button.setText("Watch Trailer")

    def update_media_sizes(self):
        if not hasattr(self, "details_panel"):
            return

        layout = self.details_panel.layout()
        margins = layout.contentsMargins()

        available_width = (
            self.details_panel.contentsRect().width()
            - margins.left()
            - margins.right()
        )

        media_width = min(max(available_width, 1), 650)

        image_height = int(media_width * 215 / 460)
        video_height = int(media_width * 9 / 16)

        self.game_image.setFixedSize(media_width, image_height)
        self.video_widget.setFixedSize(media_width, video_height)

        if self.current_game_pixmap is not None:
            scaled_pixmap = self.current_game_pixmap.scaled(
                self.game_image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            self.game_image.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "details_panel"):
            QTimer.singleShot(0, self.update_media_sizes)

def run_gui(games, steam_api_key):
    app = QApplication(sys.argv)
    window = MainWindow(games, steam_api_key)
    window.show()
    app.exec()