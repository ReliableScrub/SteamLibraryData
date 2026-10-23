import html
import json

import requests
from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRunnable,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedLayout,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from api.store_api import get_trailer_url
from recommendations.persistence import (
    load_recommendation_state,
    load_saved_recommendations,
)
from recommendations.similar import SimilarGameIndex
from storage.image_cache import get_cached_image_path, get_game_image
from ui.genre_tag_filter import GenreTagFilterWidget

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
        except (requests.RequestException, OSError):
            image_path = None

        self.signals.loaded.emit(
            self.app_id,
            image_path,
        )


class SlidingStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._animation_group = None

    def is_animating(self):
        return self._animation_group is not None

    def slide_to(self, index, direction=1):
        if not 0 <= index < self.count():
            return

        current_index = self.currentIndex()

        if current_index < 0:
            self.setCurrentIndex(index)
            return

        if current_index == index:
            return

        if self.is_animating():
            return

        width = self.width()

        if width <= 0:
            self.setCurrentIndex(index)
            return

        current_widget = self.widget(current_index)
        next_widget = self.widget(index)

        if current_widget is None or next_widget is None:
            self.setCurrentIndex(index)
            return

        stack_layout = self.layout()

        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)

        offset = width if direction >= 0 else -width

        current_widget.setGeometry(self.rect())
        next_widget.setGeometry(self.rect())

        current_widget.move(
            QPoint(
                0,
                0,
            )
        )

        next_widget.move(
            QPoint(
                offset,
                0,
            )
        )

        current_widget.show()
        next_widget.show()
        next_widget.raise_()

        current_animation = QPropertyAnimation(
            current_widget,
            b"pos",
            self,
        )

        current_animation.setDuration(240)

        current_animation.setStartValue(
            QPoint(
                0,
                0,
            )
        )

        current_animation.setEndValue(
            QPoint(
                -offset,
                0,
            )
        )

        current_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        next_animation = QPropertyAnimation(
            next_widget,
            b"pos",
            self,
        )

        next_animation.setDuration(240)

        next_animation.setStartValue(
            QPoint(
                offset,
                0,
            )
        )

        next_animation.setEndValue(
            QPoint(
                0,
                0,
            )
        )

        next_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        group = QParallelAnimationGroup(self)

        group.addAnimation(current_animation)
        group.addAnimation(next_animation)

        self._animation_group = group

        group.finished.connect(
            lambda: self._finish_slide(
                index,
                current_widget,
                next_widget,
            )
        )

        group.start()

    def _finish_slide(
        self,
        index,
        current_widget,
        next_widget,
    ):
        self.setCurrentIndex(index)

        current_widget.move(
            QPoint(
                0,
                0,
            )
        )

        next_widget.move(
            QPoint(
                0,
                0,
            )
        )

        stack_layout = self.layout()

        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackingMode.StackOne)

        self._animation_group = None


