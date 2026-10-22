from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

GENRE_ALIASES = {
    "free to play": "Free To Play",
}


def canonicalize_genre(genre):
    if not genre:
        return ""

    cleaned = genre.strip()

    return GENRE_ALIASES.get(cleaned.casefold(), cleaned)


class SearchableMultiSelectDialog(QDialog):
    def __init__(
        self,
        title,
        values,
        selected_values=None,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.resize(420, 520)

        self.values = list(values)
        self.initial_selected_values = set(selected_values or ())

        self._create_controls()
        self._create_layout()
        self._connect_signals()
        self._populate_list()

    def _create_controls(self):
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")

        self.list_widget = QListWidget()

        self.clear_button = QPushButton("Clear Selection")

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

    def _create_layout(self):
        layout = QVBoxLayout(self)

        layout.addWidget(self.search_box)
        layout.addWidget(self.list_widget, 1)
        layout.addWidget(self.clear_button)
        layout.addWidget(self.button_box)

    def _connect_signals(self):
        self.search_box.textChanged.connect(self._apply_search_filter)
        self.clear_button.clicked.connect(self._clear_selection)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(self._toggle_item)

    def _populate_list(self):
        self.list_widget.clear()

        for value in self.values:
            item = QListWidgetItem(value)

            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            if value in self.initial_selected_values:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

            self.list_widget.addItem(item)

    def _apply_search_filter(self, text):
        search_text = text.strip().casefold()

        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)

            item.setHidden(
                bool(search_text) and search_text not in item.text().casefold()
            )

    def _clear_selection(self):
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setCheckState(Qt.CheckState.Unchecked)

    def selected_values(self):
        selected = []

        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)

            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())

        return tuple(selected)

    def _toggle_item(self, item):
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)


