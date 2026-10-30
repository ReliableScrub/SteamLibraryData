import html
import json
from datetime import UTC, datetime

import requests
from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRunnable,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from recommendations.baseline import PUBLIC_RECEPTION_MIN_REVIEWS
from recommendations.persistence import (
    load_recommendation_state,
    load_saved_recommendations,
)
from recommendations.similar import SimilarGameIndex
from storage.image_cache import get_cached_image_path, get_game_image
from ui.genre_tag_filter import GenreTagFilterWidget
from ui.semantic_widgets import BadgeLabel, SectionHeading, StatTile
from ui.store_description_loader import StoreDescriptionWorker
from ui.trailer_player import TrailerPlayer
from workers import RecommendationBuildWorker

FOR_YOU_LIMIT = 10
SIMILAR_SEARCH_LIMIT = 250
SIMILAR_RESULT_LIMIT = 50

CARD_IMAGE_WIDTH = 400
CARD_IMAGE_HEIGHT = 187


class ImageWorkerSignals(QObject):
    loaded = Signal(int, object)


class ImageWorker(QRunnable):
    def __init__(self, app_id):
        super().__init__()

        self.app_id = app_id
        self.signals = ImageWorkerSignals()

    def run(self):
        image_path = None

        try:
            image_path = str(get_game_image(self.app_id))
        except (requests.RequestException, OSError, ValueError):
            image_path = None

        self.signals.loaded.emit(
            self.app_id,
            image_path,
        )


