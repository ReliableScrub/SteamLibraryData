import random
import time
from datetime import UTC, datetime

from PySide6.QtCore import (
    QEvent,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from game_updates import (
    accept_hltb_candidate,
    set_hltb_no_match,
    update_achievements,
    update_hltb,
    update_metadata,
)
from recommendations.baseline import PUBLIC_RECEPTION_MIN_REVIEWS
from storage.database import (
    clear_game_rating,
    get_game_rating,
    load_game_ratings,
    load_hltb_candidates,
    save_manual_status,
    set_game_rating,
)
from storage.image_cache import get_game_image
from storage.settings import (
    get_library_view_settings,
    set_library_view_settings,
)
from ui.game_table_model import GameTableModel
from ui.genre_tag_filter import GenreTagFilterWidget
from ui.semantic_widgets import BadgeLabel, SectionHeading, SelectAllDoubleSpinBox
from ui.store_description_loader import StoreDescriptionWorker
from ui.trailer_player import TrailerPlayer

LIBRARY_DISPLAY_PRESETS = {
    "Compact": {
        "table_font": 11,
        "header_font": 13,
        "row_height": 30,
        "detail_font": 11,
        "title_narrow": 15,
        "title_wide": 17,
    },
    "Normal": {
        "table_font": 12,
        "header_font": 14,
        "row_height": 36,
        "detail_font": 12,
        "title_narrow": 16,
        "title_wide": 18,
    },
    "Large": {
        "table_font": 14,
        "header_font": 16,
        "row_height": 46,
        "detail_font": 14,
        "title_narrow": 18,
        "title_wide": 20,
    },
}
DEFAULT_LIBRARY_DISPLAY_SIZE = "Normal"

DEFAULT_LIBRARY_COLUMN_WIDTHS = (
    320,  # Game
    110,  # Status
    120,  # Steam Playtime
    130,  # Last Played
    90,  # Rating
    150,  # HLTB Time
    120,  # Achievements
    130,  # Steam Type
)


class SelectedGameRefreshSignals(QObject):
    result_ready = Signal(str, object, object)
    failed = Signal(str, object, str)
    finished = Signal()


class SelectedGameRefreshWorker(QRunnable):
    def __init__(
        self,
        source,
        game,
        steam_id=None,
        steam_api_key=None,
    ):
        super().__init__()

        self.source = source
        self.game = game
        self.steam_id = steam_id
        self.steam_api_key = steam_api_key
        self.signals = SelectedGameRefreshSignals()

    def run(self):
        try:
            if self.source == "hltb":
                update_hltb(self.game)

            elif self.source == "metadata":
                update_metadata(self.game)

            elif self.source == "achievements":
                if not self.steam_id:
                    raise ValueError("A SteamID64 is required to refresh achievements.")

                if not self.steam_api_key:
                    raise ValueError(
                        "A Steam Web API key is required to refresh achievements."
                    )

                update_achievements(
                    self.game,
                    self.steam_id,
                    self.steam_api_key,
                )

            else:
                raise ValueError(f"Unknown selected-game refresh source: {self.source}")

            self.signals.result_ready.emit(
                self.source,
                self.game,
                None,
            )

        except Exception as error:  # noqa: BLE001
            self.signals.failed.emit(
                self.source,
                self.game,
                f"{type(error).__name__}: {error}",
            )

        finally:
            self.signals.finished.emit()


class SelectedGameRefreshController(QObject):
    busy_changed = Signal(bool)
    succeeded = Signal(str, object)
    failed = Signal(str, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.thread_pool = QThreadPool.globalInstance()
        self._busy = False
        self._active_worker = None

    def is_running(self):
        return self._busy

    def start(
        self,
        source,
        game,
        steam_id=None,
        steam_api_key=None,
    ):
        if self._busy or game is None:
            return False

        self._busy = True
        self.busy_changed.emit(True)

        worker = SelectedGameRefreshWorker(
            source,
            game,
            steam_id=steam_id,
            steam_api_key=steam_api_key,
        )

        self._active_worker = worker

        worker.signals.result_ready.connect(self._apply_result)
        worker.signals.failed.connect(self.failed.emit)
        worker.signals.finished.connect(self._finished)

        self.thread_pool.start(worker)

        return True

    def _apply_result(
        self,
        source,
        game,
        _result,
    ):
        self.succeeded.emit(
            source,
            game,
        )

    def _finished(self):
        self._active_worker = None
        self._busy = False
        self.busy_changed.emit(False)


class EscapeClearsLineEdit(QLineEdit):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            event.accept()
            return

        super().keyPressEvent(event)


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

        self._selected_refresh_controller = SelectedGameRefreshController(self)
        self._selected_refresh_busy = False
        self._global_update_busy = False
        self.description_requests_in_flight = set()
        self._adjusting_columns = False
        self._preferred_column_widths = list(DEFAULT_LIBRARY_COLUMN_WIDTHS)
        self._column_save_timer = QTimer(self)
        self._column_save_timer.setSingleShot(True)
        self._column_save_timer.setInterval(250)
        self._column_save_timer.timeout.connect(self._save_library_view)

        self._create_filter_controls()
        self._create_table()
        self._create_details()

        self._create_layout()
        self._restore_library_view()
        self._connect_signals()
        self.apply_filters()

        QTimer.singleShot(0, self._apply_library_display_size)

    def _create_filter_controls(self):
        self.search_box = EscapeClearsLineEdit()
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
                "Test / Beta",
                "Unknown (Test / Beta)",
                "Unknown (Game)",
                "Software",
                "Unknown (Software)",
                "Unknown",
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
        self.hltb_min_filter.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        self.hltb_min_filter.setSpecialValueText("Min")
        self.hltb_min_filter.setSuffix(" h")

        self.hltb_max_filter = SelectAllDoubleSpinBox()

        self.hltb_max_filter.setRange(0, 10000)
        self.hltb_max_filter.setDecimals(1)
        self.hltb_max_filter.setSingleStep(0.5)
        self.hltb_max_filter.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
        self.hltb_max_filter.setSpecialValueText("Max")
        self.hltb_max_filter.setSuffix(" h")

        self.genre_tag_filter = GenreTagFilterWidget(self)
        self.genre_tag_filter.set_available_from_games(self.games)

        self.clear_genre_tag_button = QPushButton("Clear Genres / Tags")
        self.clear_genre_tag_button.setToolTip(
            "Clear only the selected Genre and Tag filters."
        )
        self.clear_genre_tag_button.setEnabled(
            self.genre_tag_filter.has_active_filters()
        )

        self.rating_filter = QComboBox()

        self.rating_filter.addItems(
            [
                "All Ratings",
                "Unrated",
                "★",
                "★★",
                "★★★",
                "★★★★",
                "★★★★★",
            ]
        )

        self.pick_button = QPushButton("Pick Something For Me")

        self.display_size_combo = QComboBox()
        self.display_size_combo.addItems(list(LIBRARY_DISPLAY_PRESETS))
        self.display_size_combo.setCurrentText(DEFAULT_LIBRARY_DISPLAY_SIZE)
        self.display_size_combo.setToolTip(
            "Adjust Library table rows and selected-game text for readability."
        )

        self.reset_columns_button = QPushButton("Reset Columns")
        self.reset_columns_button.setToolTip(
            "Restore the default Library column order, visibility, and widths. "
            "You can also drag headers to reorder them and right-click a header "
            "to show or hide columns."
        )

        self.help_faq_button = QPushButton("Help / FAQ")
        self.help_faq_button.setToolTip(
            "Open setup help and answers for common SteamLibraryData issues."
        )

        self.clear_filters_button = QPushButton("Clear Filters")
        self.clear_filters_button.setToolTip(
            "Clear search, standard filters, Genre / Tags, and Advanced Filters."
        )
        self.clear_filters_button.setEnabled(False)

        self.summary_label = QLabel("")
        self.summary_label.setProperty("summaryText", True)

        self.filter_chip_widget = QWidget()
        self.filter_chip_layout = QHBoxLayout(self.filter_chip_widget)
        self.filter_chip_layout.setContentsMargins(0, 0, 0, 0)
        self.filter_chip_layout.setSpacing(6)
        self.filter_chip_widget.setVisible(False)

        self.no_results_frame = QFrame()
        self.no_results_frame.setProperty("noResults", True)
        no_results_layout = QHBoxLayout(self.no_results_frame)
        no_results_layout.setContentsMargins(12, 8, 12, 8)
        self.no_results_label = QLabel("No games match the current filters.")
        self.no_results_clear_button = QPushButton("Clear Filters")
        no_results_layout.addWidget(self.no_results_label)
        no_results_layout.addStretch()
        no_results_layout.addWidget(self.no_results_clear_button)
        self.no_results_frame.setVisible(False)

        self.advanced_toggle_button = QPushButton("Advanced Filters ▸")
        self.advanced_toggle_button.setCheckable(True)

        self.advanced_clear_button = QPushButton("Clear Advanced")
        self.advanced_clear_button.setToolTip(
            "Clear only the filters inside Advanced Filters."
        )

        self.achievement_filter = QComboBox()
        self.achievement_filter.addItems(
            [
                "Any",
                "Has achievements",
                "No achievements",
                "100% unlocked",
                "At least % unlocked",
                "Remaining at most",
            ]
        )

        self.achievement_percent_label = QLabel("Percent:")
        self.achievement_percent_filter = QSpinBox()
        self.achievement_percent_filter.setRange(1, 100)
        self.achievement_percent_filter.setValue(75)
        self.achievement_percent_filter.setSuffix("%")

        self.achievement_remaining_label = QLabel("Remaining:")
        self.achievement_remaining_filter = QSpinBox()
        self.achievement_remaining_filter.setRange(0, 9999)
        self.achievement_remaining_filter.setValue(5)

        self.playtime_hltb_filter = QComboBox()
        self.playtime_hltb_filter.addItems(
            [
                "Any",
                "At least Main Story",
                "At least Main + Extra",
                "At least Completionist",
                "Custom % of Completionist",
            ]
        )
        self.playtime_hltb_filter.setToolTip(
            "Compare total Steam playtime against the selected HLTB time."
        )

        self.playtime_hltb_percent_label = QLabel("Completionist %:")
        self.playtime_hltb_percent_filter = QSpinBox()
        self.playtime_hltb_percent_filter.setRange(1, 500)
        self.playtime_hltb_percent_filter.setValue(80)
        self.playtime_hltb_percent_filter.setSuffix("%")

        self.last_played_filter = QComboBox()
        self.last_played_filter.addItems(
            [
                "Any",
                "Never",
                "Within 30 days",
                "Within 90 days",
                "Within 1 year",
                "More than 1 year ago",
            ]
        )

        self.data_completeness_filter = QComboBox()
        self.data_completeness_filter.addItems(
            [
                "Any",
                "All enrichment checked",
                "Missing any enrichment",
                "Missing HLTB",
                "Missing Genre / Tags",
                "Missing Achievements",
            ]
        )

    def _create_table(self):
        self.table = QTableView()
        self.game_table_model = GameTableModel(self.filtered_games, self)

        self.game_table_model.set_steam_type_resolver(
            self.genre_tag_filter.display_steam_type
        )

        self.game_table_model.set_ratings(load_game_ratings())

        self.table.setModel(self.game_table_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setSectionsClickable(True)
        header.setSectionsMovable(True)
        header.setSortIndicatorShown(False)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(70)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        for column, width in enumerate(DEFAULT_LIBRARY_COLUMN_WIDTHS):
            header.resizeSection(column, width)

        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.setToolTip(
            "Drag headers to reorder columns. Drag dividers to resize. "
            "Double-click a divider to auto-fit, or right-click for column options."
        )
        self.table.viewport().installEventFilter(self)
        header.sectionClicked.connect(self.sort_by_column)

    def _create_details(self):
        self.game_image = QLabel("Select a game")

        self.game_image.setMinimumSize(0, 0)
        self.game_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.game_title = QLabel("No game selected")

        self.game_title.setWordWrap(True)
        self.game_title.setStyleSheet("font-size: 15pt; font-weight: bold;")

        self.status_label = QLabel("Status:")

        self.status_value = BadgeLabel("NO GAME", tone="neutral")

        self.type_badge = BadgeLabel("", tone="neutral")
        self.type_badge.setVisible(False)

        self.reception_badge = BadgeLabel("", tone="neutral")
        self.reception_badge.setVisible(False)

        self.manual_status_combo = QComboBox()

        self.manual_status_combo.addItems(
            ["Automatic", "Completed", "On Hold", "Dropped"]
        )
        self.manual_status_combo.setEnabled(False)

        self.rating_label = QLabel("Your Rating:")

        self.rating_combo = QComboBox()
        self.rating_combo.addItems(
            [
                "Unrated",
                "★",
                "★★",
                "★★★",
                "★★★★",
                "★★★★★",
            ]
        )
        self.rating_combo.setEnabled(False)
        self.rating_combo.setToolTip("How much you personally enjoyed this game.")

        self.about_heading = SectionHeading("ABOUT")

        self.game_description = QLabel("")
        self.game_description.setWordWrap(True)
        self.game_description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.details_heading = SectionHeading("DETAILS")

        self.game_details = QLabel("")
        self.game_details.setWordWrap(True)
        self.game_details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.empty_details_label = QLabel("Select a game to view details")
        self.empty_details_label.setProperty("emptyState", True)
        self.empty_details_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.steam_page_button = QPushButton("Steam Page")
        self.hltb_page_button = QPushButton("HLTB Page")

        self.steam_page_button.setEnabled(False)
        self.hltb_page_button.setEnabled(False)
        self.hltb_page_button.setToolTip(
            "Open the accepted HowLongToBeat match for the selected game."
        )

        self.refresh_hltb_button = QPushButton("HLTB")
        self.refresh_metadata_button = QPushButton("Genre / Tags")
        self.refresh_achievements_button = QPushButton("Achievements")

        self.refresh_hltb_button.setToolTip(
            "Run a fresh HowLongToBeat lookup for the selected game."
        )
        self.refresh_metadata_button.setToolTip(
            "Refresh genre and tag data for the selected game."
        )
        self.refresh_achievements_button.setToolTip(
            "Refresh Steam achievement progress for the selected game."
        )

        self.selected_refresh_status = QLabel("")
        self.selected_refresh_status.setWordWrap(True)

        self.trailer_player = TrailerPlayer(self)

    def _create_layout(self):
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.pick_button)
        search_row.addSpacing(8)
        search_row.addWidget(QLabel("Display:"))
        search_row.addWidget(self.display_size_combo)
        search_row.addWidget(self.reset_columns_button)
        search_row.addWidget(self.help_faq_button)

        primary_filter_row = QHBoxLayout()
        primary_filter_row.addWidget(QLabel("Status:"))
        primary_filter_row.addWidget(self.status_filter)
        primary_filter_row.addWidget(QLabel("Type:"))
        primary_filter_row.addWidget(self.type_filter)
        primary_filter_row.addWidget(QLabel("HLTB Metric:"))
        primary_filter_row.addWidget(self.hltb_metric_filter)
        primary_filter_row.addWidget(QLabel("HLTB Hours:"))
        primary_filter_row.addWidget(self.hltb_min_filter)
        primary_filter_row.addWidget(QLabel("to"))
        primary_filter_row.addWidget(self.hltb_max_filter)
        primary_filter_row.addStretch()

        secondary_filter_row = QHBoxLayout()
        secondary_filter_row.addWidget(self.genre_tag_filter, 1)
        secondary_filter_row.addWidget(self.clear_genre_tag_button)
        secondary_filter_row.addSpacing(8)
        secondary_filter_row.addWidget(QLabel("Rating:"))
        secondary_filter_row.addWidget(self.rating_filter)
        secondary_filter_row.addStretch()

        summary_frame = QFrame()
        summary_frame.setProperty("summaryStrip", True)
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(12, 7, 12, 7)
        summary_layout.addWidget(self.summary_label, 1)
        summary_layout.addWidget(self.clear_filters_button)

        self.details_panel = QScrollArea()
        self.details_panel.setWidgetResizable(True)
        self.details_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.details_panel.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.details_panel.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.details_panel.setMinimumWidth(320)

        self.details_content = QWidget()
        self.details_content.setProperty("accentCard", True)
        details_layout = QVBoxLayout(self.details_content)
        details_layout.setContentsMargins(12, 12, 12, 12)
        details_layout.setSpacing(8)

        details_layout.addWidget(self.empty_details_label, 1)

        details_layout.addWidget(
            self.game_image,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        details_layout.addWidget(self.game_title)

        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.status_value)
        status_row.addWidget(self.type_badge)
        status_row.addWidget(self.reception_badge)
        status_row.addSpacing(8)
        status_row.addWidget(self.manual_status_combo)
        status_row.addStretch()
        details_layout.addLayout(status_row)

        rating_row = QHBoxLayout()
        rating_row.addWidget(self.rating_label)
        rating_row.addWidget(self.rating_combo)
        rating_row.addStretch()
        details_layout.addLayout(rating_row)

        details_layout.addWidget(self.about_heading)
        details_layout.addWidget(self.game_description)
        details_layout.addWidget(self.details_heading)
        details_layout.addWidget(self.game_details)

        self.refresh_selected_label = QLabel("Refresh selected:")
        details_layout.addWidget(self.refresh_selected_label)

        refresh_row = QHBoxLayout()
        refresh_row.addWidget(self.refresh_hltb_button)
        refresh_row.addWidget(self.refresh_metadata_button)
        refresh_row.addWidget(self.refresh_achievements_button)
        refresh_row.addStretch()
        details_layout.addLayout(refresh_row)
        details_layout.addWidget(self.selected_refresh_status)

        details_layout.addWidget(self.trailer_player)

        action_row = QHBoxLayout()
        action_row.addWidget(self.steam_page_button)
        action_row.addWidget(self.hltb_page_button)
        action_row.addStretch()
        details_layout.addLayout(action_row)
        details_layout.addStretch()

        self._game_detail_widgets = [
            self.game_image,
            self.game_title,
            self.status_label,
            self.status_value,
            self.type_badge,
            self.reception_badge,
            self.manual_status_combo,
            self.rating_label,
            self.rating_combo,
            self.about_heading,
            self.game_description,
            self.details_heading,
            self.game_details,
            self.refresh_selected_label,
            self.refresh_hltb_button,
            self.refresh_metadata_button,
            self.refresh_achievements_button,
            self.selected_refresh_status,
            self.trailer_player,
            self.steam_page_button,
            self.hltb_page_button,
        ]

        self._set_detail_content_visible(False)

        self.details_panel.setWidget(self.details_content)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.details_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([650, 450])

        advanced_header_row = QHBoxLayout()
        advanced_header_row.addWidget(self.advanced_toggle_button)
        advanced_header_row.addWidget(self.advanced_clear_button)
        advanced_header_row.addStretch()

        self.advanced_panel = QFrame()
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(12, 4, 12, 8)
        advanced_layout.setSpacing(6)

        achievement_row = QHBoxLayout()
        achievement_row.addWidget(QLabel("Achievements:"))
        achievement_row.addWidget(self.achievement_filter)
        achievement_row.addWidget(self.achievement_percent_label)
        achievement_row.addWidget(self.achievement_percent_filter)
        achievement_row.addWidget(self.achievement_remaining_label)
        achievement_row.addWidget(self.achievement_remaining_filter)
        achievement_row.addStretch()

        playtime_row = QHBoxLayout()
        playtime_row.addWidget(QLabel("Playtime vs HLTB:"))
        playtime_row.addWidget(self.playtime_hltb_filter)
        playtime_row.addWidget(self.playtime_hltb_percent_label)
        playtime_row.addWidget(self.playtime_hltb_percent_filter)
        playtime_row.addStretch()

        other_row = QHBoxLayout()
        other_row.addWidget(QLabel("Last played:"))
        other_row.addWidget(self.last_played_filter)
        other_row.addSpacing(12)
        other_row.addWidget(QLabel("Data completeness:"))
        other_row.addWidget(self.data_completeness_filter)
        other_row.addStretch()

        advanced_layout.addLayout(achievement_row)
        advanced_layout.addLayout(playtime_row)
        advanced_layout.addLayout(other_row)

        self.advanced_panel.setVisible(False)
        self._update_advanced_filter_controls()

        layout.addLayout(search_row)
        layout.addLayout(primary_filter_row)
        layout.addLayout(secondary_filter_row)
        layout.addWidget(summary_frame)
        layout.addWidget(self.filter_chip_widget)
        layout.addLayout(advanced_header_row)
        layout.addWidget(self.advanced_panel)
        layout.addWidget(self.no_results_frame)
        layout.addWidget(self.splitter, 1)

    def _connect_signals(self):
        self.search_box.textChanged.connect(self._search_changed)
        self.display_size_combo.currentTextChanged.connect(
            self._library_display_size_changed
        )

        self.status_filter.currentTextChanged.connect(self._library_filter_changed)
        self.type_filter.currentTextChanged.connect(self._library_filter_changed)
        self.hltb_metric_filter.currentTextChanged.connect(self._hltb_metric_changed)
        self.genre_tag_filter.filters_changed.connect(self._genre_tag_filters_changed)
        self.clear_genre_tag_button.clicked.connect(self.genre_tag_filter.clear_filters)
        self.clear_filters_button.clicked.connect(self.clear_filters)
        self.no_results_clear_button.clicked.connect(self.clear_filters)

        self.hltb_min_filter.valueChanged.connect(self.hltb_min_changed)
        self.hltb_max_filter.valueChanged.connect(self.hltb_max_changed)

        self.pick_button.clicked.connect(self.pick_random_game)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.show_selected_game()
        )
        self.manual_status_combo.currentTextChanged.connect(self.change_manual_status)
        self.rating_combo.currentIndexChanged.connect(self.change_game_rating)

        self.steam_page_button.clicked.connect(self.open_selected_steam_page)
        self.hltb_page_button.clicked.connect(self.open_selected_hltb_page)
        self.reset_columns_button.clicked.connect(self.reset_table_columns)

        self.refresh_hltb_button.clicked.connect(
            lambda: self._refresh_selected_game("hltb")
        )
        self.refresh_metadata_button.clicked.connect(
            lambda: self._refresh_selected_game("metadata")
        )
        self.refresh_achievements_button.clicked.connect(
            lambda: self._refresh_selected_game("achievements")
        )

        self._selected_refresh_controller.busy_changed.connect(
            self._selected_refresh_busy_changed
        )
        self._selected_refresh_controller.succeeded.connect(
            self._selected_refresh_succeeded
        )
        self._selected_refresh_controller.failed.connect(self._selected_refresh_failed)

        main_window = self.window()
        update_controller = getattr(
            main_window,
            "update_controller",
            None,
        )

        if update_controller is not None:
            update_controller.busy_changed.connect(self._global_update_busy_changed)

        self.splitter.splitterMoved.connect(self._splitter_moved)
        header = self.table.horizontalHeader()
        header.sectionResized.connect(self._table_column_resized)
        header.sectionMoved.connect(self._table_columns_changed)
        header.sectionHandleDoubleClicked.connect(self._auto_fit_column)
        header.customContextMenuRequested.connect(self._show_header_context_menu)
        self.rating_filter.currentTextChanged.connect(self._library_filter_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)

        self.find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        self.find_shortcut.activated.connect(self._focus_search)

        self.advanced_toggle_button.toggled.connect(self._advanced_expanded_changed)
        self.advanced_clear_button.clicked.connect(self.clear_advanced_filters)

        self.achievement_filter.currentTextChanged.connect(
            self._advanced_filter_changed
        )
        self.achievement_percent_filter.valueChanged.connect(
            self._advanced_filter_changed
        )
        self.achievement_remaining_filter.valueChanged.connect(
            self._advanced_filter_changed
        )
        self.playtime_hltb_filter.currentTextChanged.connect(
            self._advanced_filter_changed
        )
        self.playtime_hltb_percent_filter.valueChanged.connect(
            self._advanced_filter_changed
        )
        self.last_played_filter.currentTextChanged.connect(
            self._advanced_filter_changed
        )
        self.data_completeness_filter.currentTextChanged.connect(
            self._advanced_filter_changed
        )

        self._update_selected_refresh_enabled()

    def set_games(self, games):
        self.games = games

        self.genre_tag_filter.set_available_from_games(games)

        self.refresh_data()

    def refresh_data(self):
        selected_app_id = (
            self.selected_game.app_id if self.selected_game is not None else None
        )

        self.genre_tag_filter.set_available_from_games(self.games)
        self.apply_filters()

        if selected_app_id is None:
            return

        for row, game in enumerate(self.filtered_games):
            if game.app_id == selected_app_id:
                self.table.selectRow(row)

                return

        self.clear_game_details()

    def _show_table_context_menu(self, position):
        index = self.table.indexAt(position)

        if not index.isValid():
            return

        self.table.selectRow(index.row())
        game = self.game_table_model.game_at(index.row())

        if game is None:
            return

        menu = QMenu(self)
        open_action = menu.addAction("Open Steam Page")
        open_hltb_action = menu.addAction("Open HLTB Page")
        open_hltb_action.setEnabled(bool(getattr(game, "hltb_web_link", None)))
        menu.addSeparator()
        refresh_hltb_action = menu.addAction("Refresh HLTB")
        refresh_metadata_action = menu.addAction("Refresh Genre / Tags")
        refresh_achievements_action = menu.addAction("Refresh Achievements")

        refresh_hltb_action.setEnabled(
            self._selected_refresh_unavailable_reason("hltb") is None
        )
        refresh_metadata_action.setEnabled(
            self._selected_refresh_unavailable_reason("metadata") is None
        )
        refresh_achievements_action.setEnabled(
            self._selected_refresh_unavailable_reason("achievements") is None
        )

        action = menu.exec(self.table.viewport().mapToGlobal(position))

        if action == open_action:
            self.open_selected_steam_page()
        elif action == open_hltb_action:
            self.open_selected_hltb_page()
        elif action == refresh_hltb_action:
            self._refresh_selected_game("hltb")
        elif action == refresh_metadata_action:
            self._refresh_selected_game("metadata")
        elif action == refresh_achievements_action:
            self._refresh_selected_game("achievements")

    def current_hltb_time(self, game):
        metric = self.hltb_metric_filter.currentText()

        return game.hltb_time(metric)

    def _restore_library_view(self):
        settings = get_library_view_settings()

        display_size = settings.get("display_size", DEFAULT_LIBRARY_DISPLAY_SIZE)

        if display_size not in LIBRARY_DISPLAY_PRESETS:
            display_size = DEFAULT_LIBRARY_DISPLAY_SIZE

        self.display_size_combo.setCurrentText(display_size)

        combo_settings = [
            (self.status_filter, settings.get("status")),
            (self.type_filter, settings.get("type")),
            (self.hltb_metric_filter, settings.get("hltb_metric")),
        ]

        for combo, value in combo_settings:
            if not isinstance(value, str):
                continue

            index = combo.findText(value)

            if index >= 0:
                combo.setCurrentIndex(index)

        search_text = settings.get("search")

        if isinstance(search_text, str):
            self.search_box.setText(search_text)

        rating = settings.get("rating")

        if isinstance(rating, str):
            rating_index = self.rating_filter.findText(rating)

            if rating_index >= 0:
                self.rating_filter.setCurrentIndex(rating_index)

        self.genre_tag_filter.set_selected_filters(
            settings.get("game_genres", ()),
            settings.get("software_genres", ()),
            settings.get("tags", ()),
        )

        hltb_min = settings.get("hltb_min")
        hltb_max = settings.get("hltb_max")

        if isinstance(hltb_min, (int, float)):
            self.hltb_min_filter.setValue(hltb_min)

        if isinstance(hltb_max, (int, float)):
            self.hltb_max_filter.setValue(hltb_max)

        advanced = settings.get("advanced_filters")

        if isinstance(advanced, dict):
            combo_settings = [
                (
                    self.achievement_filter,
                    advanced.get("achievement_mode"),
                ),
                (
                    self.playtime_hltb_filter,
                    advanced.get("playtime_hltb_mode"),
                ),
                (
                    self.last_played_filter,
                    advanced.get("last_played_mode"),
                ),
                (
                    self.data_completeness_filter,
                    advanced.get("data_completeness_mode"),
                ),
            ]

            for combo, value in combo_settings:
                if not isinstance(value, str):
                    continue

                index = combo.findText(value)

                if index >= 0:
                    combo.setCurrentIndex(index)

            achievement_percent = advanced.get("achievement_percent")
            achievement_remaining = advanced.get("achievement_remaining")
            playtime_hltb_percent = advanced.get("playtime_hltb_percent")

            if isinstance(achievement_percent, int):
                self.achievement_percent_filter.setValue(achievement_percent)

            if isinstance(achievement_remaining, int):
                self.achievement_remaining_filter.setValue(achievement_remaining)

            if isinstance(playtime_hltb_percent, int):
                self.playtime_hltb_percent_filter.setValue(playtime_hltb_percent)

            expanded = advanced.get("expanded") is True
            self.advanced_toggle_button.setChecked(expanded)
            self.advanced_panel.setVisible(expanded)
            self.advanced_toggle_button.setText(
                "Advanced Filters ▾" if expanded else "Advanced Filters ▸"
            )

        self._update_advanced_filter_controls()
        self._apply_library_display_size()

        sort_column = settings.get("sort_column")

        if (
            isinstance(sort_column, int)
            and 0 <= sort_column < self.game_table_model.columnCount()
        ):
            self.header_sort_column = sort_column

            if settings.get("sort_order") == "descending":
                self.header_sort_order = Qt.SortOrder.DescendingOrder
            else:
                self.header_sort_order = Qt.SortOrder.AscendingOrder

            header = self.table.horizontalHeader()
            header.setSortIndicatorShown(True)
            header.setSortIndicator(
                self.header_sort_column,
                self.header_sort_order,
            )
            self.game_table_model.set_sort_column(self.header_sort_column)

        self._restore_table_columns(settings)

        splitter_sizes = settings.get("splitter_sizes")

        if (
            isinstance(splitter_sizes, list)
            and len(splitter_sizes) == 2
            and all(isinstance(size, int) and size > 0 for size in splitter_sizes)
        ):
            self.splitter.setSizes(splitter_sizes)

    def _save_library_view(self):
        set_library_view_settings(
            {
                "display_size": self.display_size_combo.currentText(),
                "search": self.search_box.text(),
                "status": self.status_filter.currentText(),
                "type": self.type_filter.currentText(),
                "rating": self.rating_filter.currentText(),
                "hltb_metric": self.hltb_metric_filter.currentText(),
                "hltb_min": self.hltb_min_filter.value(),
                "hltb_max": self.hltb_max_filter.value(),
                "game_genres": list(self.genre_tag_filter.selected_game_genres()),
                "software_genres": list(
                    self.genre_tag_filter.selected_software_genres()
                ),
                "tags": list(self.genre_tag_filter.selected_tags()),
                "advanced_filters": {
                    "expanded": self.advanced_toggle_button.isChecked(),
                    "achievement_mode": self.achievement_filter.currentText(),
                    "achievement_percent": self.achievement_percent_filter.value(),
                    "achievement_remaining": (
                        self.achievement_remaining_filter.value()
                    ),
                    "playtime_hltb_mode": self.playtime_hltb_filter.currentText(),
                    "playtime_hltb_percent": (
                        self.playtime_hltb_percent_filter.value()
                    ),
                    "last_played_mode": self.last_played_filter.currentText(),
                    "data_completeness_mode": (
                        self.data_completeness_filter.currentText()
                    ),
                },
                "sort_column": self.header_sort_column,
                "sort_order": (
                    "descending"
                    if self.header_sort_order == Qt.SortOrder.DescendingOrder
                    else "ascending"
                ),
                "splitter_sizes": self.splitter.sizes(),
                "column_widths": list(self._preferred_column_widths),
                "column_order": [
                    self.table.horizontalHeader().logicalIndex(visual_index)
                    for visual_index in range(self.game_table_model.columnCount())
                ],
                "hidden_columns": [
                    column
                    for column in range(self.game_table_model.columnCount())
                    if self.table.isColumnHidden(column)
                ],
            }
        )

    def _restore_table_columns(self, settings):
        header = self.table.horizontalHeader()
        column_count = self.game_table_model.columnCount()
        widths = settings.get("column_widths")

        if (
            isinstance(widths, list)
            and len(widths) == column_count
            and all(isinstance(width, int) and width >= 70 for width in widths)
        ):
            self._preferred_column_widths = list(widths)
        else:
            self._preferred_column_widths = list(DEFAULT_LIBRARY_COLUMN_WIDTHS)

        order = settings.get("column_order")
        hidden_columns = settings.get("hidden_columns", [])

        self._adjusting_columns = True
        header.blockSignals(True)

        try:
            for column, width in enumerate(self._preferred_column_widths):
                header.resizeSection(column, width)

            if (
                isinstance(order, list)
                and len(order) == column_count
                and sorted(order) == list(range(column_count))
            ):
                for target_visual_index, logical_index in enumerate(order):
                    current_visual_index = header.visualIndex(logical_index)

                    if current_visual_index != target_visual_index:
                        header.moveSection(current_visual_index, target_visual_index)

            hidden_set = {
                column
                for column in hidden_columns
                if isinstance(column, int) and 0 < column < column_count
            }

            for column in range(column_count):
                self.table.setColumnHidden(column, column in hidden_set)
        finally:
            header.blockSignals(False)
            self._adjusting_columns = False

        QTimer.singleShot(0, self._fit_table_columns)

    def eventFilter(self, watched, event):
        if watched is self.table.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._fit_table_columns)

        return super().eventFilter(watched, event)

    def _fit_table_columns(self):
        if self._adjusting_columns:
            return

        column_count = self.game_table_model.columnCount()
        visible_columns = [
            column
            for column in range(column_count)
            if not self.table.isColumnHidden(column)
        ]

        if not visible_columns:
            return

        available_width = self.table.viewport().width()

        if available_width <= 0:
            return

        preferred = {
            column: max(self._preferred_column_widths[column], 70)
            for column in visible_columns
        }
        preferred_total = sum(preferred.values())
        filler_column = 0 if 0 in visible_columns else visible_columns[0]
        target_widths = dict(preferred)

        if preferred_total < available_width:
            target_widths[filler_column] += available_width - preferred_total

        header = self.table.horizontalHeader()
        self._adjusting_columns = True

        try:
            for column, width in target_widths.items():
                if header.sectionSize(column) != width:
                    header.resizeSection(column, width)
        finally:
            self._adjusting_columns = False

    def _table_column_resized(self, logical_index, _old_size, new_size):
        if self._adjusting_columns:
            return

        if 0 <= logical_index < len(self._preferred_column_widths):
            self._preferred_column_widths[logical_index] = max(int(new_size), 70)

        self._column_save_timer.start()
        QTimer.singleShot(0, self._fit_table_columns)

    def _table_columns_changed(self, *_):
        if self._adjusting_columns:
            return

        self._column_save_timer.start()
        QTimer.singleShot(0, self._fit_table_columns)

    def _auto_fit_column(self, logical_index):
        if not 0 <= logical_index < self.game_table_model.columnCount():
            return

        self.table.resizeColumnToContents(logical_index)
        width = max(self.table.horizontalHeader().sectionSize(logical_index), 70)
        self._preferred_column_widths[logical_index] = width
        self._save_library_view()
        self._fit_table_columns()

    def _show_header_context_menu(self, position):
        header = self.table.horizontalHeader()
        logical_index = header.logicalIndexAt(position)
        menu = QMenu(self)
        auto_fit_action = None

        if logical_index >= 0:
            label = self.game_table_model.headerData(
                logical_index,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.DisplayRole,
            )
            auto_fit_action = menu.addAction(f"Auto-fit {label}")
            menu.addSeparator()

        visibility_actions = {}

        for column in range(self.game_table_model.columnCount()):
            label = self.game_table_model.headerData(
                column,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.DisplayRole,
            )
            action = menu.addAction(str(label))
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(column))

            if column == 0:
                action.setEnabled(False)
                action.setToolTip("The Game column is always shown.")

            visibility_actions[action] = column

        menu.addSeparator()
        reset_action = menu.addAction("Reset Columns")
        selected_action = menu.exec(header.viewport().mapToGlobal(position))

        if selected_action is None:
            return

        if selected_action == auto_fit_action and logical_index >= 0:
            self._auto_fit_column(logical_index)
            return

        if selected_action == reset_action:
            self.reset_table_columns()
            return

        column = visibility_actions.get(selected_action)

        if column is None or column == 0:
            return

        self.table.setColumnHidden(column, not selected_action.isChecked())
        self._save_library_view()
        self._fit_table_columns()

    def reset_table_columns(self):
        header = self.table.horizontalHeader()
        self._preferred_column_widths = list(DEFAULT_LIBRARY_COLUMN_WIDTHS)
        self._adjusting_columns = True
        header.blockSignals(True)

        try:
            for column in range(self.game_table_model.columnCount()):
                self.table.setColumnHidden(column, False)

            for logical_index in range(self.game_table_model.columnCount()):
                current_visual_index = header.visualIndex(logical_index)

                if current_visual_index != logical_index:
                    header.moveSection(current_visual_index, logical_index)

            for column, width in enumerate(self._preferred_column_widths):
                header.resizeSection(column, width)
        finally:
            header.blockSignals(False)
            self._adjusting_columns = False

        self._fit_table_columns()
        self._save_library_view()

    def _library_display_size_changed(self, *_):
        self._apply_library_display_size()
        self._save_library_view()

    def _apply_library_display_size(self):
        display_size = self.display_size_combo.currentText()
        preset = LIBRARY_DISPLAY_PRESETS.get(
            display_size,
            LIBRARY_DISPLAY_PRESETS[DEFAULT_LIBRARY_DISPLAY_SIZE],
        )

        library_font = self.font()
        library_font.setPointSize(preset["detail_font"])
        self.setFont(library_font)

        table_font = self.table.font()
        table_font.setPointSize(preset["table_font"])
        self.table.setFont(table_font)

        header = self.table.horizontalHeader()
        header_font = header.font()
        header_font.setPointSize(preset["header_font"])
        header.setFont(header_font)
        self.game_table_model.set_header_font_point_size(preset["header_font"])

        vertical_header = self.table.verticalHeader()
        vertical_header.setMinimumSectionSize(preset["row_height"])
        vertical_header.setDefaultSectionSize(preset["row_height"])

        self.update_media_sizes()

    def _focus_search(self):
        self.search_box.setFocus()
        self.search_box.selectAll()

    def _search_changed(self, *_):
        self.apply_filters()
        self._save_library_view()

    def _splitter_moved(self, *_):
        self.update_media_sizes()
        self._fit_table_columns()
        self._save_library_view()

    def _library_filter_changed(self):
        self.apply_filters()
        self._save_library_view()

    def _genre_tag_filters_changed(self):
        self.clear_genre_tag_button.setEnabled(
            self.genre_tag_filter.has_active_filters()
        )
        self.apply_filters()
        self._save_library_view()

    def _hltb_metric_changed(self, *_):
        self._library_filter_changed()

        if self.selected_game is not None:
            self._update_game_details_text(self.selected_game)

    def clear_filters(self):
        controls = [
            self.search_box,
            self.status_filter,
            self.type_filter,
            self.rating_filter,
            self.hltb_metric_filter,
            self.hltb_min_filter,
            self.hltb_max_filter,
            self.achievement_filter,
            self.achievement_percent_filter,
            self.achievement_remaining_filter,
            self.playtime_hltb_filter,
            self.playtime_hltb_percent_filter,
            self.last_played_filter,
            self.data_completeness_filter,
            self.genre_tag_filter,
        ]

        for control in controls:
            control.blockSignals(True)

        try:
            self.search_box.clear()
            self.status_filter.setCurrentText("All")
            self.type_filter.setCurrentText("All Types")
            self.rating_filter.setCurrentText("All Ratings")
            self.hltb_metric_filter.setCurrentText("Main Story")
            self.hltb_min_filter.setValue(0)
            self.hltb_max_filter.setValue(0)
            self.achievement_filter.setCurrentText("Any")
            self.achievement_percent_filter.setValue(75)
            self.achievement_remaining_filter.setValue(5)
            self.playtime_hltb_filter.setCurrentText("Any")
            self.playtime_hltb_percent_filter.setValue(80)
            self.last_played_filter.setCurrentText("Any")
            self.data_completeness_filter.setCurrentText("Any")
            self.genre_tag_filter.clear_filters()
        finally:
            for control in controls:
                control.blockSignals(False)

        self.clear_genre_tag_button.setEnabled(False)
        self._update_advanced_filter_controls()
        self.apply_filters()
        self._save_library_view()

    def _clear_hltb_range(self):
        self.hltb_min_filter.setValue(0)
        self.hltb_max_filter.setValue(0)

    def _clear_advanced_mode(self, control):
        control.setCurrentText("Any")

    def _active_filter_specs(self):
        specs = []
        search_text = self.search_box.text().strip()

        if search_text:
            specs.append(
                (
                    f'Search: "{search_text}"',
                    lambda checked=False: self.search_box.clear(),
                )
            )

        status = self.status_filter.currentText()

        if status != "All":
            specs.append(
                (
                    f"Status: {status}",
                    lambda checked=False: self.status_filter.setCurrentText("All"),
                )
            )

        steam_type = self.type_filter.currentText()

        if steam_type != "All Types":
            specs.append(
                (
                    f"Type: {steam_type}",
                    lambda checked=False: self.type_filter.setCurrentText("All Types"),
                )
            )

        min_hours = self.hltb_min_filter.value()
        max_hours = self.hltb_max_filter.value()

        if min_hours > 0 or max_hours > 0:
            lower = f"{min_hours:g}h" if min_hours > 0 else "Min"
            upper = f"{max_hours:g}h" if max_hours > 0 else "Max"
            metric = self.hltb_metric_filter.currentText()
            specs.append(
                (
                    f"HLTB {metric}: {lower}–{upper}",
                    lambda checked=False: self._clear_hltb_range(),
                )
            )

        for genre in self.genre_tag_filter.selected_game_genres():
            specs.append(
                (
                    f"Genre: {genre}",
                    lambda checked=False, value=genre: (
                        self.genre_tag_filter.remove_filter("game_genre", value)
                    ),
                )
            )

        for genre in self.genre_tag_filter.selected_software_genres():
            specs.append(
                (
                    f"Software genre: {genre}",
                    lambda checked=False, value=genre: (
                        self.genre_tag_filter.remove_filter("software_genre", value)
                    ),
                )
            )

        for tag in self.genre_tag_filter.selected_tags():
            specs.append(
                (
                    f"Tag: {tag}",
                    lambda checked=False, value=tag: (
                        self.genre_tag_filter.remove_filter("tag", value)
                    ),
                )
            )

        rating = self.rating_filter.currentText()

        if rating != "All Ratings":
            specs.append(
                (
                    f"Rating: {rating}",
                    lambda checked=False: self.rating_filter.setCurrentText(
                        "All Ratings"
                    ),
                )
            )

        achievement_mode = self.achievement_filter.currentText()

        if achievement_mode != "Any":
            achievement_value = achievement_mode

            if achievement_mode == "At least % unlocked":
                achievement_value = (
                    f"At least {self.achievement_percent_filter.value()}% unlocked"
                )
            elif achievement_mode == "Remaining at most":
                achievement_value = (
                    f"{self.achievement_remaining_filter.value()} remaining at most"
                )

            specs.append(
                (
                    f"Achievements: {achievement_value}",
                    lambda checked=False: self._clear_advanced_mode(
                        self.achievement_filter
                    ),
                )
            )

        playtime_mode = self.playtime_hltb_filter.currentText()

        if playtime_mode != "Any":
            playtime_value = playtime_mode

            if playtime_mode == "Custom % of Completionist":
                playtime_value = (
                    f"{self.playtime_hltb_percent_filter.value()}% of Completionist"
                )

            specs.append(
                (
                    f"Playtime vs HLTB: {playtime_value}",
                    lambda checked=False: self._clear_advanced_mode(
                        self.playtime_hltb_filter
                    ),
                )
            )

        last_played = self.last_played_filter.currentText()

        if last_played != "Any":
            specs.append(
                (
                    f"Last played: {last_played}",
                    lambda checked=False: self._clear_advanced_mode(
                        self.last_played_filter
                    ),
                )
            )

        data_mode = self.data_completeness_filter.currentText()

        if data_mode != "Any":
            specs.append(
                (
                    f"Data: {data_mode}",
                    lambda checked=False: self._clear_advanced_mode(
                        self.data_completeness_filter
                    ),
                )
            )

        return specs

    def _update_filter_summary(self):
        specs = self._active_filter_specs()

        while self.filter_chip_layout.count():
            item = self.filter_chip_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        visible_specs = specs[:4]

        for label, callback in visible_specs:
            display_label = label if len(label) <= 32 else f"{label[:29]}…"
            chip = QPushButton(f"{display_label}  ×")
            chip.setProperty("filterChip", True)
            chip.setToolTip(f"{label}\nClick to remove this filter.")
            chip.clicked.connect(callback)
            self.filter_chip_layout.addWidget(chip)

        hidden_count = len(specs) - len(visible_specs)

        if hidden_count > 0:
            more_label = QLabel(f"+{hidden_count} more")
            more_label.setProperty("context", "muted")
            self.filter_chip_layout.addWidget(more_label)

        if specs:
            self.filter_chip_layout.addStretch()

        self.filter_chip_widget.setVisible(bool(specs))
        self.clear_filters_button.setEnabled(bool(specs))

        total = len(self.games)
        backlog = sum(
            1
            for game in self.games
            if game.effective_status() == "Backlog"
            and self.genre_tag_filter.is_backlog_eligible(game)
        )
        completed = sum(
            1 for game in self.games if game.effective_status() == "Completed"
        )
        shown = len(self.filtered_games)

        summary = (
            f"{total:,} total  •  {backlog:,} backlog  •  "
            f"{completed:,} completed  •  {shown:,} shown"
        )

        if specs:
            summary += f"  •  {len(specs)} filters active"

        self.summary_label.setText(summary)

        has_no_results = not self.filtered_games
        self.no_results_frame.setVisible(has_no_results)

        if not self.games:
            self.no_results_label.setText(
                "The library is empty. Use Maintenance > Refresh Steam Library "
                "to import your Steam games."
            )
            self.no_results_clear_button.setVisible(False)
        elif has_no_results:
            self.no_results_label.setText(
                "No games match the current filters."
                if specs
                else "No games are available in the current library."
            )
            self.no_results_clear_button.setVisible(bool(specs))
        else:
            self.no_results_clear_button.setVisible(False)

    def _advanced_expanded_changed(self, expanded):
        self.advanced_panel.setVisible(expanded)
        self.advanced_toggle_button.setText(
            "Advanced Filters ▾" if expanded else "Advanced Filters ▸"
        )
        self._save_library_view()

    def _advanced_filter_changed(self, *_):
        self._update_advanced_filter_controls()
        self.apply_filters()
        self._save_library_view()

    def _update_advanced_filter_controls(self):
        achievement_mode = self.achievement_filter.currentText()
        uses_percent = achievement_mode == "At least % unlocked"
        uses_remaining = achievement_mode == "Remaining at most"

        self.achievement_percent_label.setEnabled(uses_percent)
        self.achievement_percent_filter.setEnabled(uses_percent)
        self.achievement_remaining_label.setEnabled(uses_remaining)
        self.achievement_remaining_filter.setEnabled(uses_remaining)

        custom_hltb = (
            self.playtime_hltb_filter.currentText() == "Custom % of Completionist"
        )

        self.playtime_hltb_percent_label.setEnabled(custom_hltb)
        self.playtime_hltb_percent_filter.setEnabled(custom_hltb)

        advanced_active = any(
            combo.currentText() != "Any"
            for combo in (
                self.achievement_filter,
                self.playtime_hltb_filter,
                self.last_played_filter,
                self.data_completeness_filter,
            )
        )
        self.advanced_clear_button.setEnabled(advanced_active)

    def clear_advanced_filters(self):
        controls = [
            self.achievement_filter,
            self.achievement_percent_filter,
            self.achievement_remaining_filter,
            self.playtime_hltb_filter,
            self.playtime_hltb_percent_filter,
            self.last_played_filter,
            self.data_completeness_filter,
        ]

        for control in controls:
            control.blockSignals(True)

        try:
            self.achievement_filter.setCurrentText("Any")
            self.achievement_percent_filter.setValue(75)
            self.achievement_remaining_filter.setValue(5)
            self.playtime_hltb_filter.setCurrentText("Any")
            self.playtime_hltb_percent_filter.setValue(80)
            self.last_played_filter.setCurrentText("Any")
            self.data_completeness_filter.setCurrentText("Any")
        finally:
            for control in controls:
                control.blockSignals(False)

        self._update_advanced_filter_controls()
        self.apply_filters()
        self._save_library_view()

    def _matches_achievement_filter(self, game):
        mode = self.achievement_filter.currentText()

        if mode == "Any":
            return True

        if not game.achievements_checked:
            return False

        total = game.achievement_total
        unlocked = game.achievements_unlocked

        if total is None or unlocked is None:
            return False

        if mode == "Has achievements":
            return total > 0

        if mode == "No achievements":
            return total == 0

        if mode == "100% unlocked":
            return total > 0 and unlocked >= total

        if mode == "At least % unlocked":
            if total <= 0:
                return False

            percent = (unlocked / total) * 100
            return percent >= self.achievement_percent_filter.value()

        if mode == "Remaining at most":
            if total <= 0:
                return False

            remaining = max(total - unlocked, 0)
            return remaining <= self.achievement_remaining_filter.value()

        return True

    def _matches_playtime_hltb_filter(self, game):
        mode = self.playtime_hltb_filter.currentText()

        if mode == "Any":
            return True

        playtime_hours = (game.playtime_minutes or 0) / 60

        if mode == "At least Main Story":
            target = game.hltb_main

        elif mode == "At least Main + Extra":
            target = game.hltb_main_extra

        elif mode == "At least Completionist":
            target = game.hltb_completionist

        elif mode == "Custom % of Completionist":
            completionist = game.hltb_completionist

            if completionist is None or completionist <= 0:
                return False

            target = completionist * (self.playtime_hltb_percent_filter.value() / 100)

        else:
            return True

        if target is None or target <= 0:
            return False

        return playtime_hours >= target

    def _matches_last_played_filter(self, game, now):
        mode = self.last_played_filter.currentText()

        if mode == "Any":
            return True

        timestamp = game.last_played_timestamp or 0

        if mode == "Never":
            return timestamp <= 0

        if timestamp <= 0:
            return False

        day = 24 * 60 * 60

        if mode == "Within 30 days":
            return timestamp >= now - (30 * day)

        if mode == "Within 90 days":
            return timestamp >= now - (90 * day)

        if mode == "Within 1 year":
            return timestamp >= now - (365 * day)

        if mode == "More than 1 year ago":
            return timestamp < now - (365 * day)

        return True

    def _matches_data_completeness_filter(self, game):
        mode = self.data_completeness_filter.currentText()

        if mode == "Any":
            return True

        all_checked = (
            game.hltb_checked and game.metadata_checked and game.achievements_checked
        )

        if mode == "All enrichment checked":
            return all_checked

        if mode == "Missing any enrichment":
            return not all_checked

        if mode == "Missing HLTB":
            return not game.hltb_checked

        if mode == "Missing Genre / Tags":
            return not game.metadata_checked

        if mode == "Missing Achievements":
            return not game.achievements_checked

        return True

    def _matches_advanced_filters(self, game, now):
        return (
            self._matches_achievement_filter(game)
            and self._matches_playtime_hltb_filter(game)
            and self._matches_last_played_filter(game, now)
            and self._matches_data_completeness_filter(game)
        )

    def hltb_min_changed(self, min_hours):
        max_hours = self.hltb_max_filter.value()

        if min_hours > 0 and max_hours > 0 and min_hours > max_hours:
            self.hltb_max_filter.setValue(min_hours)

        self.apply_filters()
        self._save_library_view()

    def hltb_max_changed(self, max_hours):
        min_hours = self.hltb_min_filter.value()

        if max_hours > 0 and min_hours > 0 and max_hours < min_hours:
            self.hltb_min_filter.setValue(max_hours)

        self.apply_filters()
        self._save_library_view()

    def apply_filters(self):
        selected_app_id = (
            self.selected_game.app_id if self.selected_game is not None else None
        )
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
                if game.effective_status() == "Backlog"
                and self.genre_tag_filter.is_backlog_eligible(game)
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
                game
                for game in filtered_games
                if self.genre_tag_filter.is_backlog_eligible(game)
            ]

        elif selected_type != "All Types":
            filtered_games = [
                game
                for game in filtered_games
                if self.genre_tag_filter.matches_type_filter(
                    game,
                    selected_type,
                )
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

        # 4. GENRE / TAG FILTER
        if self.genre_tag_filter.has_active_filters():
            filtered_games = [
                game
                for game in filtered_games
                if self.genre_tag_filter.matches_game(game)
            ]
        # 5. RATING FILTER
        selected_rating = self.rating_filter.currentText()

        if selected_rating != "All Ratings":
            ratings = load_game_ratings()

            if selected_rating == "Unrated":
                filtered_games = [
                    game for game in filtered_games if game.app_id not in ratings
                ]

            else:
                rating_value = len(selected_rating)

                filtered_games = [
                    game
                    for game in filtered_games
                    if ratings.get(game.app_id) == rating_value
                ]

        # 6. ADVANCED FILTERS
        now = time.time()

        filtered_games = [
            game for game in filtered_games if self._matches_advanced_filters(game, now)
        ]

        # 7. SEARCH
        search_text = self.search_box.text().strip().lower()

        if search_text:
            filtered_games = [
                game for game in filtered_games if search_text in game.name.lower()
            ]

        # 8. SORT
        if self.header_sort_column is not None:
            filtered_games = self.sort_games_by_column(filtered_games)
        else:
            filtered_games = sorted(
                filtered_games,
                key=lambda game: game.name.lower(),
            )

        # 9. PUSH RESULT INTO TABLE
        self.filtered_games = filtered_games
        self.game_table_model.set_games(filtered_games)
        self._update_filter_summary()

        if selected_app_id is None:
            return

        for row, game in enumerate(filtered_games):
            if game.app_id == selected_app_id:
                self.table.selectRow(row)
                return

        self.table.clearSelection()
        self.clear_game_details()

    def _set_detail_content_visible(self, visible):
        self.empty_details_label.setVisible(not visible)

        for widget in self._game_detail_widgets:
            widget.setVisible(visible)

    @staticmethod
    def _status_tone(status):
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
    def _refresh_age_text(timestamp):
        if not timestamp:
            return "Never"

        age_seconds = max(int(time.time()) - int(timestamp), 0)

        if age_seconds < 60:
            return "Just now"

        if age_seconds < 60 * 60:
            minutes = age_seconds // 60
            return f"{minutes}m ago"

        if age_seconds < 24 * 60 * 60:
            hours = age_seconds // (60 * 60)
            return f"{hours}h ago"

        if age_seconds < 7 * 24 * 60 * 60:
            days = age_seconds // (24 * 60 * 60)
            return f"{days}d ago"

        return (
            datetime.fromtimestamp(timestamp, tz=UTC).astimezone().strftime("%b %d, %Y")
        )

    @staticmethod
    def _description_text(game):
        description = game.steam_short_description

        if description is None:
            return "Loading Steam description..."

        if not description:
            return "No Steam description is available."

        return description

    def _request_short_description(self, game):
        if game.steam_short_description is not None:
            return

        if game.app_id in self.description_requests_in_flight:
            return

        self.description_requests_in_flight.add(game.app_id)

        worker = StoreDescriptionWorker(game.app_id)
        worker.signals.loaded.connect(self._short_description_loaded)
        worker.signals.failed.connect(self._short_description_failed)
        QThreadPool.globalInstance().start(worker)

    def _short_description_loaded(self, app_id, description):
        self.description_requests_in_flight.discard(app_id)

        game = next((item for item in self.games if item.app_id == app_id), None)

        if game is None:
            return

        game.steam_short_description = description

        if self.selected_game is not None and self.selected_game.app_id == app_id:
            self._update_game_details_text(game)

    def _short_description_failed(self, app_id, _error_message):
        self.description_requests_in_flight.discard(app_id)

    def _update_game_details_text(self, game):
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
        last_played_timestamp = game.last_played_timestamp or 0

        if last_played_timestamp > 0:
            last_played_text = (
                datetime.fromtimestamp(last_played_timestamp, tz=UTC)
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

        steam_type_text = self.genre_tag_filter.display_steam_type(game)
        reception_text = self._public_reception_text(game)
        description_text = self._description_text(game)

        self.game_description.setText(description_text)

        refresh_text = (
            f"HLTB {self._refresh_age_text(game.hltb_updated_at)}"
            f" • Genre / Tags {self._refresh_age_text(game.metadata_updated_at)}"
            f" • Achievements {self._refresh_age_text(game.achievements_updated_at)}"
        )

        self.game_details.setText(
            f"Last played: {last_played_text}\n"
            f"Last 2 weeks: {recent_activity_text}\n\n"
            f"Steam Playtime: {playtime_hours:.1f} hours\n"
            f"Steam Type: {steam_type_text}\n"
            f"Public Reception: {reception_text}\n"
            f"HLTB ({hltb_metric}): {hltb_text}\n"
            f"Achievements: {achievement_text}\n"
            f"Data refreshed: {refresh_text}\n\n"
            f"Genres: {genres}\n\n"
            f"Tags: {tags}"
        )

    def show_selected_game(self):
        row = self.table.currentIndex().row()

        if row < 0:
            return

        game = self.game_table_model.game_at(row)

        if game is None:
            return

        self.details_panel.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self._set_detail_content_visible(True)
        self.trailer_player.set_game(game.app_id)
        self.game_title.setText(game.name)
        self.game_title.setToolTip(game.name)
        self.selected_game = game

        status = game.effective_status()
        self.status_value.set_badge(status.upper(), self._status_tone(status))

        steam_type = self.genre_tag_filter.display_steam_type(game)
        self.type_badge.set_badge(steam_type.upper(), "neutral")
        self.type_badge.setVisible(True)

        reception_badge, reception_tone = self._reception_badge(game)
        self.reception_badge.set_badge(
            reception_badge,
            reception_tone,
            self._public_reception_text(game),
        )
        self.reception_badge.setVisible(True)

        self.manual_status_combo.blockSignals(True)

        if game.manual_status is None:
            self.manual_status_combo.setCurrentText("Automatic")
        else:
            self.manual_status_combo.setCurrentText(game.manual_status)

        self.manual_status_combo.setEnabled(True)
        self.manual_status_combo.blockSignals(False)

        rating = get_game_rating(game.app_id)

        self.rating_combo.blockSignals(True)
        self.rating_combo.setCurrentIndex(rating if rating is not None else 0)
        self.rating_combo.setEnabled(True)
        self.rating_combo.blockSignals(False)

        self._update_game_details_text(game)
        self._request_short_description(game)

        self.steam_page_button.setEnabled(True)
        self.hltb_page_button.setEnabled(bool(getattr(game, "hltb_web_link", None)))
        self._set_selected_refresh_status("")
        self._set_detail_content_visible(True)
        self._update_selected_refresh_enabled()

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
        if not self.filtered_games:
            QMessageBox.information(
                self,
                "No Games",
                "No games match the current filters.",
            )

            return

        game = random.choice(self.filtered_games)

        for row, filtered_game in enumerate(self.filtered_games):
            if filtered_game.app_id != game.app_id:
                continue

            index = self.game_table_model.index(
                row,
                0,
            )

            self.table.selectRow(row)

            self.table.scrollTo(
                index,
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )

            self.table.setFocus()

            return

    def change_manual_status(self, selected_status):
        if self.selected_game is None:
            return

        game = self.selected_game

        if selected_status == "Automatic":
            game.manual_status = None
        else:
            game.manual_status = selected_status

        save_manual_status(game)
        status = game.effective_status()
        self.status_value.set_badge(status.upper(), self._status_tone(status))
        self.refresh_data()

        self.data_changed.emit()

    def change_game_rating(self, rating_index):
        if self.selected_game is None:
            return

        if rating_index == 0:
            clear_game_rating(self.selected_game.app_id)
        else:
            set_game_rating(
                self.selected_game.app_id,
                rating_index,
            )

        self.refresh_ratings()
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
        accept_button.setProperty("role", "primary")
        accept_button.setToolTip("Use the selected HLTB entry for this Steam game.")

        skip_button = QPushButton("Skip")
        skip_button.setToolTip(
            "Leave this game pending and continue to the next review item."
        )

        no_match_button = QPushButton("No Match")
        no_match_button.setProperty("role", "warning")
        no_match_button.setToolTip(
            "Mark this game as checked with no usable HLTB match."
        )

        close_button = QPushButton("Close Review")
        close_button.setToolTip(
            "Stop reviewing. Remaining games stay pending for later."
        )

        button_row.addWidget(accept_button)
        button_row.addWidget(skip_button)
        button_row.addWidget(no_match_button)
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

            accept_hltb_candidate(game, candidate)

            result["action"] = "accept"

            dialog.accept()

        def mark_no_match():
            set_hltb_no_match(game)

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

    def _set_selected_refresh_status(self, text, tone=None):
        self.selected_refresh_status.setText(text)
        self.selected_refresh_status.setProperty("status", tone or "")
        style = self.selected_refresh_status.style()

        if style is not None:
            style.unpolish(self.selected_refresh_status)
            style.polish(self.selected_refresh_status)

        self.selected_refresh_status.update()

    def _main_window(self):
        return self.window()

    def _selected_refresh_unavailable_reason(self, source):
        if self.selected_game is None:
            return "Select a game first."

        if self._global_update_busy:
            return "Finish or cancel the current Maintenance update first."

        if self._selected_refresh_busy:
            return "Another selected-game refresh is already running."

        if source == "achievements":
            main_window = self._main_window()
            steam_id = getattr(main_window, "steam_id", None)
            steam_api_key = getattr(main_window, "steam_api_key", None)

            if not steam_id:
                return "A SteamID64 is required to refresh achievements."

            if not steam_api_key:
                return "A Steam Web API key is required to refresh achievements."

        return None

    def _refresh_selected_game(self, source):
        reason = self._selected_refresh_unavailable_reason(source)

        if reason is not None:
            QMessageBox.information(
                self,
                "Refresh Unavailable",
                reason,
            )
            return

        game = self.selected_game
        main_window = self._main_window()

        steam_id = getattr(
            main_window,
            "steam_id",
            None,
        )

        steam_api_key = getattr(
            main_window,
            "steam_api_key",
            None,
        )

        source_labels = {
            "hltb": "HLTB",
            "metadata": "Genre / Tags",
            "achievements": "Achievements",
        }

        self._set_selected_refresh_status(
            f"Refreshing {source_labels[source]} for {game.name}...",
            "accent",
        )

        started = self._selected_refresh_controller.start(
            source,
            game,
            steam_id=steam_id,
            steam_api_key=steam_api_key,
        )

        if not started:
            self._set_selected_refresh_status(
                "Another selected-game refresh is already running.",
                "warning",
            )

    def _selected_refresh_busy_changed(self, busy):
        self._selected_refresh_busy = busy
        self._update_selected_refresh_enabled()

    def _global_update_busy_changed(self, busy):
        self._global_update_busy = busy
        self._update_selected_refresh_enabled()

    def _update_selected_refresh_enabled(self):
        controls = (
            (
                "hltb",
                self.refresh_hltb_button,
                "Run a fresh HowLongToBeat lookup for the selected game.",
            ),
            (
                "metadata",
                self.refresh_metadata_button,
                "Refresh genre and tag data for the selected game.",
            ),
            (
                "achievements",
                self.refresh_achievements_button,
                "Refresh Steam achievement progress for the selected game.",
            ),
        )

        for source, button, enabled_tooltip in controls:
            reason = self._selected_refresh_unavailable_reason(source)
            button.setEnabled(reason is None)
            button.setToolTip(reason or enabled_tooltip)

    def _selected_refresh_succeeded(
        self,
        source,
        game,
    ):
        source_labels = {
            "hltb": "HLTB",
            "metadata": "Genre / Tags",
            "achievements": "Achievements",
        }

        self.genre_tag_filter.set_available_from_games(self.games)
        self.refresh_data()

        if self.selected_game is not None:
            self.show_selected_game()

        self.data_changed.emit()

        if source == "hltb" and getattr(game, "hltb_match_status", None) == "review":
            self._set_selected_refresh_status(
                f"{source_labels[source]} refreshed for {game.name}; "
                "the match needs review.",
                "warning",
            )
            return

        self._set_selected_refresh_status(
            f"{source_labels[source]} refreshed for {game.name}.",
            "positive",
        )

    def _selected_refresh_failed(
        self,
        source,
        game,
        error_message,
    ):
        source_labels = {
            "hltb": "HLTB",
            "metadata": "Genre / Tags",
            "achievements": "Achievements",
        }

        label = source_labels.get(source, source)

        self._set_selected_refresh_status(
            f"{label} refresh failed for {game.name}.",
            "danger",
        )

        QMessageBox.warning(
            self,
            f"{label} Refresh Failed",
            f"Could not refresh {label} for {game.name}:\n\n{error_message}",
        )

    def stop_trailer(self):
        self.trailer_player.stop()

    def clear_game_details(self):
        self.selected_game = None

        self.details_panel.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        self.trailer_player.clear_game()
        self.game_title.setText("No game selected")
        self.status_value.set_badge("NO GAME", "neutral")
        self.type_badge.setVisible(False)
        self.reception_badge.setVisible(False)

        self.game_description.setText("")
        self.game_details.setText("")
        self.game_image.setPixmap(QPixmap())
        self.game_image.setText("Select a game")
        self.manual_status_combo.blockSignals(True)
        self.manual_status_combo.setCurrentText("Automatic")
        self.manual_status_combo.setEnabled(False)
        self.manual_status_combo.blockSignals(False)

        self.rating_combo.blockSignals(True)
        self.rating_combo.setCurrentIndex(0)
        self.rating_combo.setEnabled(False)
        self.rating_combo.blockSignals(False)

        self.steam_page_button.setEnabled(False)
        self.hltb_page_button.setEnabled(False)
        self._set_selected_refresh_status("")
        self._set_detail_content_visible(False)
        self._update_selected_refresh_enabled()

        self.current_game_pixmap = None

    def open_selected_steam_page(self):
        if self.selected_game is None:
            return

        url = QUrl(f"https://store.steampowered.com/app/{self.selected_game.app_id}/")

        QDesktopServices.openUrl(url)

    def open_selected_hltb_page(self):
        if self.selected_game is None:
            return

        web_link = getattr(self.selected_game, "hltb_web_link", None)

        if not web_link:
            return

        QDesktopServices.openUrl(QUrl(web_link))

    def update_media_sizes(self):
        if not hasattr(self, "details_content"):
            return

        layout = self.details_content.layout()
        margins = layout.contentsMargins()
        available_width = (
            self.details_panel.viewport().width() - margins.left() - margins.right()
        )

        media_width = min(max(available_width, 1), 520)
        image_height = int(media_width * 215 / 460)
        self.game_image.setFixedSize(media_width, image_height)

        if self.current_game_pixmap is not None:
            scaled_pixmap = self.current_game_pixmap.scaled(
                self.game_image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.game_image.setPixmap(scaled_pixmap)

        self._update_detail_typography()

    def _update_detail_typography(self):
        display_size = self.display_size_combo.currentText()
        preset = LIBRARY_DISPLAY_PRESETS.get(
            display_size,
            LIBRARY_DISPLAY_PRESETS[DEFAULT_LIBRARY_DISPLAY_SIZE],
        )
        panel_width = self.details_panel.viewport().width()
        title_size = (
            preset["title_wide"] if panel_width >= 560 else preset["title_narrow"]
        )

        self.game_title.setStyleSheet(f"font-size: {title_size}pt; font-weight: bold;")

        heading_size = max(preset["detail_font"], 11)
        self.about_heading.setStyleSheet(f"font-size: {heading_size}pt;")
        self.details_heading.setStyleSheet(f"font-size: {heading_size}pt;")

        for label in (
            self.game_description,
            self.game_details,
            self.status_label,
            self.status_value,
            self.rating_label,
            self.refresh_selected_label,
            self.selected_refresh_status,
        ):
            font = label.font()
            font.setPointSize(preset["detail_font"])
            label.setFont(font)

        for control in (
            self.manual_status_combo,
            self.rating_combo,
            self.refresh_hltb_button,
            self.refresh_metadata_button,
            self.refresh_achievements_button,
            self.steam_page_button,
        ):
            font = control.font()
            font.setPointSize(preset["detail_font"])
            control.setFont(font)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "details_panel"):
            QTimer.singleShot(0, self.update_media_sizes)

    def hideEvent(self, event):
        self.trailer_player.pause()
        super().hideEvent(event)

    def sort_by_column(self, column):
        if column == 0:
            if (
                self.header_sort_column == column
                and self.header_sort_order == Qt.SortOrder.AscendingOrder
            ):
                self.header_sort_order = Qt.SortOrder.DescendingOrder
            else:
                self.header_sort_column = column
                self.header_sort_order = Qt.SortOrder.AscendingOrder

        elif self.header_sort_column == column:
            if self.header_sort_order == Qt.SortOrder.AscendingOrder:
                self.header_sort_order = Qt.SortOrder.DescendingOrder
            else:
                self.header_sort_column = None
                self.header_sort_order = Qt.SortOrder.AscendingOrder

        else:
            self.header_sort_column = column
            self.header_sort_order = Qt.SortOrder.AscendingOrder

        header = self.table.horizontalHeader()

        if self.header_sort_column is None:
            header.setSortIndicatorShown(False)
            self.game_table_model.set_sort_column(None)
        else:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(
                self.header_sort_column,
                self.header_sort_order,
            )
            self.game_table_model.set_sort_column(
                self.header_sort_column,
            )

        self.apply_filters()
        self._save_library_view()

    def sort_filter_changed(self):
        self.header_sort_column = None

        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.game_table_model.set_sort_column(None)

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
            ratings = load_game_ratings()

            return sorted(
                games,
                key=lambda game: ratings.get(
                    game.app_id,
                    0,
                ),
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
                "Game": 0,
                "Test / Beta": 1,
                "Unknown (Test / Beta)": 2,
                "Unknown (Game)": 3,
                "Unknown": 4,
                "Software": 5,
                "Unknown (Software)": 6,
                "DLC": 7,
                "Video": 8,
                "Hardware": 9,
            }

            return sorted(
                games,
                key=lambda game: (
                    type_order.get(
                        self.genre_tag_filter.display_steam_type(game),
                        99,
                    ),
                    game.name.lower(),
                ),
                reverse=reverse,
            )

        return games

    def refresh_ratings(self):
        self.game_table_model.set_ratings(load_game_ratings())