class RecommendationsTab(QWidget):
    def __init__(self, games, parent=None):
        super().__init__(parent)

        self.games = list(games)
        self.games_by_id = {game.app_id: game for game in self.games}

        self.recommendation_records = []
        self.recommendations_by_id = {}

        self.for_you_records = []
        self.current_for_you_index = -1

        self.similar_index = None
        self.similar_reference_app_id = None
        self.similar_all_scores = []
        self.similar_scores = []
        self.similar_scores_by_id = {}

        self.thread_pool = QThreadPool.globalInstance()

        self.image_targets = {}
        self.image_requests_in_flight = set()

        self.recommendation_state = None

        self._create_controls()
        self._create_layout()
        self._connect_signals()

        self.genre_tag_filter.set_available_from_games(self.games)

        self._populate_reference_games()
        self.refresh()

    def _create_controls(self):
        self.type_filter = QComboBox()

        self.type_filter.addItems(
            [
                "All Types",
                "Game",
                "Software",
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

        self.hltb_min_filter.setRange(
            0,
            10000,
        )

        self.hltb_min_filter.setDecimals(1)
        self.hltb_min_filter.setSingleStep(0.5)
        self.hltb_min_filter.setSpecialValueText("Min")
        self.hltb_min_filter.setSuffix(" h")

        self.hltb_max_filter = QDoubleSpinBox()

        self.hltb_max_filter.setRange(
            0,
            10000,
        )

        self.hltb_max_filter.setDecimals(1)
        self.hltb_max_filter.setSingleStep(0.5)
        self.hltb_max_filter.setSpecialValueText("Max")
        self.hltb_max_filter.setSuffix(" h")

        self.clear_filters_button = QPushButton("Clear Filters")

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

        self.reload_button = QPushButton("Reload Saved Recommendations")

        self.for_you_stack = SlidingStackedWidget()

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

        self.similar_image.setFixedSize(
            CARD_IMAGE_WIDTH,
            CARD_IMAGE_HEIGHT,
        )

        self.similar_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.similar_hltb = QLabel(self._empty_hltb_text())

        self.similar_hltb.setWordWrap(True)

        self.similar_steam_button = QPushButton("Steam Page")

        self.similar_steam_button.setEnabled(False)

        self.similar_trailer_button = QPushButton("Trailer")

        self.similar_trailer_button.setEnabled(False)

        self.similar_title = QLabel("No similar game selected")

        self.similar_title.setWordWrap(True)

        self.similar_title.setStyleSheet("font-size: 16pt; font-weight: bold;")

        self.similar_summary = QLabel("")
        self.similar_summary.setWordWrap(True)

        self.similar_details = QTextBrowser()

    def _create_layout(self):
        root_layout = QVBoxLayout(self)

        root_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        title = QLabel("<h2>Recommendations</h2>")

        root_layout.addWidget(title)

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

        status_row.addWidget(self.reload_button)

        layout.addLayout(status_row)

        help_label = QLabel(
            "Browse up to ten personalized picks. "
            "Filters narrow the saved recommendation pool "
            "without rebuilding the recommendation model."
        )

        help_label.setWordWrap(True)

        layout.addWidget(help_label)

        layout.addWidget(
            self.for_you_stack,
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

        left_panel = QFrame()

        left_panel.setFrameShape(QFrame.Shape.StyledPanel)

        left_panel.setMinimumWidth(430)
        left_panel.setMaximumWidth(500)

        left_layout = QVBoxLayout(left_panel)

        left_layout.addWidget(
            self.similar_image,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        left_layout.addSpacing(8)

        hltb_heading = QLabel("<b>HowLongToBeat</b>")

        left_layout.addWidget(hltb_heading)

        left_layout.addWidget(self.similar_hltb)

        left_layout.addStretch()

        link_row = QHBoxLayout()

        link_row.addWidget(self.similar_steam_button)

        link_row.addWidget(self.similar_trailer_button)

        left_layout.addLayout(link_row)

        right_panel = QWidget()

        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(self.similar_title)

        right_layout.addWidget(self.similar_summary)

        right_layout.addWidget(
            self.similar_details,
            1,
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(left_panel)

        splitter.addWidget(right_panel)

        splitter.setStretchFactor(
            0,
            0,
        )

        splitter.setStretchFactor(
            1,
            1,
        )

        splitter.setCollapsible(
            0,
            False,
        )

        splitter.setCollapsible(
            1,
            False,
        )

        splitter.setSizes(
            [
                450,
                700,
            ]
        )

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

        self.reload_button.clicked.connect(self.refresh)

        self.find_similar_button.clicked.connect(self.find_similar_games)

        self.similar_result_combo.currentIndexChanged.connect(
            self._similar_result_changed
        )

        self.similar_steam_button.clicked.connect(self._open_selected_similar_steam)

        self.similar_trailer_button.clicked.connect(self._open_selected_similar_trailer)

    def set_games(self, games):
        self.games = list(games)

        self.games_by_id = {game.app_id: game for game in self.games}

        self.similar_index = None
        self.similar_all_scores = []
        self.similar_scores = []
        self.similar_scores_by_id = {}

        self.genre_tag_filter.set_available_from_games(self.games)

        self._populate_reference_games()

        self.refresh()

    def refresh(self):
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

        if selected_type != "All Types":
            type_values = {
                "Game": "game",
                "Software": "software",
                "Unknown": "unknown",
                "DLC": "dlc",
                "Video": "video",
                "Hardware": "hardware",
            }

            wanted_type = type_values[selected_type]

            actual_type = self.genre_tag_filter.inferred_steam_type(game)

            if actual_type != wanted_type:
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

    def _rebuild_for_you(self):
        self._clear_for_you_stack()

        if self.recommendation_state is None or not self.recommendation_records:
            self.saved_status_label.setText(
                "No saved personalized recommendation build is available."
            )

            self._add_for_you_placeholder("No saved recommendations are available.")

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

            self._add_for_you_placeholder(
                "No saved recommendations match the current filters."
            )

            return

        total = len(self.for_you_records)

        for index, record in enumerate(self.for_you_records):
            page = self._create_for_you_page(
                record,
                index,
                total,
            )

            self.for_you_stack.addWidget(page)

        self.current_for_you_index = 0

        self.for_you_stack.setCurrentIndex(0)

        self._update_saved_status(
            eligible_count=len(eligible),
            showing_count=total,
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

        features.update(
            {f"tag:{tag.casefold()}" for tag in (game.tags or {}) if tag}
        )

        return features

    def _create_for_you_page(
        self,
        record,
        index,
        total,
    ):
        app_id = record["app_id"]

        game = self.games_by_id[app_id]

        page = QWidget()

        page_layout = QHBoxLayout(page)

        page_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        left_panel = QFrame()

        left_panel.setFrameShape(QFrame.Shape.StyledPanel)

        left_panel.setMinimumWidth(430)
        left_panel.setMaximumWidth(500)

        left_layout = QVBoxLayout(left_panel)

        image_label = QLabel("Loading image…")

        image_label.setFixedSize(
            CARD_IMAGE_WIDTH,
            CARD_IMAGE_HEIGHT,
        )

        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        left_layout.addWidget(
            image_label,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        left_layout.addSpacing(8)

        left_layout.addWidget(QLabel("<b>HowLongToBeat</b>"))

        hltb_label = QLabel(self._hltb_text(game))

        hltb_label.setWordWrap(True)

        left_layout.addWidget(hltb_label)

        left_layout.addStretch()

        link_row = QHBoxLayout()

        steam_button = QPushButton("Steam Page")

        trailer_button = QPushButton("Trailer")

        steam_button.clicked.connect(
            lambda _checked=False, value=app_id: self._open_steam_page(value)
        )

        trailer_button.clicked.connect(
            lambda _checked=False, value=app_id: self._open_trailer(value)
        )

        link_row.addWidget(steam_button)

        link_row.addWidget(trailer_button)

        left_layout.addLayout(link_row)

        navigation_row = QHBoxLayout()

        previous_button = QPushButton("Previous")

        next_button = QPushButton("Next")

        position_label = QLabel(f"{index + 1} of {total}")

        position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        previous_button.clicked.connect(self.previous_for_you)

        next_button.clicked.connect(self.next_for_you)

        navigation_row.addWidget(previous_button)

        navigation_row.addWidget(
            position_label,
            1,
        )

        navigation_row.addWidget(next_button)

        left_layout.addLayout(navigation_row)

        right_panel = QWidget()

        right_layout = QVBoxLayout(right_panel)

        title_label = QLabel(game.name)

        title_label.setWordWrap(True)

        title_label.setStyleSheet("font-size: 16pt; font-weight: bold;")

        right_layout.addWidget(title_label)

        score_label = QLabel(f"Recommendation score: {record['score']:.4f}")

        score_label.setWordWrap(True)

        right_layout.addWidget(score_label)

        steam_type_text = self.genre_tag_filter.display_steam_type(game)

        type_label = QLabel(f"Steam Type: {steam_type_text}")

        right_layout.addWidget(type_label)

        explanation_browser = QTextBrowser()

        explanation = self._explanation_for(record)

        explanation_browser.setHtml(
            self._format_recommendation_explanation(
                game,
                explanation,
            )
        )

        right_layout.addWidget(
            explanation_browser,
            1,
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(left_panel)

        splitter.addWidget(right_panel)

        splitter.setStretchFactor(
            0,
            0,
        )

        splitter.setStretchFactor(
            1,
            1,
        )

        splitter.setCollapsible(
            0,
            False,
        )

        splitter.setCollapsible(
            1,
            False,
        )

        splitter.setSizes(
            [
                450,
                700,
            ]
        )

        page_layout.addWidget(splitter)

        self._request_image(
            app_id,
            image_label,
        )

        return page

    def previous_for_you(self):
        if len(self.for_you_records) <= 1:
            return

        if self.for_you_stack.is_animating():
            return

        new_index = (self.current_for_you_index - 1) % len(self.for_you_records)

        self.current_for_you_index = new_index

        self.for_you_stack.slide_to(
            new_index,
            direction=-1,
        )

    def next_for_you(self):
        if len(self.for_you_records) <= 1:
            return

        if self.for_you_stack.is_animating():
            return

        new_index = (self.current_for_you_index + 1) % len(self.for_you_records)

        self.current_for_you_index = new_index

        self.for_you_stack.slide_to(
            new_index,
            direction=1,
        )

    def _clear_for_you_stack(self):
        self.for_you_records = []
        self.current_for_you_index = -1

        while self.for_you_stack.count():
            widget = self.for_you_stack.widget(0)

            self.for_you_stack.removeWidget(widget)

            widget.deleteLater()

    def _add_for_you_placeholder(
        self,
        text,
    ):
        placeholder = QLabel(text)

        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        placeholder.setWordWrap(True)

        self.for_you_stack.addWidget(placeholder)

        self.for_you_stack.setCurrentIndex(0)

    def _update_saved_status(
        self,
        eligible_count,
        showing_count,
    ):
        state = self.recommendation_state

        if state is None:
            self.saved_status_label.setText("No saved recommendation build.")

            return

        (
            method,
            model_version,
            feature_version,
            _generated_at,
            training_game_count,
            _rated_game_count,
            _implicit_game_count,
            candidate_game_count,
        ) = state

        self.saved_status_label.setText(
            f"{candidate_game_count} saved recommendations"
            f" • {eligible_count} match filters"
            f" • showing {showing_count}"
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
        parts = ["<h3>Why it fits</h3>"]

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
                parts.append("<h3>Similar games you've played</h3>")

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

                    evidence = html.escape(
                        str(
                            supporting_game.get(
                                "evidence",
                                "unknown",
                            )
                        )
                    )

                    feedback_weight = supporting_game.get(
                        "feedback_weight",
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
                        f"Similarity: {similarity:.4f}<br>"
                        f"Evidence: {evidence}<br>"
                        f"Feedback weight: "
                        f"{feedback_weight:.3f}"
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

        if self.similar_reference_app_id is None or not self.similar_all_scores:
            self.similar_result_combo.setEnabled(False)

            self.similar_result_combo.blockSignals(False)

            self._clear_similar_card()

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

            display_text = f"{game.name} — {score.adjusted_similarity:.4f}"

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
            self.similar_status_label.setText(
                f"No similar backlog games for "
                f"{reference_name} match the "
                f"current filters."
            )

            self._clear_similar_card()

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

        self.similar_title.setText(game.name)

        steam_type_text = self.genre_tag_filter.display_steam_type(game)

        self.similar_summary.setText(
            f"Similarity to {reference_name}: "
            f"{score.adjusted_similarity:.4f}\n"
            f"Steam Type: {steam_type_text}"
        )

        self.similar_hltb.setText(self._hltb_text(game))

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
            f"<p><b>Adjusted similarity:</b> {score.adjusted_similarity:.4f}<br>",
            f"<b>Raw cosine similarity:</b> {score.similarity:.4f}<br>",
            f"<b>Shared feature count:</b> {score.shared_feature_count}</p>",
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
            "<p>This similarity result is based "
            "on genre/tag content features. "
            "It does not use your overall "
            "personalized taste profile.</p>"
        )

        self.similar_details.setHtml("".join(detail_parts))

        self.similar_steam_button.setEnabled(True)

        self.similar_trailer_button.setEnabled(True)

        self.similar_image.setProperty(
            "steam_app_id",
            game.app_id,
        )

        self._request_image(
            game.app_id,
            self.similar_image,
        )

    def _clear_similar_card(self):
        self.similar_image.setProperty(
            "steam_app_id",
            None,
        )

        self.similar_image.setPixmap(QPixmap())

        self.similar_image.setText("No result selected")

        self.similar_hltb.setText(self._empty_hltb_text())

        self.similar_title.setText("No similar game selected")

        self.similar_summary.setText("")

        self.similar_details.clear()

        self.similar_steam_button.setEnabled(False)

        self.similar_trailer_button.setEnabled(False)

    def _open_selected_similar_steam(self):
        app_id = self._selected_similar_app_id()

        if app_id is None:
            return

        self._open_steam_page(app_id)

    def _open_selected_similar_trailer(self):
        app_id = self._selected_similar_app_id()

        if app_id is None:
            return

        self._open_trailer(app_id)

    def _selected_similar_app_id(self):
        index = self.similar_result_combo.currentIndex()

        if index < 0:
            return None

        return self.similar_result_combo.itemData(index)

    @staticmethod
    def _open_steam_page(app_id):
        QDesktopServices.openUrl(QUrl(f"https://store.steampowered.com/app/{app_id}/"))

    def _open_trailer(self, app_id):
        try:
            trailer_url = get_trailer_url(app_id)
        except (
            requests.RequestException,
            OSError,
            ValueError,
            TypeError,
            KeyError,
        ) as error:
            QMessageBox.warning(
                self,
                "Trailer",
                f"Could not load the trailer:\n{error}",
            )

            return

        if not trailer_url:
            QMessageBox.information(
                self,
                "Trailer",
                "No Steam trailer is available for this game.",
            )

            return

        QDesktopServices.openUrl(QUrl(trailer_url))

    @staticmethod
    def _format_hours(value):
        if value is None:
            return "—"

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
        return "Main Story: —\nMain + Extra: —\nCompletionist: —\nAll Styles: —"

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

    @staticmethod
    def _set_image(
        label,
        image_path,
    ):
        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            label.setPixmap(QPixmap())

            label.setText("Image unavailable")

            return

        scaled = pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        label.setText("")
        label.setPixmap(scaled)
