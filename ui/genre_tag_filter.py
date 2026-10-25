from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyledItemDelegate,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

GENRE_CANONICAL_NAMES = {
    "free to play": "Free To Play",
}


def canonical_genre_name(name):
    if not isinstance(name, str):
        return ""

    cleaned = " ".join(name.split())

    if not cleaned:
        return ""

    return GENRE_CANONICAL_NAMES.get(
        cleaned.casefold(),
        cleaned,
    )


def canonical_feature_key(name):
    if not isinstance(name, str):
        return ""

    return " ".join(name.split()).casefold()


class _CheckListItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 26))
        return size


class _SearchableCheckList(QWidget):
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._available = []
        self._selected = set()
        self._syncing = False

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")

        self.list_widget = QListWidget()
        self.list_widget.setUniformItemSizes(False)
        self.list_widget.setItemDelegate(_CheckListItemDelegate(self.list_widget))
        self.list_widget.itemChanged.connect(self._item_changed)
        self.search_box.textChanged.connect(self._apply_search)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.search_box)
        layout.addWidget(self.list_widget)

    def selected(self):
        return set(self._selected)

    def set_selected(self, values):
        self._selected = set(values) & set(self._available)
        self._rebuild()

    def set_available(self, values):
        previous = set(self._selected)
        self._available = sorted(set(values), key=str.casefold)
        self._selected = previous & set(self._available)
        self._rebuild()

    def clear_selection(self):
        if not self._selected:
            return

        self._selected.clear()
        self._rebuild()
        self.selection_changed.emit()

    def _rebuild(self):
        search_text = self.search_box.text().strip().casefold()
        self._syncing = True

        try:
            self.list_widget.clear()

            for value in self._available:
                if search_text and search_text not in value.casefold():
                    continue

                item = QListWidgetItem(value)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if value in self._selected
                    else Qt.CheckState.Unchecked
                )
                self.list_widget.addItem(item)

            self.list_widget.doItemsLayout()

        finally:
            self._syncing = False

    def _apply_search(self, _text):
        self._rebuild()

    def _item_changed(self, item):
        if self._syncing:
            return

        if item.checkState() == Qt.CheckState.Checked:
            self._selected.add(item.text())
        else:
            self._selected.discard(item.text())

        self.selection_changed.emit()


