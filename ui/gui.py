import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from api.steam_api import (
    SteamApiKeyRejected,
    SteamApiValidationError,
    validate_steam_api_key,
)
from storage.credentials import set_steam_api_key
from storage.database import (
    delete_database,
    get_database_steam_id,
    set_database_steam_id,
)
from storage.image_cache import clear_image_cache
from storage.settings import (
    get_steam_id as get_saved_steam_id,
)
from storage.settings import (
    set_steam_id as save_steam_id,
)
from ui.library_tab import LibraryTab
from ui.settings_tab import SettingsTab
from ui.update_controller import UpdateController
from ui.updates_tab import DataUpdatesTab

OFFICIAL_REPOSITORY_URL = "https://github.com/ReliableScrub/SteamLibraryData"
DISCUSSIONS_URL = f"{OFFICIAL_REPOSITORY_URL}/discussions"
ISSUES_URL = f"{OFFICIAL_REPOSITORY_URL}/issues/new"
BUY_ME_A_COFFEE_URL = "https://www.buymeacoffee.com/ReliableScrub"


def open_external_url(url):
    QDesktopServices.openUrl(QUrl(url))


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

    def _create_contact_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("<h2>Contact</h2>")
        layout.addWidget(title)

        description = QLabel(
            "Steam Backlog DB is an open-source desktop application for "
            "organizing and enriching your Steam library."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        repository_heading = QLabel("<b>Official Project</b>")
        layout.addWidget(repository_heading)

        repository_text = QLabel(
            "Source code, documentation, and official project information "
            "are available on GitHub."
        )
        repository_text.setWordWrap(True)
        layout.addWidget(repository_text)

        repository_link = QLabel(
            f'<a href="{OFFICIAL_REPOSITORY_URL}">{OFFICIAL_REPOSITORY_URL}</a>'
        )
        repository_link.setOpenExternalLinks(True)
        repository_link.setWordWrap(True)
        layout.addWidget(repository_link)

        repository_button = QPushButton("Open GitHub Repository")
        repository_button.clicked.connect(
            lambda checked=False: open_external_url(OFFICIAL_REPOSITORY_URL)
        )
        layout.addWidget(repository_button)

        feedback_heading = QLabel("<b>Feedback & Suggestions</b>")
        layout.addWidget(feedback_heading)

        feedback_text = QLabel(
            "Have an idea, suggestion, or general feedback about the application? "
            "Use GitHub Discussions."
        )
        feedback_text.setWordWrap(True)
        layout.addWidget(feedback_text)

        feedback_button = QPushButton("Open GitHub Discussions")
        feedback_button.clicked.connect(
            lambda checked=False: open_external_url(DISCUSSIONS_URL)
        )
        layout.addWidget(feedback_button)

        issues_heading = QLabel("<b>Bug Reports</b>")
        layout.addWidget(issues_heading)

        issues_text = QLabel(
            "If something is not working correctly, open a GitHub Issue so "
            "the problem can be tracked."
        )
        issues_text.setWordWrap(True)
        layout.addWidget(issues_text)

        issues_button = QPushButton("Report an Issue")
        issues_button.clicked.connect(
            lambda checked=False: open_external_url(ISSUES_URL)
        )
        layout.addWidget(issues_button)

        support_heading = QLabel("<b>Support Development</b>")
        layout.addWidget(support_heading)

        support_text = QLabel(
            "If you like using this and want to support me in general, you can buy me a coffee. We run on it. Sadly."
        )
        support_text.setWordWrap(True)
        layout.addWidget(support_text)

        support_button = QPushButton("Buy Me a Coffee")
        support_button.clicked.connect(
            lambda checked=False: open_external_url(BUY_ME_A_COFFEE_URL)
        )
        layout.addWidget(support_button)

        layout.addStretch()

        return tab

    def _create_tabs(self):
        self.tabs = QTabWidget()
        self.library_tab = LibraryTab(self.games, self)
        self.updates_tab = DataUpdatesTab(self)
        saved_steam_id = get_saved_steam_id()

        if saved_steam_id is None:
            saved_steam_id = get_database_steam_id()

        self.settings_tab = SettingsTab(saved_steam_id, self)
        self.contact_tab = self._create_contact_tab()

        self.tabs.addTab(self.library_tab, "Library")
        self.tabs.addTab(self.updates_tab, "Data Updates")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.tabs.addTab(self.contact_tab, "Contact")

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

        saved_steam_id = get_saved_steam_id()

        if saved_steam_id is None:
            saved_steam_id = get_database_steam_id()

            if saved_steam_id is not None:
                save_steam_id(saved_steam_id)

        if saved_steam_id is not None:
            try:
                set_database_steam_id(saved_steam_id)
            except ValueError as error:
                QMessageBox.warning(
                    self,
                    "Steam Account",
                    str(error),
                )
                return None

            self.steam_id = saved_steam_id
            return self.steam_id

        steam_id, accepted = QInputDialog.getText(
            self,
            "Steam ID",
            "Enter your SteamID64:",
        )

        if not accepted:
            return None

        steam_id = steam_id.strip()

        if not steam_id.isdigit():
            QMessageBox.warning(
                self,
                "Invalid Steam ID",
                "SteamID64 must contain only numbers.",
            )
            return None

        try:
            set_database_steam_id(steam_id)
            save_steam_id(steam_id)
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Steam Account",
                str(error),
            )
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


