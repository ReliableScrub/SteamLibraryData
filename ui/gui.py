import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from storage.database import (
    delete_database,
    get_database_steam_id,
    set_database_steam_id,
)
from storage.image_cache import clear_image_cache
from ui.library_tab import LibraryTab
from ui.settings_tab import SettingsTab
from ui.update_controller import UpdateController
from ui.updates_tab import DataUpdatesTab


class MainWindow(QMainWindow):
    def __init__(self, games, steam_api_key):
        super().__init__()

        self.games = games
        self.steam_api_key = steam_api_key
        self.steam_id = None
        self.close_after_updates_stop = False
        self.update_controller = UpdateController(self.games, self.steam_api_key, self)

        self.setWindowTitle("Steam Backlog")
        self.resize(1100, 700)
        self._create_tabs()

        self._bind_tabs()
        self._bind_update_controller()
        self.update_controller.refresh_statuses()

        if not self.games:
            QTimer.singleShot(0, self.first_run_setup)

    def _create_tabs(self):
        self.tabs = QTabWidget()
        self.library_tab = LibraryTab(self.games, self)
        self.updates_tab = DataUpdatesTab(self)
        self.settings_tab = SettingsTab(get_database_steam_id(), self)

        self.tabs.addTab(self.library_tab, "Library")
        self.tabs.addTab(self.updates_tab, "Data Updates")
        self.tabs.addTab(self.settings_tab, "Settings")

        self.setCentralWidget(self.tabs)

    def _bind_tabs(self):
        self.library_tab.data_changed.connect(self.update_controller.refresh_statuses)
        self.updates_tab.library_button.clicked.connect(self.start_library_refresh)
        self.updates_tab.steam_classification_button.clicked.connect(
            self.start_steam_classification
        )
        self.updates_tab.hltb_button.clicked.connect(self.start_hltb_update)

        self.updates_tab.hltb_review_button.clicked.connect(
            self.library_tab.review_hltb_matches
        )
        self.updates_tab.metadata_button.clicked.connect(self.start_metadata_update)
        self.updates_tab.achievement_button.clicked.connect(
            self.start_achievement_update
        )
        self.updates_tab.update_all_button.clicked.connect(
            self.start_missing_data_update
        )

        self.updates_tab.cancel_updates_button.clicked.connect(self.cancel_updates)
        self.settings_tab.clear_images_button.clicked.connect(self.clear_cached_images)
        self.settings_tab.reset_database_button.clicked.connect(self.reset_database)

    def _bind_update_controller(self):
        self.update_controller.status_changed.connect(self.updates_tab.set_status)
        self.update_controller.progress_changed.connect(self.updates_tab.set_progress)
        self.update_controller.busy_changed.connect(self._update_busy_state)
        self.update_controller.review_available_changed.connect(
            self.updates_tab.set_review_available
        )

        self.update_controller.games_changed.connect(self._games_changed)
        self.update_controller.data_changed.connect(self.library_tab.refresh_data)
        self.update_controller.error.connect(self._show_update_error)
        self.update_controller.item_failed.connect(print)

    def _update_busy_state(self, busy):
        self.updates_tab.set_busy(busy)
        self.settings_tab.reset_database_button.setEnabled(not busy)

    def _games_changed(self, games):
        self.games = games

        self.library_tab.set_games(games)

    def _show_update_error(self, title, message):
        QMessageBox.warning(self, title, message)

    def start_library_refresh(self):
        steam_id = self.get_steam_id()

        if steam_id is None:
            return

        self.update_controller.start_library_refresh(steam_id)

    def start_steam_classification(self):
        result = self.update_controller.start_classification()

        if result == "nothing":
            QMessageBox.information(
                self,
                "Steam Classification",
                "There are no Steam library entries to classify.",
            )

    def start_hltb_update(self):
        result = self.update_controller.start_hltb_batch()

        if result == "nothing":
            QMessageBox.information(
                self, "HLTB", "All games have already been checked."
            )

    def start_metadata_update(self):
        result = self.update_controller.start_metadata_batch()

        if result == "nothing":
            QMessageBox.information(
                self, "Metadata", "All games already have genre/tag data."
            )

    def start_achievement_update(self):
        if self.update_controller.achievement_pending_count() == 0:
            QMessageBox.information(
                self, "Achievements", "There are no games that need achievement data."
            )

            return

        steam_id = self.get_steam_id()

        if steam_id is None:
            return

        self.update_controller.start_achievement_batch(steam_id)

    def start_missing_data_update(self):
        if not self.update_controller.has_missing_data():
            QMessageBox.information(
                self, "Missing Data", "All games have already been checked."
            )

            return

        steam_id = None

        if self.update_controller.missing_data_needs_steam_id():
            steam_id = self.get_steam_id()

            if steam_id is None:
                return

        self.update_controller.start_all_missing(steam_id)

    def cancel_updates(self):
        self.updates_tab.cancel_updates_button.setEnabled(False)
        self.update_controller.cancel()

    def get_steam_id(self):
        if self.steam_id is not None:
            return self.steam_id

        saved_steam_id = get_database_steam_id()

        if saved_steam_id is not None:
            self.steam_id = saved_steam_id

            return self.steam_id

        steam_id, accepted = QInputDialog.getText(
            self, "Steam ID", "Enter your SteamID64:"
        )

        if not accepted:
            return None

        steam_id = steam_id.strip()

        if not steam_id.isdigit():
            QMessageBox.warning(
                self, "Invalid Steam ID", "SteamID64 must contain only numbers."
            )

            return None

        try:
            set_database_steam_id(steam_id)
        except ValueError as error:
            QMessageBox.warning(self, "Steam Account", str(error))

            return None

        self.steam_id = steam_id

        self.settings_tab.account_label.setText(f"Steam account: {steam_id}")

        return self.steam_id

    def clear_cached_images(self):
        clear_image_cache()
        QMessageBox.information(
            self, "Image Cache", "Cached game images have been deleted."
        )

    def reset_database(self):
        result = QMessageBox.question(
            self,
            "Reset Local Database",
            "Delete all locally collected Steam, HLTB, SteamSpy, achievement, and cached image data?",
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        clear_image_cache()
        delete_database()
        QMessageBox.information(
            self,
            "Database Reset",
            "Local data has been deleted. The application will now close.",
        )

        QApplication.quit()

    def first_run_setup(self):
        result = QMessageBox.question(
            self,
            "Steam Library",
            "Your local library is empty. Import your Steam library now?",
        )

        if result == QMessageBox.StandardButton.Yes:
            self.start_library_refresh()

    def closeEvent(self, event):
        if self.update_controller.is_running():
            if not self.close_after_updates_stop:
                self.close_after_updates_stop = True

                self.update_controller.cancel()

            event.ignore()
            QTimer.singleShot(100, self.close)

            return

        self.library_tab.stop_trailer()
        event.accept()


def run_gui(games, steam_api_key):
    app = QApplication(sys.argv)
    window = MainWindow(games, steam_api_key)

    window.show()
    app.exec()
