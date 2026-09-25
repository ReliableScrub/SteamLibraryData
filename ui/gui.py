import random
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from api.store_api import get_trailer_url
from game_updates import (
    apply_achievements,
    apply_hltb,
    apply_hltb_candidate,
    apply_metadata,
    fetch_achievements,
    fetch_hltb,
    fetch_metadata,
    mark_hltb_no_match,
    update_achievements,
    update_hltb,
    update_metadata,
)
from storage.database import (
    delete_database,
    delete_games_not_in,
    get_database_steam_id,
    load_hltb_candidates,
    save_game,
    set_database_steam_id,
)
from storage.image_cache import clear_image_cache, get_game_image
from ui.game_table_model import GameTableModel
from workers import (
    BatchUpdateWorker,
    ConcurrentResultWorker,
    ResultBatchWorker,
    SteamLibraryRefreshWorker,
)

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

        self.steam_refresh_thread = None
        self.steam_refresh_worker = None

        self.batch_update_thread = None
        self.batch_update_worker = None
        self.batch_update_progress = None
        self.batch_update_finished_callback = None

        self.combined_update_active = False
        self.combined_update_total = 0
        self.combined_progress = {}
        self.combined_jobs_remaining = 0

        self.combined_hltb_thread = None
        self.combined_hltb_worker = None

        self.combined_metadata_thread = None
        self.combined_metadata_worker = None

        self.combined_achievement_thread = None
        self.combined_achievement_worker = None

        self.combined_progress_bars = {}
        self.combined_finished_callbacks = {}
        self.combined_thread_sources = {}

        self.update_cancel_requested = False
        self.close_after_updates_stop = False

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
        self.status_filter.addItems(
            ["All", "Backlog", "Playing", "On Hold", "Inactive", "Completed", "Dropped"]
        )
        self.status_filter.currentTextChanged.connect(self.apply_filters)

        self.hltb_metric_filter = QComboBox()

        self.hltb_metric_filter.addItems(
            [
                "Main Story",
                "Main + Extra",
                "Completionist",
                "All Styles",
            ]
        )

        self.hltb_metric_filter.currentTextChanged.connect(self.apply_filters)

        self.time_filter = QComboBox()
        self.time_filter.addItems(
            [
                "Any Length",
                "Under 5 Hours",
                "Under 10 Hours",
                "Under 25 Hours",
                "Under 50 Hours",
            ]
        )
        self.time_filter.currentTextChanged.connect(self.apply_filters)

        self.sort_filter = QComboBox()
        self.sort_filter.addItems(
            [
                "Name",
                "Shortest HLTB",
                "Longest HLTB",
                "Most Played",
                "Least Played",
                "Status",
                "Last Played",
            ]
        )
        self.sort_filter.currentTextChanged.connect(self.apply_filters)

        self.pick_button = QPushButton("Pick Something For Me")
        self.pick_button.clicked.connect(self.pick_random_game)

    def create_update_controls(self):
        self.library_status = QLabel()

        self.library_button = QPushButton("Refresh Steam Library")
        self.library_button.clicked.connect(self.refresh_library)

        self.library_progress = QProgressBar()
        self.library_progress.setRange(0, 0)
        self.library_progress.setTextVisible(False)
        self.library_progress.setVisible(False)

        self.hltb_status = QLabel()
        self.hltb_button = QPushButton("Update HLTB Data")
        self.hltb_button.clicked.connect(self.update_hltb_batch)
        self.hltb_progress = QProgressBar()
        self.hltb_progress.setVisible(False)
        self.hltb_progress.setFormat("%v / %m")

        self.hltb_review_button = QPushButton("Review HLTB Matches")
        self.hltb_review_button.clicked.connect(self.review_hltb_matches)
        self.hltb_review_button.setEnabled(False)

        self.metadata_status = QLabel()
        self.metadata_button = QPushButton("Update Genre / Tag Data")
        self.metadata_button.clicked.connect(self.update_metadata_batch)
        self.metadata_progress = QProgressBar()
        self.metadata_progress.setVisible(False)
        self.metadata_progress.setFormat("%v / %m")

        self.achievement_status = QLabel()
        self.achievement_button = QPushButton("Update Achievement Data")
        self.achievement_button.clicked.connect(self.update_achievement_batch)
        self.achievement_progress = QProgressBar()
        self.achievement_progress.setVisible(False)
        self.achievement_progress.setFormat("%v / %m")

        self.update_all_status = QLabel("Missing Data")
        self.update_all_button = QPushButton("Update Missing Data")
        self.update_all_button.clicked.connect(self.update_all_missing_data)

        self.cancel_updates_button = QPushButton("Cancel Updates")
        self.cancel_updates_button.clicked.connect(self.cancel_updates)
        self.cancel_updates_button.setEnabled(False)

        self.update_all_progress = QProgressBar()
        self.update_all_progress.setVisible(False)
        self.update_all_progress.setFormat("%v / %m")

    def create_game_table(self):
        self.table = QTableView()

        self.game_table_model = GameTableModel(self.filtered_games, self)
        self.table.setModel(self.game_table_model)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

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
        self.manual_status_combo.addItems(
            ["Automatic", "Completed", "On Hold", "Dropped"]
        )
        self.manual_status_combo.setEnabled(False)
        self.manual_status_combo.currentTextChanged.connect(self.change_manual_status)

        self.game_details = QLabel("")
        self.game_details.setWordWrap(True)
        self.game_details.setStyleSheet("font-size: 11pt;")
        self.game_details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

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

        filter_row.addWidget(QLabel("HLTB Metric:"))
        filter_row.addWidget(self.hltb_metric_filter)

        filter_row.addWidget(QLabel("Length:"))
        filter_row.addWidget(self.time_filter)

        filter_row.addWidget(QLabel("Sort:"))
        filter_row.addWidget(self.sort_filter)

        filter_row.addStretch()

        self.details_panel = QWidget()
        self.details_panel.setMinimumWidth(220)
        details_layout = QVBoxLayout(self.details_panel)

        details_layout.addWidget(
            self.game_image, alignment=Qt.AlignmentFlag.AlignHCenter
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
            self.video_widget, alignment=Qt.AlignmentFlag.AlignHCenter
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

        layout.addWidget(self.update_all_status, 0, 0)
        layout.addWidget(self.update_all_progress, 0, 1)

        update_all_buttons = QHBoxLayout()
        update_all_buttons.addWidget(self.update_all_button)
        update_all_buttons.addWidget(self.cancel_updates_button)
        layout.addLayout(update_all_buttons, 0, 2)

        layout.addWidget(self.library_status, 1, 0)
        layout.addWidget(self.library_progress, 1, 1)
        layout.addWidget(self.library_button, 1, 2)

        layout.addWidget(self.hltb_status, 2, 0)
        layout.addWidget(self.hltb_progress, 2, 1)

        hltb_buttons = QHBoxLayout()
        hltb_buttons.addWidget(self.hltb_button)
        hltb_buttons.addWidget(self.hltb_review_button)
        layout.addLayout(hltb_buttons, 2, 2)

        layout.addWidget(self.metadata_status, 3, 0)
        layout.addWidget(self.metadata_progress, 3, 1)
        layout.addWidget(self.metadata_button, 3, 2)

        layout.addWidget(self.achievement_status, 4, 0)
        layout.addWidget(self.achievement_progress, 4, 1)
        layout.addWidget(self.achievement_button, 4, 2)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setRowStretch(5, 1)

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

    def apply_filters(self):
        filtered_games = self.games

        selected_hltb_metric = self.hltb_metric_filter.currentText()

        self.game_table_model.set_hltb_metric(selected_hltb_metric)

        selected_status = self.status_filter.currentText()
        selected_time = self.time_filter.currentText()

        if selected_status != "All":
            filtered_games = [
                game
                for game in filtered_games
                if game.effective_status() == selected_status
            ]

        time_limits = {
            "Under 5 Hours": 5,
            "Under 10 Hours": 10,
            "Under 25 Hours": 25,
            "Under 50 Hours": 50,
        }

        if selected_time in time_limits:
            max_hours = time_limits[selected_time]

            filtered_games = [
                game
                for game in filtered_games
                if self.current_hltb_time(game) is not None
                and self.current_hltb_time(game) <= max_hours
            ]

        search_text = self.search_box.text().strip().lower()

        if search_text:
            filtered_games = [
                game for game in filtered_games if search_text in game.name.lower()
            ]

        selected_sort = self.sort_filter.currentText()

        if selected_sort == "Name":
            filtered_games = sorted(filtered_games, key=lambda game: game.name.lower())

        elif selected_sort == "Shortest HLTB":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: (
                    self.current_hltb_time(game)
                    if self.current_hltb_time(game) is not None
                    else float("inf")
                ),
            )

        elif selected_sort == "Longest HLTB":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: (
                    self.current_hltb_time(game)
                    if self.current_hltb_time(game) is not None
                    else -1
                ),
                reverse=True,
            )

        elif selected_sort == "Most Played":
            filtered_games = sorted(
                filtered_games, key=lambda game: game.playtime_minutes, reverse=True
            )

        elif selected_sort == "Least Played":
            filtered_games = sorted(
                filtered_games, key=lambda game: game.playtime_minutes
            )

        elif selected_sort == "Status":
            status_order = {
                "Backlog": 0,
                "Playing": 1,
                "On Hold": 2,
                "Inactive": 3,
                "Completed": 4,
                "Dropped": 5,
            }

            filtered_games = sorted(
                filtered_games,
                key=lambda game: (
                    status_order.get(game.effective_status(), 99),
                    game.name.lower(),
                ),
            )

        elif selected_sort == "Last Played":
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.last_played_timestamp or 0,
                reverse=True,
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
        hltb_metric = self.hltb_metric_filter.currentText()
        hltb_time = game.hltb_time(hltb_metric)

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
            last_played_text = datetime.fromtimestamp(last_played_timestamp).strftime(
                "%b %d, %Y"
            )
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
            f"HLTB ({hltb_metric}): {hltb_text}\n"
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
            QMessageBox.information(
                self, "No Games", "No games match the current filters."
            )
            return

        game = random.choice(self.filtered_games)
        hltb_time = self.current_hltb_time(game)
        hltb_metric = self.hltb_metric_filter.currentText()

        if hltb_time is None:
            time_text = "Unknown completion time"
        else:
            time_text = f"{hltb_metric}: {hltb_time:.1f} hours"

        QMessageBox.information(self, "Play This", f"{game.name}\n\n{time_text}")

    def start_result_update(
        self,
        games,
        fetcher,
        task_name,
        action_text,
        status_label,
        progress_bar,
        result_handler,
        finished_status_callback,
        thread_attr,
        worker_attr,
        concurrent=False,
    ):
        progress_bar.setRange(0, len(games))
        progress_bar.setValue(0)
        progress_bar.setVisible(True)

        thread = QThread()

        if concurrent:
            worker = ConcurrentResultWorker(
                games,
                fetcher,
                task_name,
                action_text,
                max_workers=1,
            )
        else:
            worker = ResultBatchWorker(
                games,
                fetcher,
                task_name,
                action_text,
            )

        setattr(self, thread_attr, thread)
        setattr(self, worker_attr, worker)

        self.combined_progress_bars[task_name] = progress_bar
        self.combined_finished_callbacks[task_name] = finished_status_callback
        self.combined_thread_sources[thread] = (
            task_name,
            thread_attr,
            worker_attr,
        )

        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.status_changed.connect(status_label.setText)
        worker.progress_changed.connect(self.update_combined_source_progress)
        worker.result_ready.connect(result_handler)
        worker.item_failed.connect(self.batch_update_failed)

        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)

        thread.finished.connect(self.combined_thread_finished)
        thread.finished.connect(thread.deleteLater)

        thread.start()

    def update_combined_source_progress(
        self,
        source_name,
        completed,
        total,
    ):
        progress_bar = self.combined_progress_bars.get(source_name)

        if progress_bar is not None:
            progress_bar.setRange(0, total)
            progress_bar.setValue(completed)

        self.combined_progress[source_name] = completed

        overall_completed = sum(self.combined_progress.values())

        self.update_all_progress.setValue(overall_completed)

    def start_batch_update(
        self,
        games,
        updater,
        task_name,
        action_text,
        status_label,
        progress_bar,
        finished_callback,
    ):
        if self.batch_update_thread is not None:
            return

        self.update_cancel_requested = False
        self.set_update_buttons_enabled(False)

        progress_bar.setRange(0, len(games))
        progress_bar.setValue(0)
        progress_bar.setVisible(True)

        self.batch_update_progress = progress_bar
        self.batch_update_finished_callback = finished_callback

        self.batch_update_thread = QThread()

        self.batch_update_worker = BatchUpdateWorker(
            games, updater, task_name, action_text
        )

        self.batch_update_worker.moveToThread(self.batch_update_thread)

        self.batch_update_thread.started.connect(self.batch_update_worker.run)

        self.batch_update_worker.status_changed.connect(status_label.setText)

        self.batch_update_worker.progress_changed.connect(self.update_batch_progress)

        self.batch_update_worker.item_failed.connect(self.batch_update_failed)

        self.batch_update_worker.finished.connect(self.batch_update_thread.quit)

        self.batch_update_worker.finished.connect(self.batch_update_worker.deleteLater)

        self.batch_update_thread.finished.connect(self.batch_update_thread.deleteLater)

        self.batch_update_thread.finished.connect(self.batch_update_finished)

        self.batch_update_thread.start()

    def update_batch_progress(self, completed, total):
        if self.batch_update_progress is not None:
            self.batch_update_progress.setRange(0, total)
            self.batch_update_progress.setValue(completed)

    def batch_update_failed(self, error_message):
        print(error_message)

    def batch_update_finished(self):
        if self.batch_update_progress is not None:
            self.batch_update_progress.setVisible(False)

        finished_callback = self.batch_update_finished_callback

        self.batch_update_worker = None
        self.batch_update_thread = None
        self.batch_update_progress = None
        self.batch_update_finished_callback = None

        self.apply_filters()

        if finished_callback is not None:
            finished_callback()

        if self.batch_update_thread is None and not self.combined_update_active:
            if self.update_cancel_requested:
                self.update_all_status.setText("Update cancelled.")

            self.update_cancel_requested = False
            self.set_update_buttons_enabled(True)

    def update_hltb_status(self):
        matched = sum(1 for game in self.games if game.hltb_match_status == "matched")

        review = sum(1 for game in self.games if game.hltb_match_status == "review")

        no_match = sum(1 for game in self.games if game.hltb_match_status == "no_match")

        pending = sum(1 for game in self.games if not game.hltb_checked)

        self.hltb_status.setText(
            f"HLTB: "
            f"{matched} matched | "
            f"{review} review | "
            f"{no_match} no match | "
            f"{pending} pending"
        )

        self.hltb_review_button.setEnabled(review > 0 and not self.updates_running())

    def update_hltb_batch(self):
        games = [game for game in self.games if not game.hltb_checked]

        if not games:
            QMessageBox.information(
                self, "HLTB", "All games have already been checked."
            )
            return

        batch = games[:BATCH_SIZE]

        self.start_batch_update(
            games=batch,
            updater=update_hltb,
            task_name="HLTB",
            action_text="Searching HLTB for",
            status_label=self.hltb_status,
            progress_bar=self.hltb_progress,
            finished_callback=self.update_hltb_status,
        )

    def review_hltb_matches(self):
        review_games = [
            game for game in self.games if game.hltb_match_status == "review"
        ]

        if not review_games:
            QMessageBox.information(
                self,
                "HLTB Review",
                "There are no HLTB matches waiting for review.",
            )
            return

        for game in review_games:
            action = self.review_single_hltb_game(game)

            if action == "close":
                break

        self.update_hltb_status()
        self.apply_filters()

    def update_metadata_status(self):
        checked = sum(1 for game in self.games if game.metadata_checked)
        total = len(self.games)
        self.metadata_status.setText(f"Genre / Tag Data: {checked} / {total}")

    def update_metadata_batch(self):
        games = [game for game in self.games if not game.metadata_checked]

        if not games:
            QMessageBox.information(
                self, "Metadata", "All games already have genre/tag data."
            )
            return

        batch = games[:BATCH_SIZE]

        self.start_batch_update(
            games=batch,
            updater=update_metadata,
            task_name="Metadata",
            action_text="Getting metadata for",
            status_label=self.metadata_status,
            progress_bar=self.metadata_progress,
            finished_callback=self.update_metadata_status,
        )

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
            self, "Steam ID", "Enter your SteamID64:"
        )

        if not accepted:
            return None

        steam_id = steam_id.strip()

        if not steam_id.isdigit():
            QMessageBox.warning(
                self, "Invalid Steam ID", "SteamID64 must contain only numbers."
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
                self, "Achievements", "There are no games that need achievement data."
            )
            return

        steam_id = self.get_steam_id()

        if steam_id is None:
            return

        batch = games[:BATCH_SIZE]
        steam_api_key = self.steam_api_key

        def achievement_updater(game):
            update_achievements(game, steam_id, steam_api_key)

        self.start_batch_update(
            games=batch,
            updater=achievement_updater,
            task_name="Achievements",
            action_text="Checking achievements for",
            status_label=self.achievement_status,
            progress_bar=self.achievement_progress,
            finished_callback=self.update_achievement_status,
        )

    def clear_cached_images(self):
        clear_image_cache()

        QMessageBox.information(
            self, "Image Cache", "Cached game images have been deleted."
        )

    def reset_database(self):
        result = QMessageBox.question(
            self,
            "Reset Local Database",
            "Delete all locally collected Steam, HLTB, SteamSpy, achievement, and cached image data?",
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        clear_image_cache()
        delete_database()

        QMessageBox.information(
            self,
            "Database Reset",
            "Local data has been deleted. The application will now close.",
        )

        QApplication.quit()

    def update_all_missing_data(self):
        if self.combined_update_active:
            return

        if self.batch_update_thread is not None:
            return

        if self.steam_refresh_thread is not None:
            return

        hltb_games = [game for game in self.games if not game.hltb_checked]

        metadata_games = [game for game in self.games if not game.metadata_checked]

        achievement_games = [
            game for game in self.games if not game.achievements_checked
        ]

        if not hltb_games and not metadata_games and not achievement_games:
            QMessageBox.information(
                self,
                "Missing Data",
                "All games have already been checked.",
            )
            return

        steam_id = None

        if achievement_games:
            steam_id = self.get_steam_id()

            if steam_id is None:
                return

        self.update_cancel_requested = False
        self.combined_update_active = True

        self.combined_update_total = (
            len(hltb_games) + len(metadata_games) + len(achievement_games)
        )

        self.combined_progress = {}

        if hltb_games:
            self.combined_progress["HLTB"] = 0

        if metadata_games:
            self.combined_progress["Metadata"] = 0

        if achievement_games:
            self.combined_progress["Achievements"] = 0

        self.combined_jobs_remaining = len(self.combined_progress)

        self.update_all_progress.setRange(
            0,
            self.combined_update_total,
        )
        self.update_all_progress.setValue(0)
        self.update_all_progress.setVisible(True)

        self.update_all_status.setText("Missing Data: Updating...")

        self.set_update_buttons_enabled(False)

        if hltb_games:
            self.start_result_update(
                games=hltb_games,
                fetcher=fetch_hltb,
                task_name="HLTB",
                action_text="Searching HLTB for",
                status_label=self.hltb_status,
                progress_bar=self.hltb_progress,
                result_handler=self.handle_hltb_result,
                finished_status_callback=self.update_hltb_status,
                thread_attr="combined_hltb_thread",
                worker_attr="combined_hltb_worker",
                concurrent=True,
            )

        if metadata_games:
            self.start_result_update(
                games=metadata_games,
                fetcher=fetch_metadata,
                task_name="Metadata",
                action_text="Getting metadata for",
                status_label=self.metadata_status,
                progress_bar=self.metadata_progress,
                result_handler=self.handle_metadata_result,
                finished_status_callback=self.update_metadata_status,
                thread_attr="combined_metadata_thread",
                worker_attr="combined_metadata_worker",
            )

        if achievement_games:
            steam_api_key = self.steam_api_key

            def achievement_fetcher(game):
                return fetch_achievements(
                    game,
                    steam_id,
                    steam_api_key,
                )

            self.start_result_update(
                games=achievement_games,
                fetcher=achievement_fetcher,
                task_name="Achievements",
                action_text="Checking achievements for",
                status_label=self.achievement_status,
                progress_bar=self.achievement_progress,
                result_handler=self.handle_achievement_result,
                finished_status_callback=self.update_achievement_status,
                thread_attr="combined_achievement_thread",
                worker_attr="combined_achievement_worker",
            )

    def combined_thread_finished(self):
        thread = self.sender()

        source_info = self.combined_thread_sources.pop(
            thread,
            None,
        )

        if source_info is None:
            return

        source_name, thread_attr, worker_attr = source_info

        setattr(self, worker_attr, None)
        setattr(self, thread_attr, None)

        callback = self.combined_finished_callbacks.pop(
            source_name,
            None,
        )

        if callback is not None:
            callback()

        self.combined_jobs_remaining -= 1

        print(f"{source_name} finished. {self.combined_jobs_remaining} jobs remaining.")

        if self.combined_jobs_remaining == 0:
            self.finish_combined_update()

    def finish_combined_update(self):
        was_cancelled = self.update_cancel_requested

        self.combined_update_active = False

        if not was_cancelled:
            self.update_all_progress.setValue(self.combined_update_total)

        self.update_all_progress.setVisible(False)

        self.hltb_progress.setVisible(False)
        self.metadata_progress.setVisible(False)
        self.achievement_progress.setVisible(False)

        self.apply_filters()

        self.update_hltb_status()
        self.update_metadata_status()
        self.update_achievement_status()

        remaining = sum(1 for game in self.games if not game.hltb_checked)

        remaining += sum(1 for game in self.games if not game.metadata_checked)

        remaining += sum(1 for game in self.games if not game.achievements_checked)

        if was_cancelled:
            self.update_all_status.setText(
                f"Missing Data: Cancelled ({remaining} still unchecked)"
            )
        elif remaining == 0:
            self.update_all_status.setText("Missing Data: Complete")
        else:
            self.update_all_status.setText(f"Missing Data: {remaining} still unchecked")

        self.combined_hltb_worker = None
        self.combined_hltb_thread = None

        self.combined_metadata_worker = None
        self.combined_metadata_thread = None

        self.combined_achievement_worker = None
        self.combined_achievement_thread = None

        self.combined_update_total = 0
        self.combined_progress = {}
        self.combined_jobs_remaining = 0

        self.combined_progress_bars = {}
        self.combined_finished_callbacks = {}
        self.combined_thread_sources = {}

        self.update_cancel_requested = False
        self.set_update_buttons_enabled(True)

    def refresh_library(self):
        steam_id = self.get_steam_id()

        if steam_id is None:
            return

        if self.steam_refresh_thread is not None:
            return

        self.update_cancel_requested = False
        self.set_update_buttons_enabled(False)
        self.library_status.setText("Steam Library: Refreshing...")
        self.library_progress.setVisible(True)

        self.steam_refresh_thread = QThread()

        self.steam_refresh_worker = SteamLibraryRefreshWorker(
            steam_id, self.steam_api_key
        )

        self.steam_refresh_worker.moveToThread(self.steam_refresh_thread)

        self.steam_refresh_thread.started.connect(self.steam_refresh_worker.run)

        self.steam_refresh_worker.succeeded.connect(self.finish_library_refresh)

        self.steam_refresh_worker.failed.connect(self.library_refresh_failed)

        self.steam_refresh_worker.finished.connect(self.steam_refresh_thread.quit)

        self.steam_refresh_worker.finished.connect(
            self.steam_refresh_worker.deleteLater
        )

        self.steam_refresh_thread.finished.connect(
            self.steam_refresh_thread.deleteLater
        )

        self.steam_refresh_thread.finished.connect(self.library_refresh_finished)

        self.steam_refresh_thread.start()

    def finish_library_refresh(self, steam_games):
        existing_games = {game.app_id: game for game in self.games}

        merged_games = []

        for steam_game in steam_games:
            existing_game = existing_games.get(steam_game.app_id)

            if existing_game is not None:
                existing_game.name = steam_game.name
                existing_game.playtime_minutes = steam_game.playtime_minutes
                existing_game.playtime_2weeks_minutes = (
                    steam_game.playtime_2weeks_minutes
                )
                existing_game.last_played_timestamp = steam_game.last_played_timestamp

                game = existing_game
            else:
                game = steam_game

            save_game(game)
            merged_games.append(game)

        delete_games_not_in(game.app_id for game in merged_games)

        self.games = merged_games
        self.apply_filters()

        self.update_hltb_status()
        self.update_metadata_status()
        self.update_achievement_status()

        self.library_status.setText(f"Steam Library: {len(self.games)} games")

    def library_refresh_failed(self, error_message):
        self.library_status.setText("Steam Library: Refresh failed")

        QMessageBox.warning(
            self, "Steam Library", f"Library refresh failed:\n{error_message}"
        )

    def library_refresh_finished(self):
        self.library_progress.setVisible(False)

        self.steam_refresh_worker = None
        self.steam_refresh_thread = None

        if self.update_cancel_requested:
            self.library_status.setText("Steam Library: Refresh cancelled")

        self.update_cancel_requested = False
        self.set_update_buttons_enabled(True)

    def first_run_setup(self):
        result = QMessageBox.question(
            self,
            "Steam Library",
            "Your local library is empty. Import your Steam library now?",
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
                    self, "Trailer", "No Steam trailer is available for this game."
                )
                self.trailer_button.setText("Watch Trailer")
                return

            self.video_widget.setVisible(True)
            self.media_player.setSource(QUrl(trailer_url))
            self.media_player.play()

            self.trailer_button.setText("Stop Trailer")

        except Exception as error:
            QMessageBox.warning(
                self, "Trailer", f"Could not load the trailer:\n{error}"
            )
            self.trailer_button.setText("Watch Trailer")

        finally:
            self.trailer_button.setEnabled(True)

    def handle_video_error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError:
            return

        self.stop_trailer()

        QMessageBox.warning(
            self, "Video Playback", f"The trailer could not be played:\n{error_string}"
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
            self.details_panel.contentsRect().width() - margins.left() - margins.right()
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
                Qt.TransformationMode.SmoothTransformation,
            )

            self.game_image.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "details_panel"):
            QTimer.singleShot(0, self.update_media_sizes)

    def updates_running(self):
        threads = [
            self.steam_refresh_thread,
            self.batch_update_thread,
            self.combined_hltb_thread,
            self.combined_metadata_thread,
            self.combined_achievement_thread,
        ]

        return any(thread is not None and thread.isRunning() for thread in threads)

    def cancel_updates(self):
        workers = [
            self.steam_refresh_worker,
            self.batch_update_worker,
            self.combined_hltb_worker,
            self.combined_metadata_worker,
            self.combined_achievement_worker,
        ]

        active_workers = [worker for worker in workers if worker is not None]

        if not active_workers:
            return

        self.update_cancel_requested = True
        self.cancel_updates_button.setEnabled(False)

        if self.combined_update_active:
            self.update_all_status.setText("Missing Data: Stopping...")
        elif self.steam_refresh_worker is not None:
            self.library_status.setText("Steam Library: Stopping...")
        else:
            self.update_all_status.setText("Update: Stopping...")

        for worker in active_workers:
            worker.cancel()

    def closeEvent(self, event):
        if self.updates_running():
            if not self.close_after_updates_stop:
                self.close_after_updates_stop = True
                self.cancel_updates()

            event.ignore()
            QTimer.singleShot(
                100,
                self.close,
            )
            return

        self.stop_trailer()
        event.accept()

    def set_update_buttons_enabled(self, enabled):
        self.update_all_button.setEnabled(enabled)
        self.library_button.setEnabled(enabled)
        self.hltb_button.setEnabled(enabled)
        self.metadata_button.setEnabled(enabled)
        self.achievement_button.setEnabled(enabled)

        review_available = any(
            game.hltb_match_status == "review" for game in self.games
        )

        self.hltb_review_button.setEnabled(enabled and review_available)

        self.cancel_updates_button.setEnabled(
            not enabled and not self.update_cancel_requested
        )

    def handle_hltb_result(self, game, result):
        try:
            apply_hltb(game, result)
            save_game(game)

        except Exception as error:
            print(f"Could not apply HLTB result for {game.name}: {error}")

    def handle_metadata_result(self, game, result):
        try:
            apply_metadata(game, result)
            save_game(game)

        except Exception as error:
            print(f"Could not apply metadata result for {game.name}: {error}")

    def handle_achievement_result(self, game, result):
        try:
            apply_achievements(game, result)
            save_game(game)

        except Exception as error:
            print(f"Could not apply achievement result for {game.name}: {error}")

    def current_hltb_time(self, game):
        metric = self.hltb_metric_filter.currentText()
        return game.hltb_time(metric)

    def review_single_hltb_game(self, game):
        candidates = load_hltb_candidates(game.app_id)

        if not candidates:
            return "skip"

        dialog = QDialog(self)
        dialog.setWindowTitle("Review HLTB Match")
        dialog.resize(600, 350)

        layout = QVBoxLayout(dialog)

        title_label = QLabel(f"Steam game:\n{game.name}")

        title_label.setWordWrap(True)

        layout.addWidget(title_label)

        candidate_combo = QComboBox()

        for candidate in candidates:
            similarity = candidate.get("similarity") or 0

            candidate_combo.addItem(f"{candidate['game_name']} ({similarity:.2f})")

        layout.addWidget(candidate_combo)

        details_label = QLabel()
        details_label.setWordWrap(True)

        layout.addWidget(details_label)

        open_button = QPushButton("Open HLTB Page")

        layout.addWidget(open_button)

        button_row = QHBoxLayout()

        accept_button = QPushButton("Accept Match")

        no_match_button = QPushButton("No Match")

        skip_button = QPushButton("Skip")

        close_button = QPushButton("Close Review")

        button_row.addWidget(accept_button)
        button_row.addWidget(no_match_button)
        button_row.addWidget(skip_button)
        button_row.addWidget(close_button)

        layout.addLayout(button_row)

        result = {"action": "close"}

        def selected_candidate():
            index = candidate_combo.currentIndex()

            if index < 0:
                return None

            return candidates[index]

        def format_time(value):
            if value is None:
                return "Unknown"

            return f"{value:.1f} h"

        def update_candidate_details():
            candidate = selected_candidate()

            if candidate is None:
                details_label.setText("No candidate selected.")

                open_button.setEnabled(False)
                return

            similarity = candidate.get("similarity") or 0

            details_label.setText(
                f"HLTB title: "
                f"{candidate['game_name']}\n\n"
                f"Similarity: "
                f"{similarity:.2f}\n\n"
                f"Main Story: "
                f"{format_time(candidate.get('main_story'))}\n"
                f"Main + Extra: "
                f"{format_time(candidate.get('main_extra'))}\n"
                f"Completionist: "
                f"{format_time(candidate.get('completionist'))}\n"
                f"All Styles: "
                f"{format_time(candidate.get('all_styles'))}\n\n"
                f"Search query: "
                f"{candidate.get('search_query') or 'Unknown'}"
            )

            open_button.setEnabled(bool(candidate.get("game_web_link")))

        def open_candidate_page():
            candidate = selected_candidate()

            if candidate is None:
                return

            url = candidate.get("game_web_link")

            if not url:
                return

            QDesktopServices.openUrl(QUrl(url))

        def accept_candidate():
            candidate = selected_candidate()

            if candidate is None:
                return

            apply_hltb_candidate(
                game,
                candidate,
            )

            save_game(game)

            result["action"] = "accept"

            dialog.accept()

        def mark_no_match():
            mark_hltb_no_match(game)

            save_game(game)

            result["action"] = "no_match"

            dialog.accept()

        def skip_game():
            result["action"] = "skip"
            dialog.accept()

        def close_review():
            result["action"] = "close"
            dialog.reject()

        candidate_combo.currentIndexChanged.connect(update_candidate_details)

        open_button.clicked.connect(open_candidate_page)

        accept_button.clicked.connect(accept_candidate)

        no_match_button.clicked.connect(mark_no_match)

        skip_button.clicked.connect(skip_game)

        close_button.clicked.connect(close_review)

        update_candidate_details()

        dialog.exec()

        return result["action"]


def run_gui(games, steam_api_key):
    app = QApplication(sys.argv)
    window = MainWindow(games, steam_api_key)
    window.show()
    app.exec()
