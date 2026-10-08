from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SettingsTab(QWidget):
    def __init__(self, steam_id=None, api_key_configured=False, parent=None):
        super().__init__(parent)

        if steam_id is None:
            account_text = "SteamID64: Not set"
        else:
            account_text = f"SteamID64: {steam_id}"

        self.account_label = QLabel(account_text)
        self.change_steam_id_button = QPushButton("Change SteamID64")

        if api_key_configured:
            api_key_text = "Steam Web API key: Configured"
        else:
            api_key_text = "Steam Web API key: Not configured"

        self.api_key_label = QLabel(api_key_text)
        self.change_api_key_button = QPushButton("Change Steam Web API Key")

        self.clear_images_button = QPushButton("Clear Image Cache")
        self.reset_database_button = QPushButton("Reset Local Database")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Steam Account</b>"))
        layout.addWidget(self.account_label)
        layout.addWidget(self.change_steam_id_button)

        layout.addSpacing(16)

        layout.addWidget(QLabel("<b>Steam Web API</b>"))
        layout.addWidget(self.api_key_label)
        layout.addWidget(self.change_api_key_button)

        layout.addSpacing(16)

        layout.addWidget(QLabel("<b>Local Data</b>"))
        layout.addWidget(self.clear_images_button)
        layout.addWidget(self.reset_database_button)

        layout.addStretch()

    def set_steam_id(self, steam_id):
        if steam_id is None:
            self.account_label.setText("SteamID64: Not set")
        else:
            self.account_label.setText(f"SteamID64: {steam_id}")

    def set_api_key_configured(self, configured):
        if configured:
            self.api_key_label.setText("Steam Web API key: Configured")
        else:
            self.api_key_label.setText("Steam Web API key: Not configured")
