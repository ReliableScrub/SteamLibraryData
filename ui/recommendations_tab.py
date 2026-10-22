import html
import json

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    QSortFilterProxyModel,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from recommendations.persistence import (
    load_recommendation_state,
    load_saved_recommendations,
)
from recommendations.similar import SimilarGameIndex
from storage.image_cache import get_cached_image_path, get_game_image

TOP_PICK_COLUMNS = 5
TOP_PICK_IMAGE_WIDTH = 184
TOP_PICK_IMAGE_HEIGHT = 86
DETAIL_IMAGE_WIDTH = 300
DETAIL_IMAGE_HEIGHT = 140
SIMILAR_RESULT_LIMIT = 50


class RecommendationTableModel(QAbstractTableModel):
    HEADERS = ("#", "Game", "Score")

    def __init__(self, games_by_id, parent=None):
        super().__init__(parent)
        self.games_by_id = games_by_id
        self.records = []

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0

        return len(self.records)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0

        return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        record = self.records[index.row()]
        app_id = record["app_id"]
        game = self.games_by_id.get(app_id)
        name = game.name if game is not None else f"Unknown App {app_id}"

        if role == Qt.ItemDataRole.UserRole:
            return app_id

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() in {0, 2}:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            return None

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if index.column() == 0:
            return index.row() + 1

        if index.column() == 1:
            return name

        if index.column() == 2:
            return f"{record['score']:.4f}"

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]

        return section + 1

    def set_records(self, records):
        self.beginResetModel()
        self.records = list(records)
        self.endResetModel()

    def set_games_by_id(self, games_by_id):
        self.games_by_id = games_by_id

        if self.records:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.records) - 1, len(self.HEADERS) - 1)
            self.dataChanged.emit(top_left, bottom_right)

    def record_at(self, row):
        if 0 <= row < len(self.records):
            return self.records[row]

        return None


class RecommendationFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.search_text = ""

    def set_search_text(self, text):
        self.search_text = text.strip().casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.search_text:
            return True

        source_model = self.sourceModel()
        record = source_model.record_at(source_row)

        if record is None:
            return False

        app_id = record["app_id"]
        game = source_model.games_by_id.get(app_id)

        if game is None:
            return self.search_text in str(app_id)

        return self.search_text in game.name.casefold()


class RecommendationCard(QFrame):
    clicked = Signal(int)

    def __init__(self, app_id, name, score, traits, parent=None):
        super().__init__(parent)
        self.app_id = app_id

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(190)
        self.setMaximumWidth(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.image_label = QLabel("Loading image…")
        self.image_label.setFixedSize(TOP_PICK_IMAGE_WIDTH, TOP_PICK_IMAGE_HEIGHT)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        title_label = QLabel(name)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: bold;")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        score_label = QLabel(f"Fit score: {score:.4f}")
        score_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        traits_label = QLabel(" • ".join(traits) if traits else "No explanation traits")
        traits_label.setWordWrap(True)
        traits_label.setStyleSheet("color: palette(mid);")
        traits_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)
        layout.addWidget(score_label)
        layout.addWidget(traits_label)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.app_id)

        super().mousePressEvent(event)


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
        except Exception:
            image_path = None

        self.signals.loaded.emit(self.app_id, image_path)


