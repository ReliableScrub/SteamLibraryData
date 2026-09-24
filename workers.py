from PySide6.QtCore import QObject, Signal, Slot

from api.steam_api import get_owned_games
from storage.database import save_game


class SteamLibraryRefreshWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, steam_id, steam_api_key):
        super().__init__()

        self.steam_id = steam_id
        self.steam_api_key = steam_api_key

    @Slot()
    def run(self):
        try:
            games = get_owned_games(self.steam_id, self.steam_api_key)

            self.succeeded.emit(games)

        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")

        finally:
            self.finished.emit()


class BatchUpdateWorker(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(int, int)
    item_failed = Signal(str)
    finished = Signal()

    def __init__(self, games, updater, task_name, action_text):
        super().__init__()

        self.games = games
        self.updater = updater
        self.task_name = task_name
        self.action_text = action_text

    @Slot()
    def run(self):
        total = len(self.games)

        try:
            for index, game in enumerate(self.games, start=1):
                self.status_changed.emit(f"{self.action_text} {game.name}...")

                try:
                    self.updater(game)
                    save_game(game)

                except Exception as error:
                    self.item_failed.emit(
                        f"{self.task_name} failed for {game.name}: "
                        f"{type(error).__name__}: {error}"
                    )

                self.progress_changed.emit(index, total)

        finally:
            self.finished.emit()
