import random
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from api.store_api import get_trailer_url
from game_updates import apply_hltb_candidate, mark_hltb_no_match
from storage.database import load_hltb_candidates, save_game
from storage.image_cache import get_game_image
from ui.game_table_model import GameTableModel


class SelectAllDoubleSpinBox(QDoubleSpinBox):
    def focusInEvent(self, event):
        super().focusInEvent(event)

        QTimer.singleShot(
            0,
            self.selectAll,
        )


class LibraryTab(QWidget):
    data_changed = Signal()

    def __init__(self, games, parent=None):
        super().__init__(parent)

        self.games = games
        self.filtered_games = games
        self.selected_game = None
        self.current_game_pixmap = None
        self.header_sort_column = None
        self.header_sort_order = Qt.SortOrder.AscendingOrder

        self._create_filter_controls()
        self._create_table()
        self._create_details()

        self._create_layout()
        self._connect_signals()
        self.apply_filters()

    def _create_filter_controls(self):
        self.search_box = QLineEdit()

        self.search_box.setPlaceholderText("Search games...")

        self.status_filter = QComboBox()

        self.status_filter.addItems(
            ["All", "Backlog", "Playing", "On Hold", "Inactive", "Completed", "Dropped"]
        )

        self.type_filter = QComboBox()

        self.type_filter.addItems(
            [
                "All Types",
                "Backlog Eligible",
                "Game",
                "Unknown",
                "Software",
                "DLC",
                "Video",
                "Hardware",
            ]
        )

        self.hltb_metric_filter = QComboBox()

        self.hltb_metric_filter.addItems(
            ["Main Story", "Main + Extra", "Completionist", "All Styles"]
        )

        self.hltb_min_filter = SelectAllDoubleSpinBox()

        self.hltb_min_filter.setRange(0, 10000)
        self.hltb_min_filter.setDecimals(1)
        self.hltb_min_filter.setSingleStep(0.5)
        self.hltb_min_filter.setSpecialValueText("Min")
        self.hltb_min_filter.setSuffix(" h")

        self.hltb_max_filter = SelectAllDoubleSpinBox()

        self.hltb_max_filter.setRange(0, 10000)
        self.hltb_max_filter.setDecimals(1)
        self.hltb_max_filter.setSingleStep(0.5)
        self.hltb_max_filter.setSpecialValueText("Max")
        self.hltb_max_filter.setSuffix(" h")

        self.pick_button = QPushButton("Pick Something For Me")

    def _create_table(self):
        self.table = QTableView()
        self.game_table_model = GameTableModel(self.filtered_games, self)

        self.table.setModel(self.game_table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)

        header.sectionClicked.connect(self.sort_by_column)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

    def _create_details(self):
        self.game_image = QLabel("Select a game")

        self.game_image.setMinimumSize(0, 0)
        self.game_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.game_title = QLabel("No game selected")

        self.game_title.setWordWrap(True)
        self.game_title.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.status_label = QLabel("Status:")

        self.status_label.setStyleSheet("font-size: 10pt;")

        self.status_value = QLabel("No game selected")

        self.status_value.setStyleSheet("font-size: 10pt;")

        self.manual_status_combo = QComboBox()

        self.manual_status_combo.addItems(
            ["Automatic", "Completed", "On Hold", "Dropped"]
        )
        self.manual_status_combo.setEnabled(False)

        self.game_details = QLabel("")

        self.game_details.setWordWrap(True)
        self.game_details.setStyleSheet("font-size: 11pt;")
        self.game_details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.steam_page_button = QPushButton("Steam Page")

        self.steam_page_button.setEnabled(False)

        self.trailer_button = QPushButton("Watch Trailer")

        self.trailer_button.setEnabled(False)

        self.video_widget = QVideoWidget()

        self.video_widget.setMinimumSize(0, 0)
        self.video_widget.setVisible(False)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)

        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setAudioOutput(self.audio_output)

    def _create_layout(self):
        layout = QVBoxLayout(self)
        search_row = QHBoxLayout()

        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.pick_button)

        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("Status:"))
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(QLabel("Type:"))
        filter_row.addWidget(self.type_filter)
        filter_row.addWidget(QLabel("HLTB Metric:"))

        filter_row.addWidget(self.hltb_metric_filter)
        filter_row.addWidget(QLabel("HLTB Hours:"))

        filter_row.addWidget(self.hltb_min_filter)
        filter_row.addWidget(QLabel("to"))
        filter_row.addWidget(self.hltb_max_filter)
        filter_row.addStretch()

        self.details_panel = QWidget()

        self.details_panel.setMinimumWidth(220)

        details_layout = QVBoxLayout(self.details_panel)

        details_layout.addWidget(
            self.game_image, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        details_layout.addWidget(self.game_title)

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

        layout.addLayout(search_row)
        layout.addLayout(filter_row)
        layout.addWidget(self.splitter, 1)

    def _connect_signals(self):
        self.search_box.textChanged.connect(self.apply_filters)
        self.status_filter.currentTextChanged.connect(self.apply_filters)
        self.type_filter.currentTextChanged.connect(self.apply_filters)
        self.hltb_metric_filter.currentTextChanged.connect(self.apply_filters)

        self.hltb_min_filter.valueChanged.connect(self.hltb_min_changed)

        self.hltb_max_filter.valueChanged.connect(self.hltb_max_changed)

        self.pick_button.clicked.connect(self.pick_random_game)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.show_selected_game()
        )
        self.manual_status_combo.currentTextChanged.connect(self.change_manual_status)

        self.steam_page_button.clicked.connect(self.open_selected_steam_page)
        self.trailer_button.clicked.connect(self.open_selected_trailer)
        self.media_player.errorOccurred.connect(self.handle_video_error)
        self.splitter.splitterMoved.connect(self.update_media_sizes)

    def set_games(self, games):
        self.games = games

        self.refresh_data()

    def refresh_data(self):
        selected_app_id = (
            self.selected_game.app_id if self.selected_game is not None else None
        )

        self.apply_filters()

        if selected_app_id is None:
            return

        for row, game in enumerate(self.filtered_games):
            if game.app_id == selected_app_id:
                self.table.selectRow(row)

                return

        self.clear_game_details()

    def current_hltb_time(self, game):
        metric = self.hltb_metric_filter.currentText()

        return game.hltb_time(metric)

    def hltb_min_changed(self, min_hours):
        max_hours = self.hltb_max_filter.value()

        if min_hours > 0 and max_hours > 0 and min_hours > max_hours:
            self.hltb_max_filter.setValue(min_hours)

        self.apply_filters()

    def hltb_max_changed(self, max_hours):
        min_hours = self.hltb_min_filter.value()

        if max_hours > 0 and min_hours > 0 and max_hours < min_hours:
            self.hltb_min_filter.setValue(max_hours)

        self.apply_filters()

    def apply_filters(self):
        filtered_games = self.games

        selected_hltb_metric = self.hltb_metric_filter.currentText()

        self.game_table_model.set_hltb_metric(selected_hltb_metric)

        selected_status = self.status_filter.currentText()
        selected_type = self.type_filter.currentText()
        min_hours = self.hltb_min_filter.value()
        max_hours = self.hltb_max_filter.value()

        # 1. STATUS FILTER
        if selected_status == "Backlog":
            filtered_games = [
                game
                for game in filtered_games
                if game.effective_status() == "Backlog" and game.is_backlog_eligible()
            ]

        elif selected_status != "All":
            filtered_games = [
                game
                for game in filtered_games
                if game.effective_status() == selected_status
            ]

        # 2. STEAM TYPE FILTER
        if selected_type == "Backlog Eligible":
            filtered_games = [
                game for game in filtered_games if game.is_backlog_eligible()
            ]

        elif selected_type != "All Types":
            type_values = {
                "Game": "game",
                "Unknown": "unknown",
                "Software": "software",
                "DLC": "dlc",
                "Video": "video",
                "Hardware": "hardware",
            }

            steam_type = type_values[selected_type]

            filtered_games = [
                game for game in filtered_games if game.steam_type == steam_type
            ]

        # 3. HLTB LENGTH FILTER
        if min_hours > 0 or max_hours > 0:
            ranged_games = []

            for game in filtered_games:
                hltb_time = self.current_hltb_time(game)

                if hltb_time is None:
                    continue

                if min_hours > 0 and hltb_time < min_hours:
                    continue

                if max_hours > 0 and hltb_time > max_hours:
                    continue

                ranged_games.append(game)

            filtered_games = ranged_games

        # 4. SEARCH
        search_text = self.search_box.text().strip().lower()

        if search_text:
            filtered_games = [
                game for game in filtered_games if search_text in game.name.lower()
            ]

        # 5. SORT
        if self.header_sort_column is not None:
            filtered_games = self.sort_games_by_column(filtered_games)
        else:
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.name.lower(),
            )

        self.filtered_games = filtered_games

        self.game_table_model.set_games(filtered_games)

        # 6. PUSH RESULT INTO TABLE
        self.filtered_games = filtered_games

        self.game_table_model.set_games(filtered_games)

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
        tag_names = [tag for tag, _weight in sorted_tags[:8]]
        tags = ", ".join(tag_names) if tag_names else "Unknown"
        status_text = game.effective_status()
        last_played_timestamp = game.last_played_timestamp or 0

        if last_played_timestamp > 0:
            last_played_text = (
                datetime.fromtimestamp(last_played_timestamp, tz=timezone.utc)
                .astimezone()
                .strftime("%b %d, %Y")
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

        steam_type_text = game.steam_type.replace("_", " ").title()

        self.game_details.setText(
            f"Last played: {last_played_text}\nLast 2 weeks: {recent_activity_text}\n\nSteam Playtime: {playtime_hours:.1f} hours\nSteam Type: {steam_type_text}\nHLTB ({hltb_metric}): {hltb_text}\nAchievements: {achievement_text}\n\nGenres: {genres}\n\nTags: {tags}"
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
        except Exception as error:  # noqa: BLE001
            self.current_game_pixmap = None

            self.game_image.setPixmap(QPixmap())
            self.game_image.setText("Image unavailable")
            print(f"Image failed for {game.name}: {error}")

    def pick_random_game(self):
        eligible_games = [
            game for game in self.filtered_games if game.is_backlog_eligible()
        ]

        if not eligible_games:
            QMessageBox.information(
                self,
                "No Games",
                "No backlog-eligible games match the current filters",
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
        self.refresh_data()

        self.data_changed.emit()

    def review_hltb_matches(self):
        review_games = [
            game for game in self.games if game.hltb_match_status == "review"
        ]

        if not review_games:
            QMessageBox.information(
                self, "HLTB Review", "There are no HLTB matches waiting for review."
            )

            return

        changed = False

        for game in review_games:
            action = self._review_single_hltb_game(game)

            if action in {"accept", "no_match"}:
                changed = True

            if action == "close":
                break

        if changed:
            self.refresh_data()
            self.data_changed.emit()

    def _review_single_hltb_game(self, game):
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
                f"HLTB title: {candidate['game_name']}\n\nSimilarity: {similarity:.2f}\n\nMain Story: {format_time(candidate.get('main_story'))}\nMain + Extra: {format_time(candidate.get('main_extra'))}\nCompletionist: {format_time(candidate.get('completionist'))}\nAll Styles: {format_time(candidate.get('all_styles'))}\n\nSearch query: {candidate.get('search_query') or 'Unknown'}"
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

            apply_hltb_candidate(game, candidate)
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
        except Exception as error:  # noqa: BLE001
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

    def sort_by_column(self, column):
        if self.header_sort_column == column:
            if self.header_sort_order == Qt.SortOrder.AscendingOrder:
                self.header_sort_order = Qt.SortOrder.DescendingOrder
            else:
                self.header_sort_order = Qt.SortOrder.AscendingOrder

        else:
            self.header_sort_column = column
            self.header_sort_order = Qt.SortOrder.AscendingOrder

        header = self.table.horizontalHeader()

        header.setSortIndicatorShown(True)

        header.setSortIndicator(
            column,
            self.header_sort_order,
        )

        self.apply_filters()

    def sort_filter_changed(self):
        self.header_sort_column = None

        self.table.horizontalHeader().setSortIndicatorShown(False)

        self.apply_filters()

    def sort_games_by_column(self, games):
        column = self.header_sort_column

        reverse = self.header_sort_order == Qt.SortOrder.DescendingOrder

        if column == 0:
            return sorted(
                games,
                key=lambda game: game.name.lower(),
                reverse=reverse,
            )

        if column == 1:
            status_order = {
                "Backlog": 0,
                "Playing": 1,
                "On Hold": 2,
                "Inactive": 3,
                "Completed": 4,
                "Dropped": 5,
            }

            return sorted(
                games,
                key=lambda game: status_order.get(
                    game.effective_status(),
                    99,
                ),
                reverse=reverse,
            )

        if column == 2:
            return sorted(
                games,
                key=lambda game: game.playtime_minutes,
                reverse=reverse,
            )

        if column == 3:
            return sorted(
                games,
                key=lambda game: game.last_played_timestamp or 0,
                reverse=reverse,
            )

        if column == 4:
            return sorted(
                games,
                key=lambda game: game.playtime_2weeks_minutes or 0,
                reverse=reverse,
            )

        if column == 5:

            def hltb_key(game):
                value = self.current_hltb_time(game)

                if value is None:
                    if reverse:
                        return float("-inf")

                    return float("inf")

                return value

            return sorted(
                games,
                key=hltb_key,
                reverse=reverse,
            )

        if column == 6:

            def achievement_key(game):
                percentage = game.achievement_percent()

                if percentage is None:
                    if reverse:
                        return float("-inf")

                    return float("inf")

                return percentage

            return sorted(
                games,
                key=achievement_key,
                reverse=reverse,
            )

        if column == 7:
            type_order = {
                "game": 0,
                "unknown": 1,
                "software": 2,
                "dlc": 3,
                "video": 4,
                "hardware": 5,
            }

            return sorted(
                games,
                key=lambda game: (
                    type_order.get(
                        game.steam_type,
                        99,
                    ),
                    game.name.lower(),
                ),
                reverse=reverse,
            )

        return games
