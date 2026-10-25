from PySide6.QtCore import QObject, QRunnable, Signal

from api.store_api import get_short_description
from storage.database import save_steam_short_description


class StoreDescriptionSignals(QObject):
    loaded = Signal(int, str)
    failed = Signal(int, str)


class StoreDescriptionWorker(QRunnable):
    def __init__(self, app_id):
        super().__init__()

        self.app_id = app_id
        self.signals = StoreDescriptionSignals()

    def run(self):
        try:
            description = get_short_description(self.app_id)
            save_steam_short_description(self.app_id, description)
        except Exception as error:  # noqa: BLE001
            self.signals.failed.emit(
                self.app_id,
                f"{type(error).__name__}: {error}",
            )
            return

        self.signals.loaded.emit(self.app_id, description)
