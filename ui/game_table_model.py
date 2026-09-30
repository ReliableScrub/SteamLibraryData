from datetime import datetime, timezone
from typing import ClassVar

from PySide6.QtCore import QAbstractTableModel, Qt


class GameTableModel(QAbstractTableModel):
    HEADERS: ClassVar[tuple[str, ...]] = (
        "Game",
        "Status",
        "Steam Playtime",
        "Last Played",
        "Recent",
        "HLTB Time",
        "Achievements",
        "Steam Type",
    )

    def __init__(self, games=None, parent=None):
        super().__init__(parent)

        self.games = games or []
        self.hltb_metric = "Main Story"

    def rowCount(self, parent=None):
        return len(self.games)

    def columnCount(self, parent=None):
        return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        game = self.games[index.row()]
        column = index.column()

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
                        tz=timezone.utc,
                    )
                    .astimezone()
                    .strftime("%b %d, %Y")
                )

            return "Never"

        if column == 4:
            recent_minutes = game.playtime_2weeks_minutes or 0

            if recent_minutes == 0:
                return "-"

            if recent_minutes >= 60:
                return f"{recent_minutes / 60:.1f} h"

            return f"{recent_minutes} min"

        if column == 5:
            hltb_time = game.hltb_time(self.hltb_metric)

            if hltb_time is None:
                return "Unknown"

            return f"{hltb_time:.1f} h"

        if column == 6:
            if game.achievement_total is None or game.achievements_unlocked is None:
                return "Unknown"

            if game.achievement_total == 0:
                return "None"

            return f"{game.achievements_unlocked}/{game.achievement_total}"

        if column == 7:
            if game.classification_updated_at is None:
                return "Not Checked"

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
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if section == 5:
                return f"HLTB ({self.hltb_metric})"

            return self.HEADERS[section]

        return section + 1

    def set_games(self, games):
        self.beginResetModel()
        self.games = games
        self.endResetModel()

    def game_at(self, row):
        if 0 <= row < len(self.games):
            return self.games[row]

        return None

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
