from datetime import UTC, datetime
from typing import ClassVar

from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from api.hltb_api import is_friends_pass_title, is_non_main_hltb_title


class GameTableModel(QAbstractTableModel):
    HEADERS: ClassVar[tuple[str, ...]] = (
        "Game",
        "Status",
        "Steam Playtime",
        "Last Played",
        "Rating",
        "HLTB Time",
        "Achievements",
        "Steam Type",
    )

    def __init__(self, games=None, parent=None):
        super().__init__(parent)

        self.games = games or []
        self.steam_type_resolver = None
        self.ratings = {}
        self.hltb_metric = "Main Story"
        self.sort_column = None
        self.header_font_point_size = None

    def rowCount(self, parent=None):
        return len(self.games)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def _hltb_missing_label(self, game):
        name = getattr(game, "name", "") or ""

        if is_friends_pass_title(name) or is_non_main_hltb_title(name):
            return "Skipped"

        if self.steam_type_resolver is not None:
            display_type = self.steam_type_resolver(game)
            non_hltb_types = {
                "Software",
                "Unknown (Software)",
                "DLC",
                "Video",
                "Hardware",
                "Test / Beta",
                "Unknown (Test / Beta)",
                "Bonus Content",
            }

            if display_type in non_hltb_types:
                return "Skipped"

        if not getattr(game, "hltb_checked", False):
            return "Not Checked"

        status = getattr(game, "hltb_match_status", None)

        if status == "review":
            return "Review"

        if status == "no_match":
            return "Not Found"

        if status == "matched":
            return "N/A"

        return "Unknown"

    def hltb_display_text(self, game, metric=None, long_unit=False):
        if metric is None:
            metric = self.hltb_metric

        hltb_time = game.hltb_time(metric)

        if hltb_time is None:
            return self._hltb_missing_label(game)

        unit = "hours" if long_unit else "h"
        return f"{hltb_time:.1f} {unit}"

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        column = index.column()

        if role == Qt.ItemDataRole.BackgroundRole and column == self.sort_column:
            color = QColor(QApplication.palette().color(QPalette.ColorRole.Highlight))
            color.setAlpha(30)
            return QBrush(color)

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        game = self.games[index.row()]

        if column == 0:
            return game.name

        if column == 1:
            return game.effective_status()

        if column == 2:
            playtime_hours = game.playtime_minutes / 60
            return f"{playtime_hours:.1f} h"

        if column == 3:
            timestamp = game.last_played_timestamp or 0

            if timestamp > 0:
                return (
                    datetime.fromtimestamp(
                        timestamp,
                        tz=UTC,
                    )
                    .astimezone()
                    .strftime("%b %d, %Y")
                )

            return "Never"

        if column == 4:
            rating = self.ratings.get(game.app_id)

            if rating is None:
                return "-"

            return "★" * rating

        if column == 5:
            return self.hltb_display_text(game)

        if column == 6:
            if game.achievement_total is None or game.achievements_unlocked is None:
                return "Unknown"

            if game.achievement_total == 0:
                return "None"

            return f"{game.achievements_unlocked}/{game.achievement_total}"

        if column == 7:
            display_type = None

            if self.steam_type_resolver is not None:
                display_type = self.steam_type_resolver(game)

            if display_type in {"Test / Beta", "Unknown (Test / Beta)"}:
                return display_type

            if game.classification_updated_at is None:
                return "Not Checked"

            if display_type is not None:
                return display_type

            steam_type_names = {
                "game": "Game",
                "software": "Software",
                "dlc": "DLC",
                "video": "Video",
                "hardware": "Hardware",
                "unknown": "Unknown",
            }

            return steam_type_names.get(game.steam_type, "Unknown")

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                if section == 5:
                    return f"HLTB ({self.hltb_metric})"

                return self.HEADERS[section]

            if section == self.sort_column:
                if role == Qt.ItemDataRole.ForegroundRole:
                    return QBrush(
                        QApplication.palette().color(QPalette.ColorRole.Highlight)
                    )

                if role == Qt.ItemDataRole.BackgroundRole:
                    color = QColor(
                        QApplication.palette().color(QPalette.ColorRole.Highlight)
                    )
                    color.setAlpha(55)
                    return QBrush(color)

                if role == Qt.ItemDataRole.FontRole:
                    font = QFont(QApplication.font())

                    if self.header_font_point_size is not None:
                        font.setPointSize(self.header_font_point_size)

                    font.setBold(True)
                    return font

            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return section + 1

        return None

    def set_games(self, games):
        self.beginResetModel()
        self.games = games
        self.endResetModel()

    def game_at(self, row):
        if 0 <= row < len(self.games):
            return self.games[row]

        return None

    def set_sort_column(self, column):
        if column == self.sort_column:
            return

        previous = self.sort_column
        self.sort_column = column

        changed_sections = [
            section for section in (previous, column) if isinstance(section, int)
        ]

        for section in changed_sections:
            self.headerDataChanged.emit(
                Qt.Orientation.Horizontal,
                section,
                section,
            )

        if self.games:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self.games) - 1, self.columnCount() - 1),
                [Qt.ItemDataRole.BackgroundRole],
            )

    def set_hltb_metric(self, metric):
        if self.hltb_metric == metric:
            return

        self.hltb_metric = metric

        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            5,
            5,
        )

        if self.games:
            self.dataChanged.emit(
                self.index(0, 5),
                self.index(len(self.games) - 1, 5),
            )

    def set_ratings(self, ratings):
        self.ratings = dict(ratings or {})

        if not self.games:
            return

        self.dataChanged.emit(
            self.index(0, 4),
            self.index(
                len(self.games) - 1,
                4,
            ),
        )

    def set_header_font_point_size(self, point_size):
        if point_size == self.header_font_point_size:
            return

        self.header_font_point_size = point_size
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            0,
            self.columnCount() - 1,
        )

    def set_steam_type_resolver(self, resolver):
        self.steam_type_resolver = resolver