def prompt_for_steam_api_key():
    dialog = QDialog()
    dialog.setWindowTitle("Steam Web API Key Required")
    dialog.setMinimumWidth(600)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(14)

    heading = QLabel("<h2>Steam Backlog DB needs a Steam Web API key</h2>")
    heading.setWordWrap(True)
    layout.addWidget(heading)

    explanation = QLabel(
        "The Steam Backlog DB uses the Steam Web API to import your owned games, "
        "retrieve achievement information, and access other Steam library data."
        "<br><br>"
        "<b>This is not your Steam password.</b> Steam Backlog DB will never "
        "ask for or store your Steam password."
        "<br><br>"
        "Your API key is stored using your operating system's credential store. "
        "It is not stored in the Steam Backlog database or in settings.json."
    )
    explanation.setWordWrap(True)
    layout.addWidget(explanation)

    usage_note = QLabel(
        "<b>What does Steam Backlog DB do with the key?</b><br>"
        "The key is used to authenticate requests made to Steam's Web API. "
        "Doing so will give us the ability to fill up the database with all current information"
        "on the spot."
    )
    usage_note.setWordWrap(True)
    layout.addWidget(usage_note)

    security_note = QLabel(
        "<b>Security note:</b> Only enter an API key into a copy of "
        "Steam Backlog DB that you trust.<br><br>"
        "The official source code for this project is available at:<br>"
        f'<a href="{OFFICIAL_REPOSITORY_URL}">{OFFICIAL_REPOSITORY_URL}</a>'
        "<br><br>"
        "If you downloaded this application from somewhere else, verify "
        "the source before entering a credential."
    )
    security_note.setWordWrap(True)
    security_note.setOpenExternalLinks(True)
    layout.addWidget(security_note)

    api_help = QLabel(
        "Use a <b>standard Steam Web API user key</b>. You can create or "
        "view one at "
        '<a href="https://steamcommunity.com/dev/apikey">'
        "Steam Web API Key Registration</a>."
    )
    api_help.setWordWrap(True)
    api_help.setOpenExternalLinks(True)
    layout.addWidget(api_help)

    api_key_input = QLineEdit()
    api_key_input.setPlaceholderText("Enter your Steam Web API key")
    api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(api_key_input)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(buttons)

    def save_api_key():
        api_key = api_key_input.text().strip()

        if not api_key:
            QMessageBox.warning(
                dialog,
                "Steam API Key",
                "Steam API key cannot be empty.",
            )
            return

        try:
            validate_steam_api_key(api_key)

        except SteamApiKeyRejected as error:
            QMessageBox.warning(
                dialog,
                "Steam Rejected API Key",
                str(error),
            )
            return

        except SteamApiValidationError as error:
            result = QMessageBox.question(
                dialog,
                "Could Not Verify API Key",
                f"{error}\n\n"
                "This does not necessarily mean the key is invalid. "
                "Steam may be unavailable or your internet connection may "
                "be offline.\n\n"
                "Save the key anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if result != QMessageBox.StandardButton.Yes:
                return

        try:
            set_steam_api_key(api_key)
        except RuntimeError as error:
            QMessageBox.critical(
                dialog,
                "Credential Storage Error",
                str(error),
            )
            return

        dialog.accept()

    buttons.accepted.connect(save_api_key)
    buttons.rejected.connect(dialog.reject)

    result = dialog.exec()

    if result != QDialog.DialogCode.Accepted:
        return None

    return api_key_input.text().strip()


def run_gui(games, steam_api_key):
    app = QApplication(sys.argv)

    if not steam_api_key:
        steam_api_key = prompt_for_steam_api_key()

        if steam_api_key is None:
            return

    window = MainWindow(games, steam_api_key)

    window.show()
    app.exec()