class GenreTagFilterWidget(QWidget):
    filters_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._available_game_genres = []
        self._available_software_genres = []
        self._available_tags = []

        self._selected_game_genres = set()
        self._selected_software_genres = set()
        self._selected_tags = set()

        self._software_exclusive_genre_keys = set()
        self._software_exclusive_tag_keys = set()

        self.filter_button = QPushButton("Genres / Tags")
        self.filter_button.clicked.connect(self._open_dialog)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter_button)

    def selected_game_genres(self):
        return tuple(sorted(self._selected_game_genres, key=str.casefold))

    def selected_software_genres(self):
        return tuple(sorted(self._selected_software_genres, key=str.casefold))

    def selected_genres(self):
        return tuple(
            sorted(
                self._selected_game_genres | self._selected_software_genres,
                key=str.casefold,
            )
        )

    def selected_tags(self):
        return tuple(sorted(self._selected_tags, key=str.casefold))

    def has_active_filters(self):
        return bool(
            self._selected_game_genres
            or self._selected_software_genres
            or self._selected_tags
        )

    def clear_filters(self):
        if not self.has_active_filters():
            return

        self._selected_game_genres.clear()
        self._selected_software_genres.clear()
        self._selected_tags.clear()
        self._update_button_text()
        self.filters_changed.emit()

    def set_available_from_games(self, games):
        games = list(games)

        official_game_genres = {}
        official_software_genres = {}
        official_game_tags = {}
        official_software_tags = {}

        for game in games:
            raw_type = getattr(game, "steam_type", "unknown") or "unknown"

            if raw_type not in {"game", "software"}:
                continue

            genre_target = (
                official_game_genres if raw_type == "game" else official_software_genres
            )
            tag_target = (
                official_game_tags if raw_type == "game" else official_software_tags
            )

            for genre in getattr(game, "genres", []) or []:
                display = canonical_genre_name(genre)

                if display:
                    genre_target.setdefault(
                        canonical_feature_key(display),
                        display,
                    )

            for tag in getattr(game, "tags", {}) or {}:
                display = " ".join(tag.split())

                if display:
                    tag_target.setdefault(
                        canonical_feature_key(display),
                        display,
                    )

        game_genre_keys = set(official_game_genres)
        software_genre_keys = set(official_software_genres)
        game_tag_keys = set(official_game_tags)
        software_tag_keys = set(official_software_tags)

        self._software_exclusive_genre_keys = software_genre_keys - game_genre_keys
        self._software_exclusive_tag_keys = software_tag_keys - game_tag_keys

        game_genres = dict(official_game_genres)
        software_genres = {
            key: official_software_genres[key]
            for key in self._software_exclusive_genre_keys
        }
        all_tags = {
            **official_game_tags,
            **official_software_tags,
        }

        for game in games:
            inferred_type = self.inferred_steam_type(game)

            if inferred_type == "game":
                for genre in getattr(game, "genres", []) or []:
                    display = canonical_genre_name(genre)

                    if display:
                        game_genres.setdefault(
                            canonical_feature_key(display),
                            display,
                        )

            elif inferred_type == "software":
                for genre in getattr(game, "genres", []) or []:
                    display = canonical_genre_name(genre)
                    key = canonical_feature_key(display)

                    if key in self._software_exclusive_genre_keys:
                        software_genres.setdefault(key, display)

            for tag in getattr(game, "tags", {}) or {}:
                display = " ".join(tag.split())

                if display:
                    all_tags.setdefault(
                        canonical_feature_key(display),
                        display,
                    )

        self.set_available_options(
            game_genres.values(),
            software_genres.values(),
            all_tags.values(),
        )

    def set_available_options(self, game_genres, software_genres, tags):
        game_genres = {
            canonical_genre_name(value)
            for value in game_genres
            if canonical_genre_name(value)
        }
        software_genres = {
            canonical_genre_name(value)
            for value in software_genres
            if canonical_genre_name(value)
        }
        tags = {
            " ".join(value.split())
            for value in tags
            if isinstance(value, str) and value.strip()
        }

        self._selected_game_genres &= game_genres
        self._selected_software_genres &= software_genres
        self._selected_tags &= tags

        self._available_game_genres = sorted(game_genres, key=str.casefold)
        self._available_software_genres = sorted(
            software_genres,
            key=str.casefold,
        )
        self._available_tags = sorted(tags, key=str.casefold)
        self._update_button_text()

    def inferred_steam_type(self, game):
        raw_type = getattr(game, "steam_type", "unknown") or "unknown"

        if raw_type != "unknown":
            return raw_type

        if not getattr(game, "metadata_checked", False):
            return "unknown"

        genre_keys = {
            canonical_feature_key(canonical_genre_name(genre))
            for genre in getattr(game, "genres", []) or []
            if canonical_genre_name(genre)
        }
        tag_keys = {
            canonical_feature_key(tag)
            for tag in getattr(game, "tags", {}) or {}
            if canonical_feature_key(tag)
        }

        if (
            genre_keys & self._software_exclusive_genre_keys
            or tag_keys & self._software_exclusive_tag_keys
        ):
            return "software"

        return "game"

    def display_steam_type(self, game):
        raw_type = getattr(game, "steam_type", "unknown") or "unknown"

        if raw_type == "unknown":
            inferred = self.inferred_steam_type(game)

            if inferred == "game":
                return "Unknown (Game)"

            if inferred == "software":
                return "Unknown (Software)"

            return "Unknown"

        names = {
            "game": "Game",
            "software": "Software",
            "dlc": "DLC",
            "video": "Video",
            "hardware": "Hardware",
        }

        return names.get(raw_type, raw_type.replace("_", " ").title())

    def matches_type_filter(self, game, selected_type):
        if selected_type == "All Types":
            return True

        raw_type = getattr(game, "steam_type", "unknown") or "unknown"
        inferred_type = self.inferred_steam_type(game)

        if selected_type == "Game":
            return inferred_type == "game"

        if selected_type == "Unknown (Game)":
            return raw_type == "unknown" and inferred_type == "game"

        if selected_type == "Software":
            return inferred_type == "software"

        if selected_type == "Unknown (Software)":
            return raw_type == "unknown" and inferred_type == "software"

        if selected_type == "Unknown":
            return raw_type == "unknown" and inferred_type == "unknown"

        type_values = {
            "DLC": "dlc",
            "Video": "video",
            "Hardware": "hardware",
        }

        wanted_type = type_values.get(selected_type)

        if wanted_type is None:
            return False

        return raw_type == wanted_type

    def is_backlog_eligible(self, game):
        return self.inferred_steam_type(game) not in {
            "software",
            "dlc",
            "video",
            "hardware",
        }

    def matches_game(self, game):
        return self.matches(
            getattr(game, "genres", []) or [],
            getattr(game, "tags", {}) or {},
            self.inferred_steam_type(game),
        )

    def matches(self, genres, tags, steam_type):
        genre_keys = {
            canonical_feature_key(canonical_genre_name(genre))
            for genre in genres
            if canonical_genre_name(genre)
        }
        tag_keys = {
            canonical_feature_key(tag) for tag in tags if canonical_feature_key(tag)
        }

        selected_game_genre_keys = {
            canonical_feature_key(canonical_genre_name(genre))
            for genre in self._selected_game_genres
        }
        selected_software_genre_keys = {
            canonical_feature_key(canonical_genre_name(genre))
            for genre in self._selected_software_genres
        }
        selected_tag_keys = {canonical_feature_key(tag) for tag in self._selected_tags}

        if selected_game_genre_keys:
            if steam_type != "game":
                return False

            if not selected_game_genre_keys.issubset(genre_keys):
                return False

        if selected_software_genre_keys:
            if steam_type != "software":
                return False

            if not selected_software_genre_keys.issubset(genre_keys):
                return False

        return not (selected_tag_keys and not selected_tag_keys.issubset(tag_keys))

    def _open_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Genres / Tags")
        dialog.resize(520, 560)

        layout = QVBoxLayout(dialog)
        tabs = QTabWidget(dialog)

        game_genres = _SearchableCheckList(tabs)
        software_genres = _SearchableCheckList(tabs)
        tags = _SearchableCheckList(tabs)

        game_genres.set_available(self._available_game_genres)
        software_genres.set_available(self._available_software_genres)
        tags.set_available(self._available_tags)

        game_genres.set_selected(self._selected_game_genres)
        software_genres.set_selected(self._selected_software_genres)
        tags.set_selected(self._selected_tags)

        tabs.addTab(game_genres, "Game Genres")
        tabs.addTab(software_genres, "Software Genres")
        tabs.addTab(tags, "Tags")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
            | QDialogButtonBox.StandardButton.Reset
        )
        buttons.button(QDialogButtonBox.StandardButton.Reset).setText("Clear Filters")
        layout.addWidget(buttons)

        def sync_selection():
            self._selected_game_genres = game_genres.selected()
            self._selected_software_genres = software_genres.selected()
            self._selected_tags = tags.selected()
            self._update_button_text()
            self.filters_changed.emit()

        game_genres.selection_changed.connect(sync_selection)
        software_genres.selection_changed.connect(sync_selection)
        tags.selection_changed.connect(sync_selection)

        def clear_all():
            game_genres.clear_selection()
            software_genres.clear_selection()
            tags.clear_selection()

        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(clear_all)
        buttons.rejected.connect(dialog.reject)

        dialog.exec()

    def _update_button_text(self):
        selected_count = (
            len(self._selected_game_genres)
            + len(self._selected_software_genres)
            + len(self._selected_tags)
        )

        if selected_count:
            self.filter_button.setText(f"Genres / Tags ({selected_count})")
        else:
            self.filter_button.setText("Genres / Tags")
