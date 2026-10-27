import re

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.semantic_widgets import set_dynamic_property


class MaintenanceTab(QWidget):
    def __init__(
        self,
        steam_id=None,
        api_key_configured=False,
        appearance="System",
        parent=None,
    ):
        super().__init__(parent)

        self._review_available = False
        self._busy = False

        self._create_update_controls()
        self._create_settings_controls(
            steam_id,
            api_key_configured,
            appearance,
        )
        self._create_layout()

    def _create_update_controls(self):
        self.update_all_status = QLabel("Missing Data")
        self.update_all_button = QPushButton("Update Missing Data")
        self.cancel_updates_button = QPushButton("Cancel Updates")
        self.cancel_updates_button.setProperty("role", "warning")
        self.cancel_updates_button.setEnabled(False)

        self.view_failures_button = QPushButton("View Failures")
        self.view_failures_button.setVisible(False)
        self.view_failures_button.setEnabled(False)

        self.update_all_progress = QProgressBar()
        self.update_all_progress.setVisible(False)
        self.update_all_progress.setFormat("%v / %m")

        self.library_status = QLabel()
        self.library_button = QPushButton("Refresh Steam Library")

        self.library_progress = QProgressBar()
        self.library_progress.setRange(0, 0)
        self.library_progress.setTextVisible(False)
        self.library_progress.setVisible(False)

        self.steam_classification_status = QLabel()
        self.steam_classification_button = QPushButton("Refresh Steam Classification")

        self.steam_classification_progress = QProgressBar()
        self.steam_classification_progress.setRange(0, 0)
        self.steam_classification_progress.setTextVisible(False)
        self.steam_classification_progress.setVisible(False)

        self.hltb_status = QLabel()
        self.hltb_refresh_count = QComboBox()
        self.hltb_refresh_count.addItems(["10", "25", "50", "100", "All"])
        self.hltb_refresh_count.setCurrentText("25")
        self.hltb_refresh_count.setToolTip(
            "How many of the oldest checked HLTB entries to refresh."
        )
        self.hltb_refresh_button = QPushButton("Refresh Oldest")
        self.hltb_refresh_button.setToolTip(
            "Re-query the oldest checked HLTB entries. Pending review entries are skipped."
        )

        self.hltb_progress = QProgressBar()
        self.hltb_progress.setVisible(False)
        self.hltb_progress.setFormat("%v / %m")

        self.hltb_review_button = QPushButton("Review HLTB Matches")
        self.hltb_review_button.setProperty("role", "warning")
        self.hltb_review_button.setEnabled(False)

        self.metadata_status = QLabel()
        self.metadata_refresh_count = QComboBox()
        self.metadata_refresh_count.addItems(["25", "50", "100", "250", "All"])
        self.metadata_refresh_count.setCurrentText("100")
        self.metadata_refresh_count.setToolTip(
            "How many of the oldest checked SteamSpy metadata entries to refresh."
        )
        self.metadata_refresh_button = QPushButton("Refresh Oldest")
        self.metadata_refresh_button.setToolTip(
            "Refresh the oldest Genre / Tag / Public Reception entries first."
        )

        self.metadata_progress = QProgressBar()
        self.metadata_progress.setVisible(False)
        self.metadata_progress.setFormat("%v / %m")

        self.achievement_status = QLabel()
        self.achievement_refresh_button = QPushButton("Refresh Changed")
        self.achievement_refresh_button.setToolTip(
            "Refresh achievements only for games whose Steam playtime increased "
            "since their last achievement check."
        )

        self.achievement_progress = QProgressBar()
        self.achievement_progress.setVisible(False)
        self.achievement_progress.setFormat("%v / %m")

    def _create_settings_controls(
        self,
        steam_id,
        api_key_configured,
        appearance,
    ):
        self.account_label = QLabel()
        self.set_steam_id(steam_id)

        self.change_steam_id_button = QPushButton("Change SteamID64")

        self.api_key_label = QLabel()

        self.change_api_key_button = QPushButton("Change Steam Web API Key")
        self.remove_api_key_button = QPushButton("Remove Stored API Key")

        self.set_api_key_configured(api_key_configured)

        self.appearance_combo = QComboBox()
        self.appearance_combo.addItems(
            [
                "System",
                "Light",
                "Dark",
            ]
        )

        if appearance in {
            "System",
            "Light",
            "Dark",
        }:
            self.appearance_combo.setCurrentText(appearance)

        self.help_faq_button = QPushButton("Help / FAQ")
        self.help_faq_button.setToolTip(
            "Open setup help and answers for common SteamLibraryData issues."
        )

        self.clear_images_button = QPushButton("Clear Image Cache")

        self.reset_database_button = QPushButton("Reset Local Database")

    def _create_layout(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)

        page_header = QHBoxLayout()
        page_header.addWidget(QLabel("<h2>Maintenance</h2>"))
        page_header.addStretch()
        page_header.addWidget(self.help_faq_button)
        layout.addLayout(page_header)

        updates_card = QFrame()
        updates_card.setProperty("card", True)
        updates_card.setProperty("accentCard", True)
        updates_layout = QVBoxLayout(updates_card)
        updates_layout.setContentsMargins(18, 16, 18, 18)
        updates_layout.setSpacing(10)

        updates_heading = QLabel("<h2>Data Updates</h2>")
        updates_description = QLabel(
            "Refresh library data and maintain locally stored metadata."
        )
        updates_description.setWordWrap(True)

        updates_layout.addWidget(updates_heading)
        updates_layout.addWidget(updates_description)
        updates_layout.addSpacing(4)

        updates_grid = QGridLayout()
        updates_grid.setHorizontalSpacing(16)
        updates_grid.setVerticalSpacing(10)

        updates_grid.addWidget(self.update_all_status, 0, 0)
        updates_grid.addWidget(self.update_all_progress, 0, 1)

        update_all_buttons = QHBoxLayout()
        update_all_buttons.addWidget(self.update_all_button)
        update_all_buttons.addWidget(self.cancel_updates_button)
        update_all_buttons.addWidget(self.view_failures_button)
        updates_grid.addLayout(update_all_buttons, 0, 2)

        updates_grid.addWidget(self.library_status, 1, 0)
        updates_grid.addWidget(self.library_progress, 1, 1)
        updates_grid.addWidget(self.library_button, 1, 2)

        updates_grid.addWidget(self.steam_classification_status, 2, 0)
        updates_grid.addWidget(self.steam_classification_progress, 2, 1)
        updates_grid.addWidget(self.steam_classification_button, 2, 2)

        updates_grid.addWidget(self.hltb_status, 3, 0)
        updates_grid.addWidget(self.hltb_progress, 3, 1)

        hltb_buttons = QHBoxLayout()
        hltb_buttons.addWidget(QLabel("Refresh oldest:"))
        hltb_buttons.addWidget(self.hltb_refresh_count)
        hltb_buttons.addWidget(self.hltb_refresh_button)
        hltb_buttons.addWidget(self.hltb_review_button)
        updates_grid.addLayout(hltb_buttons, 3, 2)

        updates_grid.addWidget(self.metadata_status, 4, 0)
        updates_grid.addWidget(self.metadata_progress, 4, 1)

        metadata_buttons = QHBoxLayout()
        metadata_buttons.addWidget(QLabel("Refresh oldest:"))
        metadata_buttons.addWidget(self.metadata_refresh_count)
        metadata_buttons.addWidget(self.metadata_refresh_button)
        updates_grid.addLayout(metadata_buttons, 4, 2)

        updates_grid.addWidget(self.achievement_status, 5, 0)
        updates_grid.addWidget(self.achievement_progress, 5, 1)

        achievement_buttons = QHBoxLayout()
        achievement_buttons.addWidget(self.achievement_refresh_button)
        updates_grid.addLayout(achievement_buttons, 5, 2)

        updates_grid.setColumnStretch(0, 1)
        updates_grid.setColumnStretch(1, 1)
        updates_grid.setColumnStretch(2, 1)

        updates_layout.addLayout(updates_grid)
        layout.addWidget(updates_card)

        account_card = QFrame()
        account_card.setProperty("card", True)
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(18, 16, 18, 18)
        account_layout.setSpacing(10)

        account_layout.addWidget(QLabel("<h2>Steam Account</h2>"))
        account_layout.addWidget(self.account_label)
        account_layout.addWidget(self.change_steam_id_button)
        account_layout.addSpacing(4)
        account_layout.addWidget(QLabel("<b>Steam Web API</b>"))
        account_layout.addWidget(self.api_key_label)
        account_layout.addWidget(self.change_api_key_button)
        account_layout.addWidget(self.remove_api_key_button)
        layout.addWidget(account_card)

        application_card = QFrame()
        application_card.setProperty("card", True)
        application_layout = QVBoxLayout(application_card)
        application_layout.setContentsMargins(18, 16, 18, 18)
        application_layout.setSpacing(10)

        application_layout.addWidget(QLabel("<h2>Application</h2>"))

        appearance_row = QHBoxLayout()
        appearance_row.addWidget(QLabel("Appearance:"))
        appearance_row.addWidget(self.appearance_combo)
        appearance_row.addStretch()
        application_layout.addLayout(appearance_row)
        application_layout.addWidget(self.clear_images_button)
        layout.addWidget(application_card)

        danger_card = QFrame()
        danger_card.setProperty("card", True)
        danger_card.setProperty("dangerCard", True)
        danger_layout = QVBoxLayout(danger_card)
        danger_layout.setContentsMargins(18, 16, 18, 18)
        danger_layout.setSpacing(10)

        danger_layout.addWidget(QLabel("<h2>Danger Zone</h2>"))

        danger_description = QLabel(
            "Resetting the local database deletes "
            "collected Steam, HLTB, SteamSpy, "
            "achievement, rating, and recommendation "
            "data stored by the application."
        )
        danger_description.setWordWrap(True)

        danger_layout.addWidget(danger_description)
        danger_layout.addWidget(self.reset_database_button)
        layout.addWidget(danger_card)

        layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    @staticmethod
    def _refresh_limit(combo):
        value = combo.currentText().strip()

        if value == "All":
            return None

        return int(value)

    def metadata_refresh_limit(self):
        return self._refresh_limit(self.metadata_refresh_count)

    def hltb_refresh_limit(self):
        return self._refresh_limit(self.hltb_refresh_count)

    def set_steam_id(
        self,
        steam_id,
    ):
        if steam_id is None:
            self.account_label.setText("SteamID64: Not set")
        else:
            self.account_label.setText(f"SteamID64: {steam_id}")

    def set_api_key_configured(
        self,
        configured,
    ):
        self._api_key_configured = bool(configured)

        if self._api_key_configured:
            self.api_key_label.setText("Steam Web API key: Configured")
        else:
            self.api_key_label.setText("Steam Web API key: Not configured")

        if hasattr(self, "remove_api_key_button"):
            self.remove_api_key_button.setEnabled(
                self._api_key_configured and not self._busy
            )

    @staticmethod
    def _status_tone(source, text):
        lowered = text.lower()

        if "failed" in lowered or "error" in lowered:
            return "danger"

        if any(
            word in lowered
            for word in (
                "refreshing",
                "starting",
                "checking",
                "getting",
                "searching",
                "updating",
            )
        ):
            return "accent"

        if "cancelled" in lowered or "canceled" in lowered:
            return "warning"

        if source in {"metadata", "achievements"}:
            match = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", text)

            if match is not None:
                checked = int(match.group(1).replace(",", ""))
                total = int(match.group(2).replace(",", ""))

                return "positive" if total > 0 and checked >= total else "warning"

        if source == "hltb":
            review_match = re.search(r"(\d[\d,]*) review", lowered)
            pending_match = re.search(r"(\d[\d,]*) pending", lowered)
            review = (
                int(review_match.group(1).replace(",", ""))
                if review_match is not None
                else 0
            )
            pending = (
                int(pending_match.group(1).replace(",", ""))
                if pending_match is not None
                else 0
            )

            return "warning" if review > 0 or pending > 0 else "positive"

        if source == "classification":
            pending_match = re.search(r"(\d[\d,]*) pending", lowered)

            if "not checked" in lowered:
                return "warning"

            if pending_match is not None:
                pending = int(pending_match.group(1).replace(",", ""))

                if pending > 0:
                    return "warning"

            return "positive"

        if source == "all" and any(
            word in lowered for word in ("missing", "pending", "stale")
        ):
            return "warning"

        return "positive"

    def set_status(
        self,
        source,
        text,
    ):
        labels = {
            "all": self.update_all_status,
            "library": self.library_status,
            "classification": self.steam_classification_status,
            "hltb": self.hltb_status,
            "metadata": self.metadata_status,
            "achievements": self.achievement_status,
        }

        label = labels.get(source)

        if label is not None:
            label.setText(text)
            set_dynamic_property(
                label,
                "status",
                self._status_tone(source, text),
            )

    def set_progress(
        self,
        source,
        completed,
        total,
        visible,
    ):
        bars = {
            "all": self.update_all_progress,
            "library": self.library_progress,
            "classification": self.steam_classification_progress,
            "hltb": self.hltb_progress,
            "metadata": self.metadata_progress,
            "achievements": self.achievement_progress,
        }

        bar = bars.get(source)

        if bar is None:
            return

        bar.setVisible(visible)

        if not visible:
            return

        set_dynamic_property(bar, "tone", "accent")

        if source in {
            "library",
            "classification",
        }:
            bar.setRange(
                0,
                0,
            )
            return

        bar.setRange(
            0,
            total,
        )

        bar.setValue(completed)

    def set_failures(self, failures):
        count = len(failures)
        available = count > 0

        self.view_failures_button.setVisible(available)
        self.view_failures_button.setEnabled(available)
        set_dynamic_property(
            self.view_failures_button,
            "role",
            "danger" if available else "",
        )

        self.view_failures_button.setText(
            f"View Failures ({count})" if available else "View Failures"
        )

    def set_review_available(
        self,
        available,
    ):
        self._review_available = available

        self.hltb_review_button.setEnabled(available and not self._busy)

    def set_busy(
        self,
        busy,
    ):
        self._busy = busy
        enabled = not busy

        self.update_all_button.setEnabled(enabled)

        self.library_button.setEnabled(enabled)

        self.steam_classification_button.setEnabled(enabled)

        self.hltb_refresh_button.setEnabled(enabled)
        self.hltb_refresh_count.setEnabled(enabled)

        self.metadata_refresh_button.setEnabled(enabled)
        self.metadata_refresh_count.setEnabled(enabled)

        self.achievement_refresh_button.setEnabled(enabled)

        self.hltb_review_button.setEnabled(enabled and self._review_available)

        self.cancel_updates_button.setEnabled(busy)

        self.change_steam_id_button.setEnabled(enabled)

        self.change_api_key_button.setEnabled(enabled)
        self.remove_api_key_button.setEnabled(enabled and self._api_key_configured)

        self.reset_database_button.setEnabled(enabled)