class RecommendationsTab(QWidget):
    build_busy_changed = Signal(bool)

    def __init__(self, games, parent=None):
        super().__init__(parent)

        self.games = list(games)
        self.games_by_id = {game.app_id: game for game in self.games}

        self.recommendation_records = []
        self.recommendations_by_id = {}

        self.for_you_records = []
        self.current_for_you_index = -1
        self._for_you_animation = None
        self._for_you_effect = None

        self.similar_index = None
        self.similar_reference_app_id = None
        self.similar_all_scores = []
        self.similar_scores = []
        self.similar_scores_by_id = {}

        self.thread_pool = QThreadPool.globalInstance()

        self.image_targets = {}
        self.image_requests_in_flight = set()
        self.description_requests_in_flight = set()

        self.recommendation_state = None
        self.recommendation_thread = None
        self.recommendation_worker = None
        self._update_busy = False
        self._inputs_dirty = False
        self._dirty_during_build = False
        self._automatic_build = False
        self._auto_build_blocked = False

        self._create_controls()
        self._create_layout()
        self._connect_signals()
        self._update_media_sizes()
        self._update_responsive_typography()

        self.genre_tag_filter.set_available_from_games(self.games)

        self._populate_reference_games()
        self.refresh()
        QTimer.singleShot(0, self._update_media_sizes)

    def _create_controls(self):
        self.type_filter = QComboBox()

        self.type_filter.addItems(
            [
                "All Types",
                "Game",
                "Unknown (Game)",
                "Software",
                "Unknown (Software)",
                "Unknown",
                "DLC",
                "Video",
                "Hardware",
            ]
        )

        self.genre_tag_filter = GenreTagFilterWidget(self)

        self.hltb_metric_filter = QComboBox()

        self.hltb_metric_filter.addItems(
            [
                "Main Story",
                "Main + Extra",
                "Completionist",
                "All Styles",
            ]
        )

        self.hltb_min_filter = QDoubleSpinBox()
        self.hltb_min_filter.setRange(0, 10000)
        self.hltb_min_filter.setDecimals(1)
        self.hltb_min_filter.setSingleStep(0.5)
        self.hltb_min_filter.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        self.hltb_min_filter.setSpecialValueText("Min")
        self.hltb_min_filter.setSuffix(" h")

        self.hltb_max_filter = QDoubleSpinBox()
        self.hltb_max_filter.setRange(0, 10000)
        self.hltb_max_filter.setDecimals(1)
        self.hltb_max_filter.setSingleStep(0.5)
        self.hltb_max_filter.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        self.hltb_max_filter.setSpecialValueText("Max")
        self.hltb_max_filter.setSuffix(" h")

        self.clear_filters_button = QPushButton("Clear Filters")

        self.help_faq_button = QPushButton("Help / FAQ")
        self.help_faq_button.setToolTip(
            "Open setup help and answers for common SteamLibraryData issues."
        )

        self.mode_tabs = QTabWidget()

        self.for_you_page = QWidget()
        self.similar_page = QWidget()

        self.mode_tabs.addTab(
            self.for_you_page,
            "For You",
        )

        self.mode_tabs.addTab(
            self.similar_page,
            "Similar to a Game",
        )

        self.saved_status_label = QLabel("No saved recommendations.")
        self.saved_status_label.setWordWrap(True)

        self.rebuild_button = QPushButton("Build Recommendations")

        self.rebuild_progress = QProgressBar()
        self.rebuild_progress.setRange(0, 0)
        self.rebuild_progress.setTextVisible(False)
        self.rebuild_progress.setVisible(False)

        self.for_you_image = QLabel("No recommendation selected")
        self.for_you_image.setFixedSize(CARD_IMAGE_WIDTH, CARD_IMAGE_HEIGHT)
        self.for_you_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.for_you_image.setProperty("image_path", None)

        self.for_you_hltb = QLabel(self._empty_hltb_text())
        self.for_you_hltb.setWordWrap(True)

        self.for_you_trailer_player = TrailerPlayer(self)

        self.for_you_steam_button = QPushButton("Steam Page")
        self.for_you_steam_button.setEnabled(False)

        self.for_you_previous_button = QPushButton("Previous")
        self.for_you_previous_button.setEnabled(False)

        self.for_you_position_label = QLabel("0 of 0")
        self.for_you_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.for_you_next_button = QPushButton("Next")
        self.for_you_next_button.setEnabled(False)

        self.for_you_title = QLabel("No recommendation selected")
        self.for_you_title.setWordWrap(True)
        self.for_you_title.setStyleSheet("font-size: 17pt; font-weight: bold;")

        self.for_you_summary = QLabel("")
        self.for_you_summary.setVisible(False)

        self.for_you_match_badge = BadgeLabel("TOP PICK", tone="accent")
        self.for_you_score_badge = BadgeLabel("- MATCH", tone="accent")
        self.for_you_status_badge = BadgeLabel("", tone="neutral")
        self.for_you_type_badge = BadgeLabel("", tone="neutral")
        self.for_you_reception_badge = BadgeLabel("", tone="neutral")

        self.for_you_about_heading = SectionHeading("ABOUT")
        self.for_you_description = QLabel("")
        self.for_you_description.setWordWrap(True)
        self.for_you_description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.for_you_glance_heading = SectionHeading("AT A GLANCE")
        self.for_you_stats = {
            "playtime": StatTile("Steam Playtime"),
            "main": StatTile("Main Story"),
            "main_extra": StatTile("Main + Extra"),
            "completionist": StatTile("Completionist"),
            "achievements": StatTile("Achievements"),
            "last_played": StatTile("Last Played"),
        }

        self.for_you_details = QTextBrowser()
        self._style_details_browser(self.for_you_details)

        self.reference_combo = QComboBox()
        self.reference_combo.setEditable(True)
        self.reference_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.reference_combo.setMinimumWidth(350)

        reference_completer = self.reference_combo.completer()

        if reference_completer is not None:
            reference_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            reference_completer.setFilterMode(Qt.MatchFlag.MatchContains)
            reference_completer.setCompletionMode(
                QCompleter.CompletionMode.PopupCompletion
            )

        self.find_similar_button = QPushButton("Find Similar Backlog Games")

        self.similar_status_label = QLabel("Choose any owned game with genre/tag data.")
        self.similar_status_label.setWordWrap(True)

        self.similar_result_combo = QComboBox()
        self.similar_result_combo.setEditable(True)
        self.similar_result_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.similar_result_combo.setEnabled(False)

        result_completer = self.similar_result_combo.completer()

        if result_completer is not None:
            result_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            result_completer.setFilterMode(Qt.MatchFlag.MatchContains)
            result_completer.setCompletionMode(
                QCompleter.CompletionMode.PopupCompletion
            )

        self.similar_image = QLabel("Choose a reference game")
        self.similar_image.setFixedSize(CARD_IMAGE_WIDTH, CARD_IMAGE_HEIGHT)
        self.similar_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.similar_image.setProperty("image_path", None)

        self.similar_hltb = QLabel(self._empty_hltb_text())
        self.similar_hltb.setWordWrap(True)

        self.similar_trailer_player = TrailerPlayer(self)

        self.similar_steam_button = QPushButton("Steam Page")
        self.similar_steam_button.setEnabled(False)

        self.similar_title = QLabel("No similar game selected")
        self.similar_title.setWordWrap(True)
        self.similar_title.setStyleSheet("font-size: 17pt; font-weight: bold;")

        self.similar_summary = QLabel("")
        self.similar_summary.setVisible(False)

        self.similar_match_badge = BadgeLabel("SIMILARITY", tone="accent")
        self.similar_score_badge = BadgeLabel("- MATCH", tone="accent")
        self.similar_status_badge = BadgeLabel("", tone="neutral")
        self.similar_type_badge = BadgeLabel("", tone="neutral")
        self.similar_reception_badge = BadgeLabel("", tone="neutral")

        self.similar_context_label = QLabel("")
        self.similar_context_label.setProperty("context", "muted")
        self.similar_context_label.setWordWrap(True)

        self.similar_about_heading = SectionHeading("ABOUT")
        self.similar_description = QLabel("")
        self.similar_description.setWordWrap(True)
        self.similar_description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.similar_glance_heading = SectionHeading("AT A GLANCE")
        self.similar_stats = {
            "playtime": StatTile("Steam Playtime"),
            "main": StatTile("Main Story"),
            "main_extra": StatTile("Main + Extra"),
            "completionist": StatTile("Completionist"),
            "achievements": StatTile("Achievements"),
            "last_played": StatTile("Last Played"),
        }

        self.similar_details = QTextBrowser()
        self._style_details_browser(self.similar_details)

    @staticmethod
    def _style_media_panel(panel):
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setObjectName("recommendationMediaPanel")
        panel.setProperty("card", True)

    @staticmethod
    def _style_details_browser(browser):
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        font = browser.font()
        font.setPointSize(11)
        browser.setFont(font)
        RecommendationsTab._refresh_details_browser_style(browser)

    @staticmethod
    def _refresh_details_browser_style(browser):
        accent = browser.palette().color(QPalette.ColorRole.Highlight).name()
        muted = browser.palette().color(QPalette.ColorRole.PlaceholderText).name()

        browser.document().setDefaultStyleSheet(
            f"h3 {{ color: {accent}; margin-top: 14px; margin-bottom: 5px; }}"
            "p { margin-top: 3px; margin-bottom: 10px; }"
            f".muted {{ color: {muted}; }}"
        )

    @staticmethod
    def _friendly_score(score):
        try:
            value = float(score)
        except (TypeError, ValueError):
            return "Unknown"

        if 0.0 <= value <= 1.0:
            return f"{value * 100:.0f}%"

        return f"{value:.3f}"

    @staticmethod
    def _recommendation_match_label(record):
        if record.get("match_tier") == "top_pick":
            return "Top Pick"

        return "Recommended"

    @staticmethod
    def _public_reception_text(game):
        positive = game.steamspy_positive
        negative = game.steamspy_negative

        if positive is None or negative is None:
            return "Not fetched"

        total = positive + negative

        if total == 0:
            return "No reviews"

        percent = positive / total * 100
        text = f"{percent:.0f}% positive ({total:,} reviews)"

        if total < PUBLIC_RECEPTION_MIN_REVIEWS:
            text += " - Too few reviews to affect recommendations"

        return text

    @staticmethod
    def _similarity_match_label(_score):
        return "Similarity"

    def _create_layout(self):
        root_layout = QVBoxLayout(self)

        root_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("<h2>Recommendations</h2>"))
        title_row.addStretch()
        title_row.addWidget(self.help_faq_button)
        root_layout.addLayout(title_row)

        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("Type:"))
        filter_row.addWidget(self.type_filter)
        filter_row.addWidget(self.genre_tag_filter)
        filter_row.addWidget(QLabel("HLTB Metric:"))
        filter_row.addWidget(self.hltb_metric_filter)
        filter_row.addWidget(QLabel("HLTB Hours:"))
        filter_row.addWidget(self.hltb_min_filter)
        filter_row.addWidget(QLabel("to"))
        filter_row.addWidget(self.hltb_max_filter)
        filter_row.addWidget(self.clear_filters_button)
        filter_row.addStretch()

        root_layout.addLayout(filter_row)

        root_layout.addWidget(
            self.mode_tabs,
            1,
        )

        self._create_for_you_layout()
        self._create_similar_layout()

    def _create_for_you_layout(self):
        layout = QVBoxLayout(self.for_you_page)

        status_row = QHBoxLayout()

        status_row.addWidget(
            self.saved_status_label,
            1,
        )

        status_row.addWidget(self.rebuild_button)

        layout.addLayout(status_row)
        layout.addWidget(self.rebuild_progress)

        help_label = QLabel(
            "Browse up to ten personalized picks. "
            "Filters narrow the saved recommendation pool "
            "without rebuilding the recommendation model."
        )
        help_label.setWordWrap(True)

        layout.addWidget(help_label)

        self.for_you_left_panel = QScrollArea()
        self._style_media_panel(self.for_you_left_panel)
        self.for_you_left_panel.setWidgetResizable(True)
        self.for_you_left_panel.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.for_you_left_panel.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.for_you_left_panel.setMinimumWidth(500)
        self.for_you_left_panel.setMaximumWidth(860)

        self.for_you_left_content = QWidget()

        left_layout = QVBoxLayout(self.for_you_left_content)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        self.for_you_hltb_title = QLabel("<b>HowLongToBeat</b>")

        left_layout.addStretch(1)
        left_layout.addWidget(
            self.for_you_image,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        left_layout.addSpacing(8)
        left_layout.addWidget(self.for_you_trailer_player)

        steam_row = QHBoxLayout()
        steam_row.addWidget(self.for_you_steam_button)
        steam_row.addStretch()
        left_layout.addLayout(steam_row)
        left_layout.addStretch(1)

        navigation_row = QHBoxLayout()
        navigation_row.addWidget(self.for_you_previous_button)
        navigation_row.addWidget(
            self.for_you_position_label,
            1,
        )
        navigation_row.addWidget(self.for_you_next_button)
        left_layout.addLayout(navigation_row)

        self.for_you_left_panel.setWidget(self.for_you_left_content)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(self.for_you_title)

        primary_badges = QHBoxLayout()
        primary_badges.addWidget(self.for_you_match_badge)
        primary_badges.addWidget(self.for_you_score_badge)
        primary_badges.addStretch()
        right_layout.addLayout(primary_badges)

        secondary_badges = QHBoxLayout()
        secondary_badges.addWidget(self.for_you_status_badge)
        secondary_badges.addWidget(self.for_you_type_badge)
        secondary_badges.addWidget(self.for_you_reception_badge)
        secondary_badges.addStretch()
        right_layout.addLayout(secondary_badges)

        right_layout.addWidget(self.for_you_about_heading)
        right_layout.addWidget(self.for_you_description)
        right_layout.addWidget(self.for_you_glance_heading)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(8)
        stat_order = [
            "playtime",
            "main",
            "main_extra",
            "completionist",
            "achievements",
            "last_played",
        ]

        for index, stat_name in enumerate(stat_order):
            stats_grid.addWidget(
                self.for_you_stats[stat_name],
                index // 3,
                index % 3,
            )

        right_layout.addLayout(stats_grid)
        right_layout.addWidget(
            self.for_you_details,
            1,
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(self.for_you_left_panel)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 7)

        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        splitter.setSizes(
            [
                760,
                840,
            ]
        )

        self.for_you_splitter = splitter

        layout.addWidget(
            splitter,
            1,
        )

    def _create_similar_layout(self):
        layout = QVBoxLayout(self.similar_page)

        reference_row = QHBoxLayout()

        reference_row.addWidget(QLabel("Reference game:"))
        reference_row.addWidget(
            self.reference_combo,
            1,
        )
        reference_row.addWidget(self.find_similar_button)

        layout.addLayout(reference_row)

        result_row = QHBoxLayout()

        result_row.addWidget(QLabel("Similar result:"))
        result_row.addWidget(
            self.similar_result_combo,
            1,
        )

        layout.addLayout(result_row)
        layout.addWidget(self.similar_status_label)

        self.similar_left_panel = QScrollArea()
        self._style_media_panel(self.similar_left_panel)
        self.similar_left_panel.setWidgetResizable(True)
        self.similar_left_panel.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.similar_left_panel.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.similar_left_panel.setMinimumWidth(500)
        self.similar_left_panel.setMaximumWidth(860)

        self.similar_left_content = QWidget()

        left_layout = QVBoxLayout(self.similar_left_content)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        self.similar_hltb_title = QLabel("<b>HowLongToBeat</b>")

        left_layout.addStretch(1)
        left_layout.addWidget(
            self.similar_image,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        left_layout.addSpacing(8)
        left_layout.addWidget(self.similar_trailer_player)

        steam_row = QHBoxLayout()
        steam_row.addWidget(self.similar_steam_button)
        steam_row.addStretch()
        left_layout.addLayout(steam_row)
        left_layout.addStretch(1)

        self.similar_left_panel.setWidget(self.similar_left_content)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(self.similar_title)

        primary_badges = QHBoxLayout()
        primary_badges.addWidget(self.similar_match_badge)
        primary_badges.addWidget(self.similar_score_badge)
        primary_badges.addStretch()
        right_layout.addLayout(primary_badges)

        secondary_badges = QHBoxLayout()
        secondary_badges.addWidget(self.similar_status_badge)
        secondary_badges.addWidget(self.similar_type_badge)
        secondary_badges.addWidget(self.similar_reception_badge)
        secondary_badges.addStretch()
        right_layout.addLayout(secondary_badges)

        right_layout.addWidget(self.similar_context_label)
        right_layout.addWidget(self.similar_about_heading)
        right_layout.addWidget(self.similar_description)
        right_layout.addWidget(self.similar_glance_heading)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(8)
        stat_order = [
            "playtime",
            "main",
            "main_extra",
            "completionist",
            "achievements",
            "last_played",
        ]

        for index, stat_name in enumerate(stat_order):
            stats_grid.addWidget(
                self.similar_stats[stat_name],
                index // 3,
                index % 3,
            )

        right_layout.addLayout(stats_grid)
        right_layout.addWidget(
            self.similar_details,
            1,
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(self.similar_left_panel)
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 7)

        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        splitter.setSizes(
            [
                760,
                840,
            ]
        )

        self.similar_splitter = splitter

        layout.addWidget(
            splitter,
            1,
        )

    def _connect_signals(self):
        self.type_filter.currentTextChanged.connect(self._filters_changed)
        self.genre_tag_filter.filters_changed.connect(self._filters_changed)
        self.hltb_metric_filter.currentTextChanged.connect(self._filters_changed)
        self.hltb_min_filter.valueChanged.connect(self._hltb_min_changed)
        self.hltb_max_filter.valueChanged.connect(self._hltb_max_changed)
        self.clear_filters_button.clicked.connect(self.clear_filters)

        self.rebuild_button.clicked.connect(self.rebuild_recommendations)

        self.for_you_steam_button.clicked.connect(self._open_selected_for_you_steam)
        self.for_you_previous_button.clicked.connect(self.previous_for_you)
        self.for_you_next_button.clicked.connect(self.next_for_you)

        self.find_similar_button.clicked.connect(self.find_similar_games)

        reference_line_edit = self.reference_combo.lineEdit()

        if reference_line_edit is not None:
            reference_line_edit.returnPressed.connect(self._reference_return_pressed)

        self.similar_result_combo.currentIndexChanged.connect(
            self._similar_result_changed
        )

        self.similar_steam_button.clicked.connect(self._open_selected_similar_steam)

        self.mode_tabs.currentChanged.connect(self._mode_changed)

        self.for_you_trailer_player.volume_changed.connect(
            self.similar_trailer_player.set_volume
        )

        self.similar_trailer_player.volume_changed.connect(
            self.for_you_trailer_player.set_volume
        )

    def set_games(self, games):
        self.games = list(games)

        self.games_by_id = {game.app_id: game for game in self.games}

        self.similar_index = None
        self.similar_all_scores = []
        self.similar_scores = []
        self.similar_scores_by_id = {}

        self._clear_similar_card()

        self.genre_tag_filter.set_available_from_games(self.games)

        self._populate_reference_games()

        self.refresh()

    def notify_inputs_changed(self):
        self._inputs_dirty = True
        self._auto_build_blocked = False

        if self.recommendation_build_running():
            self._dirty_during_build = True

        self.refresh()

        if self.isVisible() and not self._update_busy:
            QTimer.singleShot(0, self._maybe_auto_rebuild)

    def on_tab_activated(self):
        self.refresh()
        QTimer.singleShot(0, self._maybe_auto_rebuild)

    def _maybe_auto_rebuild(self):
        if self._auto_build_blocked:
            return

        if self._update_busy or self.recommendation_build_running():
            return

        if not self.isVisible():
            return

        if self.recommendation_state is not None and not self._inputs_dirty:
            return

        if not self.games:
            return

        self._start_recommendation_build(automatic=True)

    def refresh(self):
        self.genre_tag_filter.set_available_from_games(self.games)

        state = load_recommendation_state()
        rows = load_saved_recommendations()

        self.recommendation_state = state

        self.recommendation_records = []
        self.recommendations_by_id = {}

        for row in rows:
            (
                app_id,
                score,
                match_tier,
                explanation_json,
                row_generated_at,
            ) = row

            record = {
                "app_id": app_id,
                "score": score,
                "match_tier": match_tier,
                "explanation_json": explanation_json,
                "explanation": None,
                "explanation_loaded": False,
                "generated_at": row_generated_at,
            }

            self.recommendation_records.append(record)

            self.recommendations_by_id[app_id] = record

        self.recommendation_records.sort(
            key=lambda record: record["score"],
            reverse=True,
        )

        self._rebuild_for_you()
        self._update_rebuild_controls()

    def recommendation_build_running(self):
        return (
            self.recommendation_thread is not None
            and self.recommendation_thread.isRunning()
        )

    def set_update_busy(self, busy):
        self._update_busy = bool(busy)

        if self._update_busy:
            self.saved_status_label.setText(
                "Library data is currently being updated. "
                "Recommendations can be built after the update finishes or is cancelled."
            )
        else:
            self.refresh()

            if self.isVisible():
                QTimer.singleShot(0, self._maybe_auto_rebuild)

        self._update_rebuild_controls()

    def _update_rebuild_controls(self):
        building = self.recommendation_build_running()

        self.rebuild_progress.setVisible(building)

        if self._update_busy:
            self.rebuild_button.setEnabled(False)
            self.rebuild_button.setText("Data Update In Progress")
            self.rebuild_button.setToolTip(
                "Recommendations cannot be built while library data is being updated."
            )

            return

        self.rebuild_button.setToolTip("")

        if building:
            self.rebuild_button.setEnabled(False)
            self.rebuild_button.setText("Rebuilding Recommendations...")

        elif self.recommendation_state is None:
            self.rebuild_button.setEnabled(True)
            self.rebuild_button.setText("Build Recommendations")

        else:
            self.rebuild_button.setEnabled(True)
            self.rebuild_button.setText("Rebuild Recommendations")

    def rebuild_recommendations(self):
        self._auto_build_blocked = False
        self._start_recommendation_build(automatic=False)

    def _start_recommendation_build(self, automatic=False):
        if self._update_busy or self.recommendation_build_running():
            return

        self._automatic_build = bool(automatic)
        self._dirty_during_build = False
        self.saved_status_label.setText("Building personalized recommendations...")

        self.recommendation_thread = QThread(self)
        self.recommendation_worker = RecommendationBuildWorker()
        self.recommendation_worker.moveToThread(self.recommendation_thread)

        self.recommendation_thread.started.connect(self.recommendation_worker.run)
        self.recommendation_worker.succeeded.connect(self._recommendations_rebuilt)
        self.recommendation_worker.failed.connect(self._recommendations_rebuild_failed)
        self.recommendation_worker.finished.connect(self.recommendation_thread.quit)
        self.recommendation_worker.finished.connect(
            self.recommendation_worker.deleteLater
        )
        self.recommendation_thread.finished.connect(
            self._recommendation_thread_finished
        )
        self.recommendation_thread.finished.connect(
            self.recommendation_thread.deleteLater
        )

        self.build_busy_changed.emit(True)
        self.recommendation_thread.start()
        self._update_rebuild_controls()

    def _recommendations_rebuilt(self):
        if not self._dirty_during_build:
            self._inputs_dirty = False

        self._auto_build_blocked = False
        self.refresh()

    def _recommendations_rebuild_failed(self, message):
        self._inputs_dirty = True
        self._auto_build_blocked = self._automatic_build
        self.saved_status_label.setText("Recommendation rebuild failed.")
        detail = str(message)
        readiness_failure = "eligible backlog" in detail.casefold()

        if readiness_failure:
            detail = f"{detail}\n\n{self._recommendation_readiness_message()}"

        if not self._automatic_build or not readiness_failure:
            QMessageBox.warning(
                self,
                "Recommendations",
                detail,
            )

    def _recommendation_thread_finished(self):
        needs_followup = self._inputs_dirty and not self._auto_build_blocked

        self.recommendation_worker = None
        self.recommendation_thread = None
        self._automatic_build = False
        self._update_rebuild_controls()
        self.build_busy_changed.emit(False)

        if needs_followup and self.isVisible() and not self._update_busy:
            QTimer.singleShot(0, self._maybe_auto_rebuild)

    def _filters_changed(self):
        self._rebuild_for_you()
        self._apply_similar_filters()

    def _hltb_min_changed(
        self,
        min_hours,
    ):
        max_hours = self.hltb_max_filter.value()

        if min_hours > 0 and max_hours > 0 and min_hours > max_hours:
            self.hltb_max_filter.setValue(min_hours)

        self._filters_changed()

    def _hltb_max_changed(
        self,
        max_hours,
    ):
        min_hours = self.hltb_min_filter.value()

        if max_hours > 0 and min_hours > 0 and max_hours < min_hours:
            self.hltb_min_filter.setValue(max_hours)

        self._filters_changed()

    def clear_filters(self):
        self.type_filter.blockSignals(True)
        self.hltb_metric_filter.blockSignals(True)
        self.hltb_min_filter.blockSignals(True)
        self.hltb_max_filter.blockSignals(True)

        self.type_filter.setCurrentText("All Types")

        self.hltb_metric_filter.setCurrentText("Main Story")

        self.hltb_min_filter.setValue(0)
        self.hltb_max_filter.setValue(0)

        self.type_filter.blockSignals(False)
        self.hltb_metric_filter.blockSignals(False)
        self.hltb_min_filter.blockSignals(False)
        self.hltb_max_filter.blockSignals(False)

        if self.genre_tag_filter.has_active_filters():
            self.genre_tag_filter.clear_filters()
        else:
            self._filters_changed()

    def _game_passes_filters(
        self,
        game,
    ):
        selected_type = self.type_filter.currentText()

        if (
            selected_type != "All Types"
            and not self.genre_tag_filter.matches_type_filter(
                game,
                selected_type,
            )
        ):
            return False

        if (
            self.genre_tag_filter.has_active_filters()
            and not self.genre_tag_filter.matches_game(game)
        ):
            return False

        min_hours = self.hltb_min_filter.value()

        max_hours = self.hltb_max_filter.value()

        if min_hours > 0 or max_hours > 0:
            metric = self.hltb_metric_filter.currentText()

            hltb_time = game.hltb_time(metric)

            if hltb_time is None:
                return False

            if min_hours > 0 and hltb_time < min_hours:
                return False

            if max_hours > 0 and hltb_time > max_hours:
                return False

        return True

    def _has_active_filters(self):
        return (
            self.type_filter.currentText() != "All Types"
            or self.genre_tag_filter.has_active_filters()
            or self.hltb_min_filter.value() > 0
            or self.hltb_max_filter.value() > 0
        )

    def _recommendation_readiness_message(self):
        if not self.games:
            return (
                "The Steam library is empty. Use Maintenance > Refresh Steam Library "
                "before building recommendations."
            )

        eligible_games = [
            game
            for game in self.games
            if self.genre_tag_filter.is_backlog_eligible(game)
        ]
        unclassified = sum(
            1 for game in self.games if game.classification_updated_at is None
        )

        if not eligible_games:
            if unclassified:
                noun = "entry" if unclassified == 1 else "entries"
                verb = "needs" if unclassified == 1 else "need"

                return (
                    "No backlog-eligible games are classified yet. "
                    f"{unclassified:,} library {noun} still {verb} Steam "
                    "classification. Use Maintenance > Update Missing Data, then "
                    "build recommendations again."
                )

            return (
                "There are no backlog-eligible games in the current library. "
                "Check Steam classification and statuses in the Library."
            )

        backlog_games = [
            game for game in eligible_games if game.effective_status() == "Backlog"
        ]

        if not backlog_games:
            return (
                "There are currently no unplayed backlog games available for "
                "personalized recommendations."
            )

        content_ready = [game for game in backlog_games if game.genres or game.tags]

        if not content_ready:
            metadata_pending = sum(
                1 for game in backlog_games if not game.metadata_checked
            )

            if metadata_pending:
                return (
                    f"{metadata_pending:,} backlog game"
                    f"{'s' if metadata_pending != 1 else ''} still need Genre / Tag "
                    "data. Use Maintenance > Update Missing Data, then build "
                    "recommendations again."
                )

            return (
                "The eligible backlog currently has no usable Genre / Tag features "
                "for content-based recommendations."
            )

        return (
            "No eligible recommendation candidates were produced from the current "
            "library data. Try Update Missing Data, then rebuild recommendations."
        )

    def _rebuild_for_you(self):
        previous_app_id = None

        if 0 <= self.current_for_you_index < len(self.for_you_records):
            previous_app_id = self.for_you_records[self.current_for_you_index]["app_id"]

        self._cancel_for_you_animation()

        if self.recommendation_state is None:
            self.for_you_records = []

            if self._inputs_dirty:
                self.saved_status_label.setText(
                    "Needs rebuild • saved recommendations are missing or stale."
                )
            else:
                self.saved_status_label.setText(
                    "Recommendations have not been generated yet."
                )
            self._clear_for_you_card(
                "Use Build Recommendations above to create a personalized "
                "backlog shortlist from your current ratings and library data.",
                title="No recommendation build yet",
            )
            return

        if not self.recommendation_records:
            self.for_you_records = []
            freshness = "Needs rebuild" if self._inputs_dirty else "Up to date"
            self.saved_status_label.setText(
                f"{freshness} • the current recommendation build has no eligible "
                "backlog candidates."
            )
            self._clear_for_you_card(
                self._recommendation_readiness_message(),
                title="No games to recommend",
            )
            return

        eligible = []

        for record in self.recommendation_records:
            game = self.games_by_id.get(record["app_id"])

            if game is None:
                continue

            if not self._game_passes_filters(game):
                continue

            eligible.append(record)

        self.for_you_records = self._select_for_you_records(eligible)

        if not self.for_you_records:
            self._update_saved_status(
                eligible_count=0,
                showing_count=0,
            )

            if self._has_active_filters():
                message = (
                    "No saved recommendations match the current filters. "
                    "Use Clear Filters to return to the full recommendation pool."
                )
                title = "No recommendations match these filters"
            else:
                message = (
                    "The saved recommendation build does not contain any games "
                    "that are currently eligible in this library."
                )
                title = "No eligible recommendations"

            self._clear_for_you_card(
                message,
                title=title,
            )
            return

        selected_index = 0

        if previous_app_id is not None:
            for index, record in enumerate(self.for_you_records):
                if record["app_id"] == previous_app_id:
                    selected_index = index
                    break

        self.current_for_you_index = selected_index
        self._populate_for_you_card()

        self._update_saved_status(
            eligible_count=len(eligible),
            showing_count=len(self.for_you_records),
        )

    def _select_for_you_records(
        self,
        eligible,
    ):
        if not eligible:
            return []

        eligible = sorted(
            eligible,
            key=lambda record: record["score"],
            reverse=True,
        )

        selected = []
        selected_ids = set()

        saved_top_picks = [
            record for record in eligible if record["match_tier"] == "top_pick"
        ]

        for record in saved_top_picks:
            if len(selected) >= FOR_YOU_LIMIT:
                break

            selected.append(record)

            selected_ids.add(record["app_id"])

        remaining = [
            record for record in eligible if record["app_id"] not in selected_ids
        ]

        while remaining and len(selected) < FOR_YOU_LIMIT:
            if not selected:
                chosen = remaining[0]
            else:
                window = remaining[:20]

                chosen = min(
                    window,
                    key=lambda record: (
                        self._maximum_feature_overlap(
                            record,
                            selected,
                        ),
                        -record["score"],
                    ),
                )

            selected.append(chosen)

            selected_ids.add(chosen["app_id"])

            remaining.remove(chosen)

        return selected

    def _maximum_feature_overlap(
        self,
        candidate_record,
        selected_records,
    ):
        candidate_game = self.games_by_id.get(candidate_record["app_id"])

        if candidate_game is None:
            return 1.0

        candidate_features = self._game_feature_keys(candidate_game)

        if not candidate_features:
            return 1.0

        highest_overlap = 0.0

        for record in selected_records:
            selected_game = self.games_by_id.get(record["app_id"])

            if selected_game is None:
                continue

            selected_features = self._game_feature_keys(selected_game)

            if not selected_features:
                continue

            union = candidate_features | selected_features

            if not union:
                continue

            overlap = len(candidate_features & selected_features) / len(union)

            highest_overlap = max(
                highest_overlap,
                overlap,
            )

        return highest_overlap

    @staticmethod
    def _game_feature_keys(game):
        features = {
            f"genre:{genre.casefold()}" for genre in (game.genres or []) if genre
        }

        features.update({f"tag:{tag.casefold()}" for tag in (game.tags or {}) if tag})

        return features

    def _request_short_description(self, game):
        if game.steam_short_description is not None:
            return

        if game.app_id in self.description_requests_in_flight:
            return

        self.description_requests_in_flight.add(game.app_id)

        worker = StoreDescriptionWorker(game.app_id)
        worker.signals.loaded.connect(self._short_description_loaded)
        worker.signals.failed.connect(self._short_description_failed)
        self.thread_pool.start(worker)

    def _short_description_loaded(self, app_id, description):
        self.description_requests_in_flight.discard(app_id)
        game = self.games_by_id.get(app_id)

        if game is None:
            return

        game.steam_short_description = description

        if 0 <= self.current_for_you_index < len(self.for_you_records):
            record = self.for_you_records[self.current_for_you_index]

            if record["app_id"] == app_id:
                self._render_for_you_text(game, record)

        selected_similar_app_id = self._selected_similar_app_id()

        if selected_similar_app_id == app_id:
            score = self.similar_scores_by_id.get(app_id)

            if score is not None:
                reference_game = self.games_by_id.get(self.similar_reference_app_id)
                reference_name = (
                    reference_game.name
                    if reference_game is not None
                    else "the selected game"
                )
                self._render_similar_text(game, score, reference_name)

    def _short_description_failed(self, app_id, _error_message):
        self.description_requests_in_flight.discard(app_id)

    @staticmethod
    def _description_text(game):
        description = game.steam_short_description

        if description is None:
            return "Loading Steam description..."

        if not description:
            return "No Steam description is available."

        return description

    @staticmethod
    def _status_badge_tone(status):
        tones = {
            "Backlog": "accent",
            "Playing": "accent",
            "Completed": "positive",
            "On Hold": "warning",
            "Dropped": "danger",
            "Inactive": "neutral",
        }

        return tones.get(status, "neutral")

    @staticmethod
    def _reception_badge(game):
        positive = game.steamspy_positive
        negative = game.steamspy_negative

        if positive is None or negative is None:
            return "RECEPTION UNKNOWN", "neutral"

        total = positive + negative

        if total == 0:
            return "NO REVIEWS", "neutral"

        percent = positive / total * 100

        if total < PUBLIC_RECEPTION_MIN_REVIEWS:
            tone = "warning"
        elif percent >= 80:
            tone = "positive"
        elif percent >= 60:
            tone = "accent"
        elif percent >= 45:
            tone = "warning"
        else:
            tone = "danger"

        return f"{percent:.0f}% POSITIVE", tone

    def _update_stat_tiles(self, tiles, game):
        playtime_hours = (game.playtime_minutes or 0) / 60

        values = {
            "playtime": f"{playtime_hours:.1f} h",
            "main": self._format_hours(game.hltb_main),
            "main_extra": self._format_hours(game.hltb_main_extra),
            "completionist": self._format_hours(game.hltb_completionist),
            "achievements": self._achievement_text(game),
            "last_played": self._last_played_text(game),
        }

        for name, value in values.items():
            tiles[name].set_value(value)

    @staticmethod
    def _description_html(game):
        description = game.steam_short_description

        if description is None:
            return "<p><i>Loading Steam description...</i></p>"

        if not description:
            return "<p><i>No Steam description is available.</i></p>"

        return f"<p>{html.escape(description)}</p>"

    @staticmethod
    def _last_played_text(game):
        timestamp = game.last_played_timestamp or 0

        if timestamp <= 0:
            return "Never"

        return (
            datetime.fromtimestamp(timestamp, tz=UTC).astimezone().strftime("%b %d, %Y")
        )

    @staticmethod
    def _achievement_text(game):
        if game.achievement_total is None or game.achievements_unlocked is None:
            return "Unknown"

        if game.achievement_total == 0:
            return "None"

        return f"{game.achievements_unlocked}/{game.achievement_total}"

    def _at_a_glance_html(self, game):
        playtime_hours = (game.playtime_minutes or 0) / 60
        rows = [
            ("Library status", game.effective_status()),
            ("Steam playtime", f"{playtime_hours:.1f} h"),
            ("Last played", self._last_played_text(game)),
            ("Main Story", self._format_hours(game.hltb_main)),
            ("Main + Extra", self._format_hours(game.hltb_main_extra)),
            ("Completionist", self._format_hours(game.hltb_completionist)),
            ("Achievements", self._achievement_text(game)),
        ]

        cells = "".join(
            f"<tr><td style='padding-right:18px;'><b>{html.escape(label)}</b></td>"
            f"<td>{html.escape(value)}</td></tr>"
            for label, value in rows
        )

        return f"<table cellspacing='0' cellpadding='2'>{cells}</table>"

    def _render_for_you_text(self, game, record):
        self.for_you_title.setText(game.name)

        steam_type_text = self.genre_tag_filter.display_steam_type(game)
        reception_text = self._public_reception_text(game)
        reception_badge, reception_tone = self._reception_badge(game)
        match_label = self._recommendation_match_label(record)
        score_text = self._friendly_score(record["score"])
        status = game.effective_status()

        self.for_you_match_badge.set_badge(match_label.upper(), "accent")
        self.for_you_score_badge.set_badge(
            f"{score_text} MATCH",
            "accent",
            f"Exact recommendation score: {record['score']:.4f}",
        )
        self.for_you_status_badge.set_badge(
            status.upper(),
            self._status_badge_tone(status),
        )
        self.for_you_type_badge.set_badge(steam_type_text.upper(), "neutral")
        self.for_you_reception_badge.set_badge(
            reception_badge,
            reception_tone,
            reception_text,
        )

        self.for_you_description.setText(self._description_text(game))
        self._update_stat_tiles(self.for_you_stats, game)

        explanation = self._explanation_for(record)
        self.for_you_details.setHtml(
            self._format_recommendation_explanation(game, explanation)
        )

    def _render_similar_text(self, game, score, reference_name):
        self.similar_title.setText(game.name)
        steam_type_text = self.genre_tag_filter.display_steam_type(game)
        reception_text = self._public_reception_text(game)
        reception_badge, reception_tone = self._reception_badge(game)
        similarity_label = self._similarity_match_label(score.adjusted_similarity)
        similarity_text = self._friendly_score(score.adjusted_similarity)
        status = game.effective_status()

        self.similar_match_badge.set_badge(similarity_label.upper(), "accent")
        self.similar_score_badge.set_badge(
            f"{similarity_text} MATCH",
            "accent",
            f"Exact adjusted similarity: {score.adjusted_similarity:.4f}",
        )
        self.similar_status_badge.set_badge(
            status.upper(),
            self._status_badge_tone(status),
        )
        self.similar_type_badge.set_badge(steam_type_text.upper(), "neutral")
        self.similar_reception_badge.set_badge(
            reception_badge,
            reception_tone,
            reception_text,
        )
        self.similar_context_label.setText(f"Similar to {reference_name}")
        self.similar_description.setText(self._description_text(game))
        self._update_stat_tiles(self.similar_stats, game)

        shared_traits = [html.escape(name) for name in score.shared_traits]
        genres = [html.escape(genre) for genre in (game.genres or [])]
        sorted_tags = sorted(
            (game.tags or {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )
        tag_names = [html.escape(tag) for tag, _weight in sorted_tags[:10]]

        detail_parts = [
            "<h3>Why it's similar</h3>",
            f"<p><b>Shared feature count:</b> {score.shared_feature_count}</p>",
        ]

        if shared_traits:
            detail_parts.append("<h3>Shared traits</h3>")
            detail_parts.append("<p>" + " • ".join(shared_traits) + "</p>")

        detail_parts.append("<h3>Game metadata</h3>")
        detail_parts.append(
            "<p><b>Genres:</b> "
            + (" • ".join(genres) if genres else "Unknown")
            + "</p>"
        )
        detail_parts.append(
            "<p><b>Top tags:</b> "
            + (" • ".join(tag_names) if tag_names else "Unknown")
            + "</p>"
        )
        detail_parts.append(
            "<p>This similarity result is based on genre/tag content features. "
            "It does not use your overall personalized taste profile.</p>"
        )
        self.similar_details.setHtml("".join(detail_parts))

    def _populate_for_you_card(self):
        if not 0 <= self.current_for_you_index < len(self.for_you_records):
            self._clear_for_you_card("No recommendation selected.")
            return

        record = self.for_you_records[self.current_for_you_index]
        game = self.games_by_id.get(record["app_id"])

        if game is None:
            self._clear_for_you_card("The selected recommendation is unavailable.")
            return

        total = len(self.for_you_records)

        self.for_you_image.setPixmap(QPixmap())
        self.for_you_image.setText("Loading image…")

        self._request_image(
            game.app_id,
            self.for_you_image,
        )

        self.for_you_hltb.setText(self._hltb_text(game))

        self.for_you_trailer_player.set_game(game.app_id)

        self.for_you_steam_button.setEnabled(True)

        self.for_you_position_label.setText(
            f"{self.current_for_you_index + 1} of {total}"
        )

        navigation_enabled = total > 1

        self.for_you_previous_button.setEnabled(navigation_enabled)

        self.for_you_next_button.setEnabled(navigation_enabled)

        self._render_for_you_text(game, record)
        self._request_short_description(game)

    def _clear_for_you_card(self, message, title="No recommendation available"):
        self.current_for_you_index = -1

        self.for_you_image.setProperty(
            "steam_app_id",
            None,
        )

        self.for_you_image.setPixmap(QPixmap())
        self.for_you_image.setProperty("image_path", None)
        self.for_you_image.setText(title)

        self.for_you_hltb.setText(self._empty_hltb_text())

        self.for_you_trailer_player.clear_game()

        self.for_you_steam_button.setEnabled(False)
        self.for_you_previous_button.setEnabled(False)
        self.for_you_next_button.setEnabled(False)

        self.for_you_position_label.setText("0 of 0")

        self.for_you_title.setText(title)
        self.for_you_match_badge.set_badge("TOP PICK", "neutral")
        self.for_you_score_badge.set_badge("- MATCH", "neutral")
        self.for_you_status_badge.set_badge("NO SELECTION", "neutral")
        self.for_you_type_badge.set_badge("-", "neutral")
        self.for_you_reception_badge.set_badge("-", "neutral")
        self.for_you_description.setText(message)

        for tile in self.for_you_stats.values():
            tile.set_value("-")

        self.for_you_details.clear()

    def previous_for_you(self):
        if len(self.for_you_records) <= 1:
            return

        if self._for_you_animation is not None:
            return

        new_index = (self.current_for_you_index - 1) % len(self.for_you_records)

        self._animate_to_for_you_index(new_index)

    def next_for_you(self):
        if len(self.for_you_records) <= 1:
            return

        if self._for_you_animation is not None:
            return

        new_index = (self.current_for_you_index + 1) % len(self.for_you_records)

        self._animate_to_for_you_index(new_index)

    def _animate_to_for_you_index(self, index):
        if not 0 <= index < len(self.for_you_records):
            return

        if index == self.current_for_you_index:
            return

        self.for_you_trailer_player.stop()

        effect = QGraphicsOpacityEffect(self.for_you_left_panel)

        effect.setOpacity(1.0)

        self.for_you_left_panel.setGraphicsEffect(effect)

        self._for_you_effect = effect

        animation = QPropertyAnimation(
            effect,
            b"opacity",
            self,
        )

        animation.setDuration(120)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._for_you_animation = animation

        animation.finished.connect(lambda: self._for_you_fade_out_finished(index))

        animation.start()

    def _for_you_fade_out_finished(self, index):
        if self._for_you_animation is not None:
            self._for_you_animation.deleteLater()
            self._for_you_animation = None

        if self._for_you_effect is None:
            return

        self.current_for_you_index = index
        self._populate_for_you_card()

        self._for_you_effect.setOpacity(0.0)

        animation = QPropertyAnimation(
            self._for_you_effect,
            b"opacity",
            self,
        )

        animation.setDuration(150)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._for_you_animation = animation

        animation.finished.connect(self._for_you_fade_in_finished)

        animation.start()

    def _for_you_fade_in_finished(self):
        if self._for_you_animation is not None:
            self._for_you_animation.deleteLater()
            self._for_you_animation = None

        if self._for_you_effect is None:
            return

        self.for_you_left_panel.setGraphicsEffect(None)

        self._for_you_effect = None

    def _cancel_for_you_animation(self):
        if self._for_you_animation is not None:
            self._for_you_animation.stop()
            self._for_you_animation.deleteLater()
            self._for_you_animation = None

        if self._for_you_effect is None:
            return

        self.for_you_left_panel.setGraphicsEffect(None)

        self._for_you_effect = None

    def _open_selected_for_you_steam(self):
        if not 0 <= self.current_for_you_index < len(self.for_you_records):
            return

        app_id = self.for_you_records[self.current_for_you_index]["app_id"]

        self._open_steam_page(app_id)

    def _update_saved_status(
        self,
        eligible_count,
        showing_count,
    ):
        state = self.recommendation_state

        if state is None:
            if self._inputs_dirty:
                self.saved_status_label.setText(
                    "Needs rebuild • no saved recommendation build."
                )
            else:
                self.saved_status_label.setText("No saved recommendation build.")
            return

        (
            method,
            model_version,
            feature_version,
            _generated_at,
            training_game_count,
            rated_game_count,
            implicit_game_count,
            candidate_game_count,
        ) = state

        freshness = "Needs rebuild" if self._inputs_dirty else "Up to date"

        self.saved_status_label.setText(
            f"{freshness} • {len(self.recommendation_records)} saved recommendations"
            f" • {eligible_count} match filters"
            f" • showing {showing_count}"
            f" • {candidate_game_count} candidates scored"
            f" • {rated_game_count} rated games"
            f" • {implicit_game_count} implicit-only games"
            f" • {method}"
            f" • model {model_version}"
            f" • features {feature_version}"
            f" • {training_game_count} training games"
        )

    def _explanation_for(
        self,
        record,
    ):
        if record["explanation_loaded"]:
            return record["explanation"]

        record["explanation_loaded"] = True

        explanation_json = record["explanation_json"]

        if not explanation_json:
            record["explanation"] = None
            return None

        try:
            record["explanation"] = json.loads(explanation_json)
        except json.JSONDecodeError:
            record["explanation"] = None

        return record["explanation"]

    def _format_recommendation_explanation(
        self,
        game,
        explanation,
    ):
        parts = [
            "<h3>Why it fits</h3>",
        ]

        if explanation:
            taste_features = explanation.get(
                "taste_features",
                [],
            )

            taste_names = [
                html.escape(
                    feature.get(
                        "name",
                        "Unknown",
                    )
                )
                for feature in taste_features
            ]

            if taste_names:
                parts.append("<p><b>" + " • ".join(taste_names) + "</b></p>")
            else:
                parts.append("<p>No strong taste traits were identified.</p>")

            supporting_games = explanation.get(
                "supporting_games",
                [],
            )

            if supporting_games:
                parts.append("<h3>Based on games you've played</h3>")

                for supporting_game in supporting_games:
                    name = html.escape(
                        supporting_game.get(
                            "name",
                            "Unknown",
                        )
                    )

                    similarity = supporting_game.get(
                        "adjusted_similarity",
                        0.0,
                    )

                    shared_names = [
                        html.escape(
                            feature.get(
                                "name",
                                "Unknown",
                            )
                        )
                        for feature in supporting_game.get(
                            "shared_features",
                            [],
                        )
                    ]

                    parts.append(
                        f"<p><b>{name}</b><br>"
                        f"Similarity: {self._friendly_score(similarity)}"
                    )

                    if shared_names:
                        parts.append("<br>Shared traits: " + " • ".join(shared_names))

                    parts.append("</p>")
        else:
            parts.append(
                "<p>No explanation data is available for this recommendation.</p>"
            )

        genres = [html.escape(genre) for genre in (game.genres or [])]

        sorted_tags = sorted(
            (game.tags or {}).items(),
            key=lambda item: item[1],
            reverse=True,
        )

        tag_names = [html.escape(tag) for tag, _weight in sorted_tags[:10]]

        parts.append("<h3>Game metadata</h3>")

        parts.append(
            "<p><b>Genres:</b> "
            + (" • ".join(genres) if genres else "Unknown")
            + "</p>"
        )

        parts.append(
            "<p><b>Top tags:</b> "
            + (" • ".join(tag_names) if tag_names else "Unknown")
            + "</p>"
        )

        return "".join(parts)

    def _populate_reference_games(self):
        current_app_id = self.similar_reference_app_id

        self.reference_combo.blockSignals(True)

        self.reference_combo.clear()

        selectable_games = [game for game in self.games if game.genres or game.tags]

        selectable_games.sort(
            key=lambda game: (
                game.name.casefold(),
                game.app_id,
            )
        )

        selected_index = -1

        for index, game in enumerate(selectable_games):
            display_name = f"{game.name} ({game.app_id})"

            self.reference_combo.addItem(
                display_name,
                game.app_id,
            )

            if game.app_id == current_app_id:
                selected_index = index

        if selected_index >= 0:
            self.reference_combo.setCurrentIndex(selected_index)
        else:
            self.reference_combo.setCurrentIndex(-1)

            self.reference_combo.setEditText("")

        self.reference_combo.blockSignals(False)

    def _reference_return_pressed(self):
        reference_app_id = self._selected_reference_app_id()

        if reference_app_id is None:
            typed_name = self.reference_combo.currentText().strip().casefold()

            matches = [
                index
                for index in range(self.reference_combo.count())
                if self.reference_combo.itemText(index).rsplit(" (", 1)[0].casefold()
                == typed_name
            ]

            if len(matches) == 1:
                self.reference_combo.setCurrentIndex(matches[0])

        self.find_similar_games()

    def find_similar_games(self):
        reference_app_id = self._selected_reference_app_id()

        if reference_app_id is None:
            QMessageBox.information(
                self,
                "Similar Games",
                "Choose a game from the reference-game list first.",
            )

            return

        reference_game = self.games_by_id.get(reference_app_id)

        if reference_game is None:
            QMessageBox.warning(
                self,
                "Similar Games",
                "The selected reference game is no longer in the library.",
            )

            return

        if not reference_game.genres and not reference_game.tags:
            self.similar_reference_app_id = reference_app_id
            self.similar_all_scores = []
            self.similar_status_label.setText(
                f"{reference_game.name} does not have usable genre/tag metadata "
                "for similarity matching."
            )
            self._clear_similar_card(
                "Choose a reference game with Steam genres or SteamSpy tags.",
                title="Not enough metadata",
            )
            return

        self.similar_reference_app_id = reference_app_id

        if self.similar_index is None:
            self.similar_status_label.setText("Building the local similarity index…")

            self.similar_index = SimilarGameIndex(self.games)

        scores = self.similar_index.find_similar(
            reference_app_id,
            limit=SIMILAR_SEARCH_LIMIT,
            unplayed_only=True,
        )

        self.similar_all_scores = list(scores)

        self._apply_similar_filters()

    def _apply_similar_filters(self):
        self.similar_result_combo.blockSignals(True)

        self.similar_result_combo.clear()

        self.similar_scores = []
        self.similar_scores_by_id = {}

        if self.similar_reference_app_id is None:
            self.similar_result_combo.setEnabled(False)
            self.similar_result_combo.blockSignals(False)
            self.similar_status_label.setText(
                "Choose any owned game with genre/tag data."
            )
            self._clear_similar_card(
                "Choose a reference game, then find similar unplayed backlog games.",
                title="Choose a reference game",
            )
            return

        if not self.similar_all_scores:
            self.similar_result_combo.setEnabled(False)
            self.similar_result_combo.blockSignals(False)

            reference_game = self.games_by_id.get(self.similar_reference_app_id)
            reference_name = (
                reference_game.name
                if reference_game is not None
                else "the selected game"
            )

            self.similar_status_label.setText(
                f"No similar unplayed backlog games were found for {reference_name}."
            )
            self._clear_similar_card(
                "No eligible unplayed games with sufficient content similarity "
                "were found for this reference game.",
                title="No similar games found",
            )
            return

        for score in self.similar_all_scores:
            game = self.games_by_id.get(score.app_id)

            if game is None:
                continue

            if not self._game_passes_filters(game):
                continue

            self.similar_scores.append(score)

            self.similar_scores_by_id[score.app_id] = score

            if len(self.similar_scores) >= SIMILAR_RESULT_LIMIT:
                break

        for score in self.similar_scores:
            game = self.games_by_id.get(score.app_id)

            if game is None:
                continue

            display_text = (
                f"{game.name} - {self._friendly_score(score.adjusted_similarity)}"
            )

            self.similar_result_combo.addItem(
                display_text,
                score.app_id,
            )

        has_results = bool(self.similar_scores)

        self.similar_result_combo.setEnabled(has_results)

        self.similar_result_combo.blockSignals(False)

        reference_game = self.games_by_id.get(self.similar_reference_app_id)

        reference_name = (
            reference_game.name if reference_game is not None else "the selected game"
        )

        if not has_results:
            if self._has_active_filters():
                self.similar_status_label.setText(
                    f"Similar games were found for {reference_name}, but none match "
                    "the current filters."
                )
                message = (
                    "No Similar-to-a-Game results match the current filters. "
                    "Use Clear Filters to see the available matches."
                )
                title = "No similar games match these filters"
            else:
                self.similar_status_label.setText(
                    f"No eligible similar backlog games were found for {reference_name}."
                )
                message = (
                    "No eligible unplayed backlog games remain for this reference game."
                )
                title = "No similar games found"

            self._clear_similar_card(
                message,
                title=title,
            )

            return

        self.similar_status_label.setText(
            f"Showing {len(self.similar_scores)} "
            f"filtered results similar to "
            f"{reference_name}. "
            f"This view uses content similarity, "
            f"not your global taste profile."
        )

        self.similar_result_combo.setCurrentIndex(0)

        self._show_similar_score(self.similar_scores[0])

    def _selected_reference_app_id(self):
        current_index = self.reference_combo.currentIndex()

        current_text = self.reference_combo.currentText().strip()

        if current_index >= 0:
            item_text = self.reference_combo.itemText(current_index)

            if item_text == current_text:
                return self.reference_combo.itemData(current_index)

        for index in range(self.reference_combo.count()):
            if (
                self.reference_combo.itemText(index).casefold()
                == current_text.casefold()
            ):
                return self.reference_combo.itemData(index)

        return None

    def _similar_result_changed(
        self,
        index,
    ):
        if index < 0:
            return

        app_id = self.similar_result_combo.itemData(index)

        score = self.similar_scores_by_id.get(app_id)

        if score is None:
            return

        self._show_similar_score(score)

    def _show_similar_score(
        self,
        score,
    ):
        game = self.games_by_id.get(score.app_id)
        reference_game = self.games_by_id.get(self.similar_reference_app_id)

        if game is None:
            self._clear_similar_card()
            return

        reference_name = (
            reference_game.name if reference_game is not None else "the selected game"
        )

        self._render_similar_text(game, score, reference_name)
        self._request_short_description(game)
        self.similar_hltb.setText(self._hltb_text(game))
        self.similar_steam_button.setEnabled(True)
        self.similar_trailer_player.set_game(game.app_id)
        self.similar_image.setProperty(
            "steam_app_id",
            game.app_id,
        )
        self._request_image(
            game.app_id,
            self.similar_image,
        )

    def _clear_similar_card(
        self,
        message="Choose a reference game to find similar backlog games.",
        title="No similar game selected",
    ):
        self.similar_image.setProperty(
            "steam_app_id",
            None,
        )

        self.similar_image.setPixmap(QPixmap())
        self.similar_image.setProperty("image_path", None)
        self.similar_image.setText(title)

        self.similar_hltb.setText(self._empty_hltb_text())

        self.similar_title.setText(title)
        self.similar_match_badge.set_badge("SIMILARITY", "neutral")
        self.similar_score_badge.set_badge("- MATCH", "neutral")
        self.similar_status_badge.set_badge("NO SELECTION", "neutral")
        self.similar_type_badge.set_badge("-", "neutral")
        self.similar_reception_badge.set_badge("-", "neutral")
        self.similar_context_label.setText("")
        self.similar_description.setText(message)

        for tile in self.similar_stats.values():
            tile.set_value("-")

        self.similar_details.clear()

        self.similar_steam_button.setEnabled(False)
        self.similar_trailer_player.clear_game()

    def _open_selected_similar_steam(self):
        app_id = self._selected_similar_app_id()

        if app_id is None:
            return

        self._open_steam_page(app_id)

    def _selected_similar_app_id(self):
        index = self.similar_result_combo.currentIndex()

        if index < 0:
            return None

        return self.similar_result_combo.itemData(index)

    @staticmethod
    def _open_steam_page(app_id):
        QDesktopServices.openUrl(QUrl(f"https://store.steampowered.com/app/{app_id}/"))

    @staticmethod
    def _format_hours(value):
        if value is None:
            return "-"

        return f"{value:.1f} h"

    def _hltb_text(self, game):
        return (
            f"Main Story: "
            f"{self._format_hours(game.hltb_main)}\n"
            f"Main + Extra: "
            f"{self._format_hours(game.hltb_main_extra)}\n"
            f"Completionist: "
            f"{self._format_hours(game.hltb_completionist)}\n"
            f"All Styles: "
            f"{self._format_hours(game.hltb_all_styles)}"
        )

    def _empty_hltb_text(self):
        return "Main Story: -\nMain + Extra: -\nCompletionist: -\nAll Styles: -"

    def _request_image(
        self,
        app_id,
        label,
    ):
        label.setProperty(
            "steam_app_id",
            app_id,
        )

        cached_path = get_cached_image_path(app_id)

        if cached_path.exists():
            self._set_image(
                label,
                str(cached_path),
            )

            return

        label.setPixmap(QPixmap())

        label.setText("Loading image…")

        targets = self.image_targets.setdefault(
            app_id,
            [],
        )

        if label not in targets:
            targets.append(label)

        if app_id in self.image_requests_in_flight:
            return

        self.image_requests_in_flight.add(app_id)

        worker = ImageWorker(app_id)

        worker.signals.loaded.connect(self._image_loaded)

        self.thread_pool.start(worker)

    def _image_loaded(
        self,
        app_id,
        image_path,
    ):
        self.image_requests_in_flight.discard(app_id)

        labels = self.image_targets.pop(
            app_id,
            [],
        )

        for label in labels:
            try:
                label_app_id = label.property("steam_app_id")
            except RuntimeError:
                continue

            if label_app_id != app_id:
                continue

            if image_path:
                self._set_image(
                    label,
                    image_path,
                )
            else:
                label.setPixmap(QPixmap())

                label.setText("Image unavailable")

    def _set_image(
        self,
        label,
        image_path,
    ):
        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            label.setPixmap(QPixmap())

            label.setText("Image unavailable")

            return

        label.setProperty("image_path", image_path)
        self._rescale_image_label(label, pixmap)
        QTimer.singleShot(
            0,
            lambda target=label: self._rescale_image_label(target),
        )

    def _rescale_image_label(self, label, pixmap=None):
        if pixmap is None:
            image_path = label.property("image_path")

            if not image_path:
                return

            pixmap = QPixmap(image_path)

        if pixmap.isNull():
            return

        scaled = pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        label.setText("")
        label.setPixmap(scaled)

    def _update_media_sizes(self):
        panels = (
            (
                self.for_you_left_panel,
                self.for_you_left_content,
                self.for_you_image,
            ),
            (
                self.similar_left_panel,
                self.similar_left_content,
                self.similar_image,
            ),
        )

        for panel, content, label in panels:
            layout = content.layout()
            margins = layout.contentsMargins()

            available_width = (
                panel.viewport().contentsRect().width()
                - margins.left()
                - margins.right()
            )

            image_width = max(
                320,
                min(available_width, 720),
            )

            image_height = int(image_width * CARD_IMAGE_HEIGHT / CARD_IMAGE_WIDTH)

            label.setFixedSize(
                image_width,
                image_height,
            )

            self._rescale_image_label(label)

    def _update_responsive_typography(self):
        width = self.width()

        if width >= 1700:
            title_size = 21
            detail_size = 13
            hltb_title_size = 13
            hltb_size = 12
        elif width >= 1350:
            title_size = 19
            detail_size = 12
            hltb_title_size = 12
            hltb_size = 11
        else:
            title_size = 17
            detail_size = 11
            hltb_title_size = 10
            hltb_size = 10

        self.for_you_title.setStyleSheet(
            f"font-size: {title_size}pt; font-weight: bold;"
        )
        self.similar_title.setStyleSheet(
            f"font-size: {title_size}pt; font-weight: bold;"
        )

        for label in (self.for_you_hltb_title, self.similar_hltb_title):
            font = label.font()
            font.setPointSize(hltb_title_size)
            font.setBold(True)
            label.setFont(font)

        for label in (self.for_you_hltb, self.similar_hltb):
            font = label.font()
            font.setPointSize(hltb_size)
            label.setFont(font)

        for browser in (self.for_you_details, self.similar_details):
            font = browser.font()
            font.setPointSize(detail_size)
            browser.setFont(font)

    def refresh_theme(self):
        for browser in (self.for_you_details, self.similar_details):
            self._refresh_details_browser_style(browser)

        for panel in (self.for_you_left_panel, self.similar_left_panel):
            panel.style().unpolish(panel)
            panel.style().polish(panel)
            panel.update()

        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._update_media_sizes)
        QTimer.singleShot(0, self._update_responsive_typography)
        QTimer.singleShot(0, self.on_tab_activated)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_media_sizes()
        self._update_responsive_typography()

    def _mode_changed(self, index):
        if index == 0:
            self.similar_trailer_player.pause()
        else:
            self.for_you_trailer_player.pause()

    def hideEvent(self, event):
        self.for_you_trailer_player.pause()
        self.similar_trailer_player.pause()

        super().hideEvent(event)
