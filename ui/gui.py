import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyleFactory,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from api.steam_api import (
    SteamApiError,
    SteamApiKeyRejected,
    validate_steam_account,
)
from storage.credentials import set_steam_api_key
from storage.database import (
    delete_database,
    get_database_steam_id,
    set_database_steam_id,
)
from storage.image_cache import clear_image_cache
from storage.settings import (
    get_appearance,
    set_appearance,
)
from storage.settings import (
    get_steam_id as get_saved_steam_id,
)
from storage.settings import (
    set_steam_id as save_steam_id,
)
from ui.library_tab import LibraryTab
from ui.maintenance_tab import MaintenanceTab
from ui.recommendations_tab import RecommendationsTab
from ui.update_controller import UpdateController
from ui.window_state import restore_window_state, save_window_state

OFFICIAL_REPOSITORY_URL = "https://github.com/ReliableScrub/SteamLibraryData"
DISCUSSIONS_URL = f"{OFFICIAL_REPOSITORY_URL}/discussions"
ISSUES_URL = f"{OFFICIAL_REPOSITORY_URL}/issues/new"
BUY_ME_A_COFFEE_URL = "https://www.buymeacoffee.com/ReliableScrub"


def open_external_url(url):
    QDesktopServices.openUrl(QUrl(url))


def apply_application_theme(app, appearance, system_style_name, system_palette):
    if appearance == "System":
        system_style = QStyleFactory.create(system_style_name)

        if system_style is not None:
            app.setStyle(system_style)

        app.setPalette(system_palette)
        return

    app.setStyle("Fusion")

    if appearance == "Light":
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

        app.setPalette(palette)
        return

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(37, 37, 38))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(235, 235, 235))
    palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(235, 235, 235))
    palette.setColor(QPalette.ColorRole.Text, QColor(235, 235, 235))
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 48))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(235, 235, 235))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150))

    app.setPalette(palette)