class GenreSelectDialog(QDialog):
    def __init__(
        self,
        game_genres,
        software_genres,
        selected_game_genres=None,
        selected_software_genres=None,
        parent=None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Choose Genres")
        self.resize(520, 600)

        self._changing_selection = False

        selected_game_genres = set(selected_game_genres or ())

        selected_software_genres = set(selected_software_genres or ())

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search genres...")

        self.game_list = QListWidget()
        self.software_list = QListWidget()

        self.clear_button = QPushButton("Clear Selection")

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        for genre in game_genres:
            self._add_genre_item(
                self.game_list,
                genre,
                selected_game_genres,
            )

        for genre in software_genres:
            self._add_genre_item(
                self.software_list,
                genre,
                selected_software_genres,
            )

        layout = QVBoxLayout(self)

        layout.addWidget(self.search_box)

        layout.addWidget(QLabel("Game Genres"))
        layout.addWidget(self.game_list, 1)

        layout.addWidget(QLabel("Software Genres"))
        layout.addWidget(self.software_list, 1)

        layout.addWidget(self.clear_button)
        layout.addWidget(self.button_box)

        self.search_box.textChanged.connect(self._apply_search_filter)

        self.game_list.itemChanged.connect(
            lambda item: self._genre_checked(
                item,
                self.software_list,
            )
        )

        self.software_list.itemChanged.connect(
            lambda item: self._genre_checked(
                item,
                self.game_list,
            )
        )

        self.game_list.itemDoubleClicked.connect(self._toggle_item)

        self.software_list.itemDoubleClicked.connect(self._toggle_item)

        self.clear_button.clicked.connect(self._clear_selection)

        self.button_box.accepted.connect(self.accept)

        self.button_box.rejected.connect(self.reject)

    @staticmethod
    def _add_genre_item(
        list_widget,
        genre,
        selected_values,
    ):
        item = QListWidgetItem(genre)

        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

        if genre in selected_values:
            item.setCheckState(Qt.CheckState.Checked)
        else:
            item.setCheckState(Qt.CheckState.Unchecked)

        list_widget.addItem(item)

    def _genre_checked(
        self,
        item,
        other_list,
    ):
        if self._changing_selection:
            return

        if item.checkState() != Qt.CheckState.Checked:
            return

        self._changing_selection = True

        try:
            for index in range(other_list.count()):
                other_list.item(index).setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._changing_selection = False

    def _apply_search_filter(self, text):
        search_text = text.strip().casefold()

        for list_widget in (
            self.game_list,
            self.software_list,
        ):
            for index in range(list_widget.count()):
                item = list_widget.item(index)

                item.setHidden(
                    bool(search_text) and search_text not in item.text().casefold()
                )

    def _clear_selection(self):
        self._changing_selection = True

        try:
            for list_widget in (
                self.game_list,
                self.software_list,
            ):
                for index in range(list_widget.count()):
                    list_widget.item(index).setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._changing_selection = False

    def selected_game_genres(self):
        return self._selected_values(self.game_list)

    def selected_software_genres(self):
        return self._selected_values(self.software_list)

    @staticmethod
    def _selected_values(list_widget):
        selected = []

        for index in range(list_widget.count()):
            item = list_widget.item(index)

            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())

        return tuple(selected)

    @staticmethod
    def _toggle_item(item):
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)


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

        self._software_genre_keys = set()
        self._software_tag_keys = set()

        self._create_controls()
        self._create_layout()
        self._connect_signals()
        self._update_button_text()

    def _create_controls(self):
        self.genre_label = QLabel("Genre:")
        self.genre_button = QPushButton()

        self.genre_button.setToolTip("An entry must contain all selected genres.")

        self.tag_label = QLabel("Tags:")
        self.tag_button = QPushButton()

        self.tag_button.setToolTip("An entry must contain all selected tags.")

        self.clear_button = QPushButton("Clear")
        self.clear_button.setEnabled(False)

    def _create_layout(self):
        layout = QHBoxLayout(self)

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.addWidget(self.genre_label)
        layout.addWidget(self.genre_button)

        layout.addSpacing(8)

        layout.addWidget(self.tag_label)
        layout.addWidget(self.tag_button)

        layout.addWidget(self.clear_button)
        layout.addStretch()

    def _connect_signals(self):
        self.genre_button.clicked.connect(self._choose_genres)

        self.tag_button.clicked.connect(self._choose_tags)

        self.clear_button.clicked.connect(self.clear_filters)

    def set_available_options(
        self,
        game_genres,
        software_genres,
        tags,
    ):
        new_game_genres = sorted(
            {canonicalize_genre(genre) for genre in game_genres if genre},
            key=str.casefold,
        )

        game_genre_keys = {genre.casefold() for genre in new_game_genres}

        new_software_genres = sorted(
            {
                canonicalize_genre(genre)
                for genre in software_genres
                if genre and canonicalize_genre(genre).casefold() not in game_genre_keys
            },
            key=str.casefold,
        )

        new_tags = sorted(
            {tag for tag in tags if tag},
            key=str.casefold,
        )

        old_selected_game_genres = set(self._selected_game_genres)

        old_selected_software_genres = set(self._selected_software_genres)

        old_selected_tags = set(self._selected_tags)

        self._available_game_genres = new_game_genres

        self._available_software_genres = new_software_genres

        self._available_tags = new_tags

        self._selected_game_genres.intersection_update(new_game_genres)

        self._selected_software_genres.intersection_update(new_software_genres)

        self._selected_tags.intersection_update(new_tags)

        self._update_button_text()

        if (
            old_selected_game_genres != self._selected_game_genres
            or old_selected_software_genres != self._selected_software_genres
            or old_selected_tags != self._selected_tags
        ):
            self.filters_changed.emit()

    def set_available_from_games(self, games):
        official_game_genres = set()
        official_software_genres = set()

        official_game_tags = set()
        official_software_tags = set()

        all_tags = set()

        for game in games:
            genres = {
                canonicalize_genre(genre) for genre in (game.genres or []) if genre
            }

            tags = {tag for tag in (game.tags or {}) if tag}

            all_tags.update(tags)

            if game.steam_type == "game":
                official_game_genres.update(genres)

                official_game_tags.update(tags)

            elif game.steam_type == "software":
                official_software_genres.update(genres)

                official_software_tags.update(tags)

        game_genre_keys = {genre.casefold() for genre in official_game_genres}

        game_tag_keys = {tag.casefold() for tag in official_game_tags}

        self._software_genre_keys = {
            genre.casefold()
            for genre in official_software_genres
            if genre.casefold() not in game_genre_keys
        }

        self._software_tag_keys = {
            tag.casefold()
            for tag in official_software_tags
            if tag.casefold() not in game_tag_keys
        }

        game_genres = set(official_game_genres)

        software_genres = set(official_software_genres)

        for game in games:
            if game.steam_type != "unknown":
                continue

            inferred_type = self.inferred_steam_type(game)

            genres = {
                canonicalize_genre(genre) for genre in (game.genres or []) if genre
            }

            if inferred_type == "game":
                game_genres.update(genres)

            elif inferred_type == "software":
                software_genres.update(genres)

        self.set_available_options(
            game_genres,
            software_genres,
            all_tags,
        )

    def inferred_steam_type(self, game):
        if game.steam_type != "unknown":
            return game.steam_type

        if not getattr(
            game,
            "metadata_checked",
            False,
        ):
            return "unknown"

        genres = {
            canonicalize_genre(genre).casefold()
            for genre in (game.genres or [])
            if genre
        }

        tags = {tag.casefold() for tag in (game.tags or {}) if tag}

        if not genres and not tags:
            return "unknown"

        if genres & self._software_genre_keys:
            return "software"

        if tags & self._software_tag_keys:
            return "software"

        return "game"

    def display_steam_type(self, game):
        inferred_type = self.inferred_steam_type(game)

        type_names = {
            "game": "Game",
            "software": "Software",
            "dlc": "DLC",
            "video": "Video",
            "hardware": "Hardware",
            "unknown": "Unknown",
        }

        if game.steam_type == "unknown" and inferred_type == "game":
            return "Unknown (Game)"

        if game.steam_type == "unknown" and inferred_type == "software":
            return "Unknown (Software)"

        return type_names.get(
            game.steam_type,
            "Unknown",
        )

    def selected_genres(self):
        return tuple(
            sorted(
                self._selected_game_genres | self._selected_software_genres,
                key=str.casefold,
            )
        )

    def selected_tags(self):
        return tuple(
            sorted(
                self._selected_tags,
                key=str.casefold,
            )
        )

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

    def matches(
        self,
        genres,
        tags,
        steam_type=None,
    ):
        entry_genres = {canonicalize_genre(genre) for genre in (genres or []) if genre}

        if self._selected_game_genres:
            if steam_type != "game":
                return False

            if not self._selected_game_genres.issubset(entry_genres):
                return False

        if self._selected_software_genres:
            if steam_type != "software":
                return False

            if not self._selected_software_genres.issubset(entry_genres):
                return False

        if isinstance(tags, dict):
            entry_tags = set(tags.keys())
        else:
            entry_tags = set(tags or [])

        return not (
            self._selected_tags and not self._selected_tags.issubset(entry_tags)
        )

    def matches_game(self, game):
        return self.matches(
            game.genres,
            game.tags,
            self.inferred_steam_type(game),
        )

    def _choose_genres(self):
        dialog = GenreSelectDialog(
            game_genres=(self._available_game_genres),
            software_genres=(self._available_software_genres),
            selected_game_genres=(self._selected_game_genres),
            selected_software_genres=(self._selected_software_genres),
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_game_selection = set(dialog.selected_game_genres())

        new_software_selection = set(dialog.selected_software_genres())

        if (
            new_game_selection == self._selected_game_genres
            and new_software_selection == self._selected_software_genres
        ):
            return

        self._selected_game_genres = new_game_selection

        self._selected_software_genres = new_software_selection

        self._update_button_text()
        self.filters_changed.emit()

    def _choose_tags(self):
        dialog = SearchableMultiSelectDialog(
            title="Choose Tags",
            values=self._available_tags,
            selected_values=self._selected_tags,
            parent=self,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_selection = set(dialog.selected_values())

        if new_selection == self._selected_tags:
            return

        self._selected_tags = new_selection

        self._update_button_text()
        self.filters_changed.emit()

    def _update_button_text(self):
        if self._selected_game_genres:
            genre_text = self._selection_text(
                self._selected_game_genres,
                empty_text="Any Genre",
            )

            self.genre_button.setText(f"Game: {genre_text}")

        elif self._selected_software_genres:
            genre_text = self._selection_text(
                self._selected_software_genres,
                empty_text="Any Genre",
            )

            self.genre_button.setText(f"Software: {genre_text}")

        else:
            self.genre_button.setText("Any Genre")

        self.tag_button.setText(
            self._selection_text(
                self._selected_tags,
                empty_text="Any Tags",
            )
        )

        self.clear_button.setEnabled(self.has_active_filters())

    @staticmethod
    def _selection_text(
        selected_values,
        empty_text,
    ):
        if not selected_values:
            return empty_text

        sorted_values = sorted(
            selected_values,
            key=str.casefold,
        )

        if len(sorted_values) == 1:
            return sorted_values[0]

        return f"{sorted_values[0]} + {len(sorted_values) - 1}"
