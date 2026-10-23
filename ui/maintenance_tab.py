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
        self.cancel_updates_button.setEnabled(False)

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
        self.hltb_button = QPushButton("Update HLTB Data")

        self.hltb_progress = QProgressBar()
        self.hltb_progress.setVisible(False)
        self.hltb_progress.setFormat("%v / %m")

        self.hltb_review_button = QPushButton("Review HLTB Matches")
        self.hltb_review_button.setEnabled(False)

        self.metadata_status = QLabel()
        self.metadata_button = QPushButton("Update Genre / Tag Data")

        self.metadata_progress = QProgressBar()
        self.metadata_progress.setVisible(False)
        self.metadata_progress.setFormat("%v / %m")

        self.achievement_status = QLabel()
        self.achievement_button = QPushButton("Update Achievement Data")

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
        self.set_api_key_configured(api_key_configured)

        self.change_api_key_button = QPushButton("Change Steam Web API Key")

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

        self.clear_images_button = QPushButton("Clear Image Cache")

        self.reset_database_button = QPushButton("Reset Local Database")

    def _create_layout(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)

        layout.setContentsMargins(
            24,
            20,
            24,
            24,
        )

        layout.setSpacing(10)

        updates_heading = QLabel("<h2>Data Updates</h2>")

        updates_description = QLabel(
            "Refresh library data and maintain locally stored metadata."
        )
        updates_description.setWordWrap(True)

        layout.addWidget(updates_heading)
        layout.addWidget(updates_description)
        layout.addSpacing(6)

        updates_grid = QGridLayout()
        updates_grid.setHorizontalSpacing(16)
        updates_grid.setVerticalSpacing(10)

        updates_grid.addWidget(
            self.update_all_status,
            0,
            0,
        )

        updates_grid.addWidget(
            self.update_all_progress,
            0,
            1,
        )

        update_all_buttons = QHBoxLayout()
        update_all_buttons.addWidget(self.update_all_button)
        update_all_buttons.addWidget(self.cancel_updates_button)

        updates_grid.addLayout(
            update_all_buttons,
            0,
            2,
        )

        updates_grid.addWidget(
            self.library_status,
            1,
            0,
        )

        updates_grid.addWidget(
            self.library_progress,
            1,
            1,
        )

        updates_grid.addWidget(
            self.library_button,
            1,
            2,
        )

        updates_grid.addWidget(
            self.steam_classification_status,
            2,
            0,
        )

        updates_grid.addWidget(
            self.steam_classification_progress,
            2,
            1,
        )

        updates_grid.addWidget(
            self.steam_classification_button,
            2,
            2,
        )

        updates_grid.addWidget(
            self.hltb_status,
            3,
            0,
        )

        updates_grid.addWidget(
            self.hltb_progress,
            3,
            1,
        )

        hltb_buttons = QHBoxLayout()

        hltb_buttons.addWidget(self.hltb_button)

        hltb_buttons.addWidget(self.hltb_review_button)

        updates_grid.addLayout(
            hltb_buttons,
            3,
            2,
        )

        updates_grid.addWidget(
            self.metadata_status,
            4,
            0,
        )

        updates_grid.addWidget(
            self.metadata_progress,
            4,
            1,
        )

        updates_grid.addWidget(
            self.metadata_button,
            4,
            2,
        )

        updates_grid.addWidget(
            self.achievement_status,
            5,
            0,
        )

        updates_grid.addWidget(
            self.achievement_progress,
            5,
            1,
        )

        updates_grid.addWidget(
            self.achievement_button,
            5,
            2,
        )

        updates_grid.setColumnStretch(
            0,
            1,
        )

        updates_grid.setColumnStretch(
            1,
            1,
        )

        updates_grid.setColumnStretch(
            2,
            1,
        )

        layout.addLayout(updates_grid)

        layout.addSpacing(24)

        account_heading = QLabel("<h2>Steam Account</h2>")

        layout.addWidget(account_heading)
        layout.addWidget(self.account_label)
        layout.addWidget(self.change_steam_id_button)

        layout.addSpacing(12)

        layout.addWidget(QLabel("<b>Steam Web API</b>"))

        layout.addWidget(self.api_key_label)

        layout.addWidget(self.change_api_key_button)

        layout.addSpacing(24)

        application_heading = QLabel("<h2>Application</h2>")

        layout.addWidget(application_heading)

        appearance_row = QHBoxLayout()

        appearance_row.addWidget(QLabel("Appearance:"))

        appearance_row.addWidget(self.appearance_combo)

        appearance_row.addStretch()

        layout.addLayout(appearance_row)

        layout.addSpacing(8)

        layout.addWidget(self.clear_images_button)

        layout.addSpacing(24)

        danger_heading = QLabel("<h2>Danger Zone</h2>")

        danger_description = QLabel(
            "Resetting the local database deletes "
            "collected Steam, HLTB, SteamSpy, "
            "achievement, rating, and recommendation "
            "data stored by the application."
        )

        danger_description.setWordWrap(True)

        layout.addWidget(danger_heading)

        layout.addWidget(danger_description)

        layout.addWidget(self.reset_database_button)

        layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

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
        if configured:
            self.api_key_label.setText("Steam Web API key: Configured")
        else:
            self.api_key_label.setText("Steam Web API key: Not configured")

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

        self.hltb_button.setEnabled(enabled)

        self.metadata_button.setEnabled(enabled)

        self.achievement_button.setEnabled(enabled)

        self.hltb_review_button.setEnabled(enabled and self._review_available)

        self.cancel_updates_button.setEnabled(busy)

        self.change_steam_id_button.setEnabled(enabled)

        self.change_api_key_button.setEnabled(enabled)

        self.reset_database_button.setEnabled(enabled)