class RecommendationsTab(QWidget):
    def __init__(self, games, parent=None):
        super().__init__(parent)

        self.games = list(games)
        self.games_by_id = {game.app_id: game for game in self.games}

        self.recommendations_by_id = {}
        self.selected_recommendation_app_id = None
        self.selected_similar_app_id = None
        self.similar_reference_app_id = None
        self.similar_index = None
        self.similar_scores = []

        self.thread_pool = QThreadPool.globalInstance()
        self.image_targets = {}
        self.image_requests_in_flight = set()

        self._create_controls()
        self._create_layout()
        self._connect_signals()
        self._populate_reference_games()
        self.refresh()

    def _create_controls(self):
        self.mode_tabs = QTabWidget()

        self.for_you_page = QWidget()
        self.similar_page = QWidget()

        self.mode_tabs.addTab(self.for_you_page, "For You")
        self.mode_tabs.addTab(self.similar_page, "Similar to a Game")

        self.saved_status_label = QLabel("No saved recommendations.")
        self.saved_status_label.setWordWrap(True)

        self.reload_button = QPushButton("Reload Saved Recommendations")

        self.top_cards_container = QWidget()
        self.top_cards_layout = QGridLayout(self.top_cards_container)
        self.top_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.top_cards_layout.setSpacing(10)

        self.top_cards_scroll = QScrollArea()
        self.top_cards_scroll.setWidgetResizable(True)
        self.top_cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.top_cards_scroll.setWidget(self.top_cards_container)

        self.all_search_box = QLineEdit()
        self.all_search_box.setPlaceholderText("Search all recommendations…")

        self.all_model = RecommendationTableModel(self.games_by_id, self)
        self.all_proxy = RecommendationFilterProxy(self)
        self.all_proxy.setSourceModel(self.all_model)

        self.all_table = QTableView()
        self.all_table.setModel(self.all_proxy)
        self.all_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.all_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.all_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.all_table.setAlternatingRowColors(True)
        self.all_table.verticalHeader().setVisible(False)

        all_header = self.all_table.horizontalHeader()
        all_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        all_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        all_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.recommendation_image = QLabel("Select a recommendation")
        self.recommendation_image.setFixedSize(DETAIL_IMAGE_WIDTH, DETAIL_IMAGE_HEIGHT)
        self.recommendation_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.recommendation_title = QLabel("Select a recommendation")
        self.recommendation_title.setWordWrap(True)
        self.recommendation_title.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.recommendation_score = QLabel("")
        self.recommendation_explanation = QTextBrowser()
        self.recommendation_steam_button = QPushButton("Steam Page")
        self.recommendation_steam_button.setEnabled(False)

        self.reference_combo = QComboBox()
        self.reference_combo.setEditable(True)
        self.reference_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.reference_combo.setMinimumWidth(350)

        completer = self.reference_combo.completer()

        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        self.find_similar_button = QPushButton("Find Similar Backlog Games")
        self.similar_status_label = QLabel(
            "Choose any owned game with genre/tag data. Results are unplayed games only."
        )
        self.similar_status_label.setWordWrap(True)

        self.reference_image = QLabel("Choose a reference game")
        self.reference_image.setFixedSize(DETAIL_IMAGE_WIDTH, DETAIL_IMAGE_HEIGHT)
        self.reference_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.reference_title = QLabel("No reference game selected")
        self.reference_title.setWordWrap(True)
        self.reference_title.setStyleSheet("font-size: 13pt; font-weight: bold;")

        self.similar_table = QTableWidget()
        self.similar_table.setColumnCount(4)
        self.similar_table.setHorizontalHeaderLabels(
            ["#", "Game", "Similarity", "Shared traits"]
        )
        self.similar_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.similar_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.similar_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.similar_table.setAlternatingRowColors(True)
        self.similar_table.verticalHeader().setVisible(False)

        similar_header = self.similar_table.horizontalHeader()
        similar_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        similar_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        similar_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        similar_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.similar_image = QLabel("Select a result")
        self.similar_image.setFixedSize(DETAIL_IMAGE_WIDTH, DETAIL_IMAGE_HEIGHT)
        self.similar_image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.similar_title = QLabel("Select a similar game")
        self.similar_title.setWordWrap(True)
        self.similar_title.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self.similar_details = QTextBrowser()
        self.similar_steam_button = QPushButton("Steam Page")
        self.similar_steam_button.setEnabled(False)

    def _create_layout(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        title = QLabel("<h2>Recommendations</h2>")
        root_layout.addWidget(title)
        root_layout.addWidget(self.mode_tabs, 1)

        self._create_for_you_layout()
        self._create_similar_layout()

    def _create_for_you_layout(self):
        layout = QVBoxLayout(self.for_you_page)

        status_row = QHBoxLayout()
        status_row.addWidget(self.saved_status_label, 1)
        status_row.addWidget(self.reload_button)
        layout.addLayout(status_row)

        top_heading = QLabel("<h3>Top Picks</h3>")
        top_help = QLabel(
            "Ten diversified picks from your saved personalized recommendation build."
        )
        top_help.setWordWrap(True)

        top_section = QWidget()
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(top_heading)
        top_layout.addWidget(top_help)
        top_layout.addWidget(self.top_cards_scroll, 1)

        lower_section = QWidget()
        lower_layout = QVBoxLayout(lower_section)
        lower_layout.setContentsMargins(0, 0, 0, 0)

        all_heading = QLabel("<h3>All Recommendations</h3>")
        lower_layout.addWidget(all_heading)
        lower_layout.addWidget(self.all_search_box)

        details_panel = QWidget()
        details_panel.setMinimumWidth(320)
        details_layout = QVBoxLayout(details_panel)
        details_layout.addWidget(
            self.recommendation_image,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        details_layout.addWidget(self.recommendation_title)
        details_layout.addWidget(self.recommendation_score)
        details_layout.addWidget(self.recommendation_explanation, 1)
        details_layout.addWidget(self.recommendation_steam_button)

        lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        lower_splitter.addWidget(self.all_table)
        lower_splitter.addWidget(details_panel)
        lower_splitter.setStretchFactor(0, 2)
        lower_splitter.setStretchFactor(1, 1)
        lower_splitter.setCollapsible(0, False)
        lower_splitter.setCollapsible(1, False)
        lower_splitter.setSizes([700, 380])

        lower_layout.addWidget(lower_splitter, 1)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(top_section)
        main_splitter.addWidget(lower_section)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)
        main_splitter.setSizes([330, 330])

        layout.addWidget(main_splitter, 1)

    def _create_similar_layout(self):
        layout = QVBoxLayout(self.similar_page)

        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Reference game:"))
        selector_row.addWidget(self.reference_combo, 1)
        selector_row.addWidget(self.find_similar_button)

        layout.addLayout(selector_row)
        layout.addWidget(self.similar_status_label)

        reference_panel = QWidget()
        reference_layout = QHBoxLayout(reference_panel)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        reference_layout.addWidget(self.reference_image)

        reference_text_layout = QVBoxLayout()
        reference_text_layout.addWidget(QLabel("<b>Selected reference</b>"))
        reference_text_layout.addWidget(self.reference_title)
        reference_text_layout.addStretch()
        reference_layout.addLayout(reference_text_layout, 1)

        layout.addWidget(reference_panel)

        result_details_panel = QWidget()
        result_details_panel.setMinimumWidth(320)
        result_details_layout = QVBoxLayout(result_details_panel)
        result_details_layout.addWidget(
            self.similar_image,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        result_details_layout.addWidget(self.similar_title)
        result_details_layout.addWidget(self.similar_details, 1)
        result_details_layout.addWidget(self.similar_steam_button)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.similar_table)
        splitter.addWidget(result_details_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setSizes([700, 380])

        layout.addWidget(splitter, 1)

    def _connect_signals(self):
        self.reload_button.clicked.connect(self.refresh)
        self.all_search_box.textChanged.connect(self.all_proxy.set_search_text)

        self.all_table.selectionModel().selectionChanged.connect(
            lambda *_: self._all_recommendation_selection_changed()
        )

        self.recommendation_steam_button.clicked.connect(
            self.open_selected_recommendation_steam_page
        )

        self.find_similar_button.clicked.connect(self.find_similar_games)
        self.similar_table.itemSelectionChanged.connect(self._similar_selection_changed)
        self.similar_steam_button.clicked.connect(self.open_selected_similar_steam_page)

    def set_games(self, games):
        self.games = list(games)
        self.games_by_id = {game.app_id: game for game in self.games}
        self.all_model.set_games_by_id(self.games_by_id)
        self.similar_index = None
        self._populate_reference_games()
        self.refresh()

    def _populate_reference_games(self):
        current_app_id = self.similar_reference_app_id

        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()

        selectable_games = [game for game in self.games if game.genres or game.tags]

        selectable_games.sort(key=lambda game: (game.name.casefold(), game.app_id))

        selected_index = -1

        for index, game in enumerate(selectable_games):
            display_name = f"{game.name} ({game.app_id})"
            self.reference_combo.addItem(display_name, game.app_id)

            if game.app_id == current_app_id:
                selected_index = index

        if selected_index >= 0:
            self.reference_combo.setCurrentIndex(selected_index)
        elif self.reference_combo.count() > 0:
            self.reference_combo.setCurrentIndex(-1)
            self.reference_combo.setEditText("")

        completer = self.reference_combo.completer()

        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        self.reference_combo.blockSignals(False)

    def refresh(self):
        state = load_recommendation_state()
        rows = load_saved_recommendations()

        self.recommendations_by_id = {}
        self.selected_recommendation_app_id = None
        self.all_model.set_records([])
        self._clear_top_cards()
        self._clear_recommendation_details()

        if state is None or not rows:
            self.saved_status_label.setText(
                "No saved personalized recommendation build is available."
            )
            return

        (
            method,
            model_version,
            feature_version,
            generated_at,
            training_game_count,
            rated_game_count,
            implicit_game_count,
            candidate_game_count,
        ) = state

        records = []

        for row in rows:
            app_id, score, match_tier, explanation_json, row_generated_at = row

            record = {
                "app_id": app_id,
                "score": score,
                "match_tier": match_tier,
                "explanation_json": explanation_json,
                "explanation": None,
                "explanation_loaded": False,
                "generated_at": row_generated_at,
            }

            records.append(record)
            self.recommendations_by_id[app_id] = record

        self.all_model.set_records(records)

        top_picks = [record for record in records if record["match_tier"] == "top_pick"]

        self._populate_top_cards(top_picks)

        self.saved_status_label.setText(
            f"{candidate_game_count} recommendations"
            f" • {len(top_picks)} top picks"
            f" • {method}"
            f" • model {model_version}"
            f" • features {feature_version}"
            f" • {training_game_count} training games"
        )

    def _clear_top_cards(self):
        while self.top_cards_layout.count():
            item = self.top_cards_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _populate_top_cards(self, top_picks):
        for index, record in enumerate(top_picks):
            app_id = record["app_id"]
            game = self.games_by_id.get(app_id)
            name = game.name if game is not None else f"Unknown App {app_id}"

            explanation = self._explanation_for(record)
            traits = self._taste_trait_names(explanation)

            card = RecommendationCard(
                app_id=app_id,
                name=name,
                score=record["score"],
                traits=traits,
                parent=self.top_cards_container,
            )

            card.clicked.connect(self.show_recommendation)

            row = index // TOP_PICK_COLUMNS
            column = index % TOP_PICK_COLUMNS
            self.top_cards_layout.addWidget(card, row, column)

            self._request_image(app_id, card.image_label)

        for column in range(TOP_PICK_COLUMNS):
            self.top_cards_layout.setColumnStretch(column, 1)

    def _all_recommendation_selection_changed(self):
        selected_rows = self.all_table.selectionModel().selectedRows()

        if not selected_rows:
            return

        proxy_index = selected_rows[0]
        source_index = self.all_proxy.mapToSource(proxy_index)
        record = self.all_model.record_at(source_index.row())

        if record is not None:
            self.show_recommendation(record["app_id"])

    def show_recommendation(self, app_id):
        record = self.recommendations_by_id.get(app_id)

        if record is None:
            self._clear_recommendation_details()
            return

        self.selected_recommendation_app_id = app_id
        game = self.games_by_id.get(app_id)
        name = game.name if game is not None else f"Unknown App {app_id}"

        self.recommendation_title.setText(name)

        tier_text = " • Top Pick" if record["match_tier"] == "top_pick" else ""
        self.recommendation_score.setText(
            f"Recommendation score: {record['score']:.4f}{tier_text}"
        )

        explanation = self._explanation_for(record)
        self.recommendation_explanation.setHtml(
            self._format_recommendation_explanation(explanation)
        )

        self.recommendation_steam_button.setEnabled(True)
        self._request_image(app_id, self.recommendation_image)

    def _explanation_for(self, record):
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

    def _taste_trait_names(self, explanation):
        if not explanation:
            return []

        return [
            feature.get("name", "Unknown")
            for feature in explanation.get("taste_features", [])
        ]

    def _format_recommendation_explanation(self, explanation):
        if not explanation:
            return "<p>No explanation data is available for this recommendation.</p>"

        taste_features = explanation.get("taste_features", [])
        supporting_games = explanation.get("supporting_games", [])
        parts = ["<h3>Why it fits</h3>"]

        taste_names = [
            html.escape(feature.get("name", "Unknown")) for feature in taste_features
        ]

        if taste_names:
            parts.append("<p><b>" + " • ".join(taste_names) + "</b></p>")
        else:
            parts.append("<p>No strong taste traits were identified.</p>")

        if supporting_games:
            parts.append("<h3>Similar games you've played</h3>")

            for supporting_game in supporting_games:
                name = html.escape(supporting_game.get("name", "Unknown"))
                similarity = supporting_game.get("adjusted_similarity", 0.0)
                evidence = html.escape(str(supporting_game.get("evidence", "unknown")))
                feedback_weight = supporting_game.get("feedback_weight", 0.0)

                shared_names = [
                    html.escape(feature.get("name", "Unknown"))
                    for feature in supporting_game.get("shared_features", [])
                ]

                parts.append(
                    f"<p><b>{name}</b><br>"
                    f"Similarity: {similarity:.4f}<br>"
                    f"Evidence: {evidence}<br>"
                    f"Feedback weight: {feedback_weight:.3f}"
                )

                if shared_names:
                    parts.append("<br>Shared traits: " + " • ".join(shared_names))

                parts.append("</p>")

        return "".join(parts)

    def _clear_recommendation_details(self):
        self.selected_recommendation_app_id = None
        self.recommendation_title.setText("Select a recommendation")
        self.recommendation_score.setText("")
        self.recommendation_explanation.clear()
        self.recommendation_steam_button.setEnabled(False)
        self._clear_image_label(self.recommendation_image, "Select a recommendation")

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
        self.reference_title.setText(reference_game.name)
        self._request_image(reference_app_id, self.reference_image)

        if self.similar_index is None:
            self.similar_status_label.setText("Building the local similarity index…")
            self.similar_index = SimilarGameIndex(self.games)

        scores = self.similar_index.find_similar(
            reference_app_id,
            limit=SIMILAR_RESULT_LIMIT,
            unplayed_only=True,
        )

        self.similar_scores = scores
        self._populate_similar_table(scores)
        self._clear_similar_details()

        if scores:
            self.similar_status_label.setText(
                f"Showing {len(scores)} unplayed games most similar to {reference_game.name}. "
                "This view uses content similarity only; it does not use your overall taste profile."
            )
            self.similar_table.selectRow(0)
        else:
            self.similar_status_label.setText(
                f"No unplayed games with usable shared genre/tag features were found for {reference_game.name}."
            )

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

    def _populate_similar_table(self, scores):
        self.similar_table.setRowCount(len(scores))

        for row_index, score in enumerate(scores):
            game = self.games_by_id.get(score.app_id)
            name = game.name if game is not None else f"Unknown App {score.app_id}"

            rank_item = QTableWidgetItem(str(row_index + 1))
            name_item = QTableWidgetItem(name)
            similarity_item = QTableWidgetItem(f"{score.adjusted_similarity:.4f}")
            traits_item = QTableWidgetItem(" • ".join(score.shared_traits))

            for item in (rank_item, name_item, similarity_item, traits_item):
                item.setData(Qt.ItemDataRole.UserRole, score.app_id)

            similarity_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

            self.similar_table.setItem(row_index, 0, rank_item)
            self.similar_table.setItem(row_index, 1, name_item)
            self.similar_table.setItem(row_index, 2, similarity_item)
            self.similar_table.setItem(row_index, 3, traits_item)

    def _similar_selection_changed(self):
        selected_rows = self.similar_table.selectionModel().selectedRows()

        if not selected_rows:
            return

        row = selected_rows[0].row()

        if not 0 <= row < len(self.similar_scores):
            return

        score = self.similar_scores[row]
        self.selected_similar_app_id = score.app_id

        game = self.games_by_id.get(score.app_id)
        reference_game = self.games_by_id.get(self.similar_reference_app_id)

        name = game.name if game is not None else f"Unknown App {score.app_id}"
        reference_name = (
            reference_game.name if reference_game is not None else "the selected game"
        )

        self.similar_title.setText(name)

        shared_traits = " • ".join(html.escape(name) for name in score.shared_traits)

        detail_parts = [
            f"<p><b>Similarity to {html.escape(reference_name)}</b></p>",
            f"<p>Adjusted similarity: {score.adjusted_similarity:.4f}<br>",
            f"Raw cosine similarity: {score.similarity:.4f}<br>",
            f"Shared feature count: {score.shared_feature_count}</p>",
        ]

        if shared_traits:
            detail_parts.append(f"<p><b>Shared traits</b><br>{shared_traits}</p>")

        detail_parts.append(
            "<p>This score is based only on the selected game's genre/tag feature vector. "
            "Your global preference profile and feedback history are not used here.</p>"
        )

        self.similar_details.setHtml("".join(detail_parts))
        self.similar_steam_button.setEnabled(True)
        self._request_image(score.app_id, self.similar_image)

    def _clear_similar_details(self):
        self.selected_similar_app_id = None
        self.similar_title.setText("Select a similar game")
        self.similar_details.clear()
        self.similar_steam_button.setEnabled(False)
        self._clear_image_label(self.similar_image, "Select a result")

    def _request_image(self, app_id, label):
        label.setProperty("steam_app_id", app_id)

        cached_path = get_cached_image_path(app_id)

        if cached_path.exists():
            self._set_image(label, str(cached_path))
            return

        label.setPixmap(QPixmap())
        label.setText("Loading image…")

        targets = self.image_targets.setdefault(app_id, [])

        if label not in targets:
            targets.append(label)

        if app_id in self.image_requests_in_flight:
            return

        self.image_requests_in_flight.add(app_id)

        worker = ImageWorker(app_id)
        worker.signals.loaded.connect(self._image_loaded)
        self.thread_pool.start(worker)

    def _image_loaded(self, app_id, image_path):
        self.image_requests_in_flight.discard(app_id)
        labels = self.image_targets.pop(app_id, [])

        for label in labels:
            if label.property("steam_app_id") != app_id:
                continue

            if image_path:
                self._set_image(label, image_path)
            else:
                label.setPixmap(QPixmap())
                label.setText("Image unavailable")

    def _set_image(self, label, image_path):
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

    def _clear_image_label(self, label, text):
        label.setProperty("steam_app_id", None)
        label.setPixmap(QPixmap())
        label.setText(text)

    def open_selected_recommendation_steam_page(self):
        if self.selected_recommendation_app_id is None:
            return

        self._open_steam_page(self.selected_recommendation_app_id)

    def open_selected_similar_steam_page(self):
        if self.selected_similar_app_id is None:
            return

        self._open_steam_page(self.selected_similar_app_id)

    def _open_steam_page(self, app_id):
        QDesktopServices.openUrl(QUrl(f"https://store.steampowered.com/app/{app_id}/"))