class MainWindow(QMainWindow):
    def __init__(
        self,
        games,
        steam_api_key,
        steam_id,
        system_style_name,
        system_palette,
    ):
        super().__init__()

        self.games = games
        self.steam_api_key = steam_api_key
        self.steam_id = steam_id
        self.system_style_name = system_style_name
        self.system_palette = system_palette
        self.appearance = get_appearance()
        self.close_after_updates_stop = False
        self.update_controller = UpdateController(
            self.games,
            self.steam_api_key,
            self,
        )

        self.setWindowTitle("Steam Backlog")
        self.setMinimumSize(1000, 650)
        self.start_maximized = restore_window_state(self)
        self._create_tabs()

        self._bind_tabs()
        self._bind_update_controller()
        self.update_controller.refresh_statuses()

        if not self.games:
            QTimer.singleShot(0, self.first_run_setup)
        else:
            QTimer.singleShot(0, self.start_startup_refresh)

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
            "Have an idea, suggestion, or general feedback about the "
            "application? Use GitHub Discussions."
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
            "If you like using this and want to support me in general, "
            "you can buy me a coffee. We run on it. Sadly."
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
        self.recommendations_tab = RecommendationsTab(self.games, self)
        self.maintenance_tab = MaintenanceTab(
            self.steam_id,
            bool(self.steam_api_key),
            self.appearance,
            self,
        )

        self.contact_tab = self._create_contact_tab()

        self.tabs.addTab(self.library_tab, "Library")
        self.tabs.addTab(self.recommendations_tab, "Recommendations")
        self.tabs.addTab(self.maintenance_tab, "Maintenance")
        self.tabs.addTab(self.contact_tab, "Contact")

        self.setCentralWidget(self.tabs)

    def _bind_tabs(self):
        self.library_tab.data_changed.connect(self._library_data_changed)
        self.recommendations_tab.build_busy_changed.connect(
            self._recommendation_busy_changed
        )

        self.maintenance_tab.library_button.clicked.connect(self.start_library_refresh)

        self.maintenance_tab.steam_classification_button.clicked.connect(
            self.start_steam_classification
        )

        self.maintenance_tab.hltb_button.clicked.connect(self.start_hltb_update)

        self.maintenance_tab.hltb_review_button.clicked.connect(
            self.library_tab.review_hltb_matches
        )

        self.maintenance_tab.metadata_button.clicked.connect(self.start_metadata_update)

        self.maintenance_tab.achievement_button.clicked.connect(
            self.start_achievement_update
        )

        self.maintenance_tab.update_all_button.clicked.connect(
            self.start_missing_data_update
        )

        self.maintenance_tab.cancel_updates_button.clicked.connect(self.cancel_updates)

        self.maintenance_tab.view_failures_button.clicked.connect(
            self.show_update_failures
        )

        self.maintenance_tab.change_steam_id_button.clicked.connect(
            self.change_steam_id
        )

        self.maintenance_tab.change_api_key_button.clicked.connect(self.change_api_key)

        self.maintenance_tab.clear_images_button.clicked.connect(
            self.clear_cached_images
        )

        self.maintenance_tab.reset_database_button.clicked.connect(self.reset_database)

        self.maintenance_tab.appearance_combo.currentTextChanged.connect(
            self.change_appearance
        )

    def _bind_update_controller(self):
        self.update_controller.status_changed.connect(self.maintenance_tab.set_status)

        self.update_controller.progress_changed.connect(
            self.maintenance_tab.set_progress
        )

        self.update_controller.busy_changed.connect(self._update_busy_state)

        self.update_controller.review_available_changed.connect(
            self.maintenance_tab.set_review_available
        )

        self.update_controller.games_changed.connect(self._games_changed)

        self.update_controller.data_changed.connect(self.library_tab.refresh_data)

        self.update_controller.error.connect(self._show_update_error)

        self.update_controller.failures_changed.connect(
            self.maintenance_tab.set_failures
        )

        self.update_controller.item_failed.connect(print)

    def _update_busy_state(self, busy):
        self.recommendations_tab.set_update_busy(busy)
        self.maintenance_tab.set_busy(
            busy or self.recommendations_tab.recommendation_build_running()
        )

    def _recommendation_busy_changed(self, busy):
        self.maintenance_tab.set_busy(
            busy or self.update_controller.is_running()
        )

    def _games_changed(self, games):
        self.games = games
        self.library_tab.set_games(games)
        self.recommendations_tab.set_games(games)

    def _show_update_error(self, title, message):
        QMessageBox.warning(
            self,
            title,
            message,
        )

    def show_update_failures(self):
        failures = self.update_controller.failures()

        if not failures:
            QMessageBox.information(
                self,
                "Update Failures",
                "There are no failures from the most recent update.",
            )
            return

        source_names = {
            "library": "Steam Library",
            "classification": "Steam Classification",
            "hltb": "HLTB",
            "metadata": "Genre / Tags",
            "achievements": "Achievements",
        }

        grouped = {}

        for failure in failures:
            source = failure.get("source", "update")
            grouped.setdefault(source, []).append(failure.get("message", ""))

        lines = []

        for source in (
            "library",
            "classification",
            "hltb",
            "metadata",
            "achievements",
            "update",
        ):
            messages = grouped.pop(source, [])

            if not messages:
                continue

            lines.append(source_names.get(source, source.title()))
            lines.append("-" * len(lines[-1]))

            for message in messages:
                lines.append(message)

            lines.append("")

        for source, messages in grouped.items():
            lines.append(source_names.get(source, source.title()))
            lines.append("-" * len(lines[-1]))

            for message in messages:
                lines.append(message)

            lines.append("")

        dialog = QDialog(self)
        dialog.setWindowTitle("Update Failures")
        dialog.resize(760, 480)

        layout = QVBoxLayout(dialog)

        heading = QLabel(
            f"<b>{len(failures)} failure"
            f"{'' if len(failures) == 1 else 's'} from the most recent update</b>"
        )
        layout.addWidget(heading)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText("\n".join(lines).rstrip())
        layout.addWidget(details, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def _library_data_changed(self):
        self.update_controller.refresh_statuses()
        self.recommendations_tab.refresh()

    def start_library_refresh(self):
        self.update_controller.start_library_refresh(self.steam_id)

    def start_startup_refresh(self):
        result = self.update_controller.start_startup_refresh(self.steam_id)

        if result not in {"started", "nothing"}:
            print(f"Startup refresh did not start: {result}")

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
                self,
                "HLTB",
                "All games have already been checked.",
            )

    def start_metadata_update(self):
        result = self.update_controller.start_metadata_batch()

        if result == "nothing":
            QMessageBox.information(
                self,
                "Metadata",
                "All games already have genre/tag data.",
            )

    def start_achievement_update(self):
        if self.update_controller.achievement_pending_count() == 0:
            QMessageBox.information(
                self,
                "Achievements",
                "There are no games that need achievement data.",
            )
            return

        self.update_controller.start_achievement_batch(self.steam_id)

    def start_missing_data_update(self):
        if not self.update_controller.has_missing_data():
            QMessageBox.information(
                self,
                "Missing Data",
                "All games have already been checked.",
            )
            return

        steam_id = None

        if self.update_controller.missing_data_needs_steam_id():
            steam_id = self.steam_id

        self.update_controller.start_all_missing(steam_id)

    def cancel_updates(self):
        self.maintenance_tab.cancel_updates_button.setEnabled(False)
        self.update_controller.cancel()

    def get_steam_id(self):
        return self.steam_id

    def change_steam_id(self):
        current_steam_id = self.steam_id

        steam_id, accepted = QInputDialog.getText(
            self,
            "Change SteamID64",
            "Enter the SteamID64 you want to use:",
            text=current_steam_id or "",
        )

        if not accepted:
            return

        steam_id = steam_id.strip()

        if not steam_id:
            QMessageBox.warning(
                self,
                "Invalid Steam ID",
                "SteamID64 cannot be empty.",
            )
            return

        if not steam_id.isdigit():
            QMessageBox.warning(
                self,
                "Invalid Steam ID",
                "SteamID64 must contain only numbers.",
            )
            return

        if steam_id == current_steam_id:
            QMessageBox.information(
                self,
                "Steam Account",
                "That SteamID64 is already configured.",
            )
            return

        try:
            valid_account = validate_steam_account(
                steam_id,
                self.steam_api_key,
            )

        except SteamApiKeyRejected as error:
            QMessageBox.warning(
                self,
                "Steam Rejected API Key",
                str(error),
            )
            return

        except SteamApiError as error:
            QMessageBox.warning(
                self,
                "Could Not Verify SteamID64",
                f"{error}\n\nThe Steam account has not been changed.",
            )
            return

        if not valid_account:
            QMessageBox.warning(
                self,
                "Steam Account Not Found",
                "Steam could not find an account with that SteamID64.\n\n"
                "Check the number and try again.",
            )
            return

        database_steam_id = get_database_steam_id()

        if database_steam_id is not None and database_steam_id != steam_id:
            result = QMessageBox.question(
                self,
                "Switch Steam Account",
                "The current local database belongs to a different Steam "
                "account.\n\n"
                "Switching accounts requires deleting the current local "
                "database so library data from the two accounts is not "
                "mixed.\n\n"
                "Your image cache will be kept.\n\n"
                "Switch accounts and reset the local database?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if result != QMessageBox.StandardButton.Yes:
                return

            delete_database()
            save_steam_id(steam_id)

            QMessageBox.information(
                self,
                "Steam Account Changed",
                "The SteamID64 has been changed and the old account's "
                "local database has been removed.\n\n"
                "The application will now close. On the next launch you "
                "can import the new Steam library.",
            )

            QApplication.quit()
            return

        try:
            set_database_steam_id(steam_id)
            save_steam_id(steam_id)

        except ValueError as error:
            QMessageBox.warning(
                self,
                "Steam Account",
                str(error),
            )
            return

        self.steam_id = steam_id
        self.maintenance_tab.set_steam_id(steam_id)

        QMessageBox.information(
            self,
            "Steam Account",
            "SteamID64 updated.",
        )

    def change_api_key(self):
        new_api_key = prompt_for_api_key_change(self.steam_id)

        if new_api_key is None:
            return

        try:
            set_steam_api_key(new_api_key)

        except RuntimeError as error:
            QMessageBox.critical(
                self,
                "Credential Storage Error",
                str(error),
            )
            return

        self.steam_api_key = new_api_key
        self.maintenance_tab.set_api_key_configured(True)

        QMessageBox.information(
            self,
            "Steam Web API Key Changed",
            "The new Steam Web API key has been saved securely.\n\n"
            "The application will now close so all Steam services use "
            "the new key when it is reopened.",
        )

        QApplication.quit()

    def change_appearance(self, appearance):
        self.appearance = appearance
        set_appearance(appearance)

        app = QApplication.instance()

        if app is None:
            return

        apply_application_theme(
            app,
            appearance,
            self.system_style_name,
            self.system_palette,
        )

        self.recommendations_tab.refresh_theme()

    def clear_cached_images(self):
        clear_image_cache()

        QMessageBox.information(
            self,
            "Image Cache",
            "Cached game images have been deleted.",
        )

    def reset_database(self):
        result = QMessageBox.question(
            self,
            "Reset Local Database",
            "Delete all locally collected Steam, HLTB, SteamSpy, "
            "achievement, and cached image data?",
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
            QTimer.singleShot(
                100,
                self.close,
            )
            return

        if self.recommendations_tab.recommendation_build_running():
            event.ignore()
            QTimer.singleShot(
                100,
                self.close,
            )
            return

        save_window_state(self)
        self.library_tab.stop_trailer()
        event.accept()


def prompt_for_steam_setup(
    existing_steam_id=None,
    existing_api_key=None,
):
    dialog = QDialog()
    dialog.setWindowTitle("Steam Setup")
    dialog.setMinimumWidth(600)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(14)

    heading = QLabel("<h2>Connect your Steam account</h2>")
    heading.setWordWrap(True)
    layout.addWidget(heading)

    explanation = QLabel(
        "Steam Backlog DB needs your <b>SteamID64</b> and a "
        "<b>Steam Web API key</b> to access your Steam library data."
        "<br><br>"
        "Both will be checked with Steam before anything is saved."
        "<br><br>"
        "<b>This is not your Steam password.</b> Steam Backlog DB "
        "will never ask for or store your Steam password."
    )
    explanation.setWordWrap(True)
    layout.addWidget(explanation)

    steam_id_label = QLabel("<b>SteamID64</b>")
    layout.addWidget(steam_id_label)

    steam_id_input = QLineEdit()
    steam_id_input.setPlaceholderText("Enter your SteamID64")

    if existing_steam_id:
        steam_id_input.setText(existing_steam_id)

    layout.addWidget(steam_id_input)

    api_key_label = QLabel("<b>Steam Web API Key</b>")
    layout.addWidget(api_key_label)

    api_key_input = QLineEdit()
    api_key_input.setPlaceholderText("Enter your Steam Web API key")
    api_key_input.setEchoMode(QLineEdit.EchoMode.Password)

    if existing_api_key:
        api_key_input.setText(existing_api_key)

    layout.addWidget(api_key_input)

    api_help = QLabel(
        "Use a <b>standard Steam Web API user key</b>. "
        "You can create or view one at "
        '<a href="https://steamcommunity.com/dev/apikey">'
        "Steam Web API Key Registration</a>."
    )
    api_help.setWordWrap(True)
    api_help.setOpenExternalLinks(True)
    layout.addWidget(api_help)

    storage_note = QLabel(
        "Your SteamID64 is stored as a normal application setting. "
        "Your API key is stored separately using your operating "
        "system's credential manager."
    )
    storage_note.setWordWrap(True)
    layout.addWidget(storage_note)

    security_note = QLabel(
        "<b>Security note:</b> Only enter an API key into a copy of "
        "Steam Backlog DB that you trust.<br><br>"
        "The official source code for this project is available at:<br>"
        f'<a href="{OFFICIAL_REPOSITORY_URL}">'
        f"{OFFICIAL_REPOSITORY_URL}</a>"
    )
    security_note.setWordWrap(True)
    security_note.setOpenExternalLinks(True)
    layout.addWidget(security_note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )

    verify_button = buttons.button(QDialogButtonBox.StandardButton.Save)
    verify_button.setText("Verify and Continue")

    layout.addWidget(buttons)

    verified_data = {}

    def verify_setup():
        steam_id = steam_id_input.text().strip()
        api_key = api_key_input.text().strip()

        if not steam_id:
            QMessageBox.warning(
                dialog,
                "Steam Setup",
                "SteamID64 cannot be empty.",
            )
            return

        if not steam_id.isdigit():
            QMessageBox.warning(
                dialog,
                "Steam Setup",
                "SteamID64 must contain only numbers.",
            )
            return

        if not api_key:
            QMessageBox.warning(
                dialog,
                "Steam Setup",
                "Steam Web API key cannot be empty.",
            )
            return

        try:
            valid_account = validate_steam_account(
                steam_id,
                api_key,
            )

        except SteamApiKeyRejected as error:
            QMessageBox.warning(
                dialog,
                "Steam Rejected API Key",
                str(error),
            )
            return

        except SteamApiError as error:
            QMessageBox.warning(
                dialog,
                "Could Not Verify Steam Setup",
                f"{error}\n\n"
                "Nothing has been saved. Check your connection and "
                "try again.",
            )
            return

        if not valid_account:
            QMessageBox.warning(
                dialog,
                "Steam Account Not Found",
                "Steam accepted the API key, but could not find an "
                "account with that SteamID64.\n\n"
                "Check the SteamID64 and try again.",
            )
            return

        verified_data["steam_id"] = steam_id
        verified_data["api_key"] = api_key

        dialog.accept()

    buttons.accepted.connect(verify_setup)

    buttons.rejected.connect(dialog.reject)

    result = dialog.exec()

    if result != QDialog.DialogCode.Accepted:
        return None

    return (
        verified_data["steam_id"],
        verified_data["api_key"],
    )


def prompt_for_api_key_change(steam_id):
    dialog = QDialog()
    dialog.setWindowTitle("Change Steam Web API Key")
    dialog.setMinimumWidth(550)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(14)

    heading = QLabel("<h2>Change Steam Web API Key</h2>")
    heading.setWordWrap(True)
    layout.addWidget(heading)

    explanation = QLabel(
        "Enter the new Steam Web API key. It will be checked against "
        "your configured Steam account before it is saved."
        "<br><br>"
        "<b>This is not your Steam password.</b>"
    )
    explanation.setWordWrap(True)
    layout.addWidget(explanation)

    api_help = QLabel(
        "You can create or view a standard Steam Web API key at "
        '<a href="https://steamcommunity.com/dev/apikey">'
        "Steam Web API Key Registration</a>."
    )
    api_help.setWordWrap(True)
    api_help.setOpenExternalLinks(True)
    layout.addWidget(api_help)

    api_key_input = QLineEdit()
    api_key_input.setPlaceholderText("Enter your new Steam Web API key")
    api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(api_key_input)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
    )

    verify_button = buttons.button(QDialogButtonBox.StandardButton.Save)
    verify_button.setText("Verify and Save")

    layout.addWidget(buttons)

    verified_key = {}

    def verify_key():
        api_key = api_key_input.text().strip()

        if not api_key:
            QMessageBox.warning(
                dialog,
                "Steam API Key",
                "Steam API key cannot be empty.",
            )
            return

        try:
            valid_account = validate_steam_account(
                steam_id,
                api_key,
            )

        except SteamApiKeyRejected as error:
            QMessageBox.warning(
                dialog,
                "Steam Rejected API Key",
                str(error),
            )
            return

        except SteamApiError as error:
            QMessageBox.warning(
                dialog,
                "Could Not Verify API Key",
                f"{error}\n\nThe API key has not been changed.",
            )
            return

        if not valid_account:
            QMessageBox.warning(
                dialog,
                "Steam Account Verification Failed",
                "Steam accepted the API key, but it could not verify "
                "the configured Steam account with that key.",
            )
            return

        verified_key["api_key"] = api_key
        dialog.accept()

    buttons.accepted.connect(verify_key)

    buttons.rejected.connect(dialog.reject)

    result = dialog.exec()

    if result != QDialog.DialogCode.Accepted:
        return None

    return verified_key["api_key"]


def run_gui(games, steam_api_key):
    app = QApplication(sys.argv)

    system_style_name = app.style().objectName()
    system_palette = QPalette(app.palette())

    appearance = get_appearance()

    apply_application_theme(
        app,
        appearance,
        system_style_name,
        system_palette,
    )

    saved_steam_id = get_saved_steam_id()
    database_steam_id = get_database_steam_id()

    if saved_steam_id is None and database_steam_id is not None:
        saved_steam_id = database_steam_id
        save_steam_id(saved_steam_id)

    if (
        saved_steam_id is not None
        and database_steam_id is not None
        and saved_steam_id != database_steam_id
    ):
        QMessageBox.critical(
            None,
            "Steam Account Mismatch",
            "The configured SteamID64 does not match the Steam account "
            "associated with the local database.\n\n"
            "SteamLibraryData will not open this database because doing "
            "so could mix data from two Steam accounts.",
        )
        return

    steam_id = saved_steam_id or database_steam_id

    if not steam_api_key or not steam_id:
        setup = prompt_for_steam_setup(
            existing_steam_id=steam_id,
            existing_api_key=steam_api_key,
        )

        if setup is None:
            return

        steam_id, steam_api_key = setup

        try:
            set_database_steam_id(steam_id)
            save_steam_id(steam_id)
            set_steam_api_key(steam_api_key)

        except (RuntimeError, ValueError, OSError) as error:
            QMessageBox.critical(
                None,
                "Steam Setup",
                "Steam Backlog DB could not save the verified "
                f"configuration:\n\n{error}",
            )
            return

    else:
        try:
            set_database_steam_id(steam_id)

        except ValueError as error:
            QMessageBox.critical(
                None,
                "Steam Account",
                str(error),
            )
            return

    window = MainWindow(
        games,
        steam_api_key,
        steam_id,
        system_style_name,
        system_palette,
    )

    if window.start_maximized:
        window.showMaximized()
    else:
        window.show()

    app.exec()
