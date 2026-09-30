from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SettingsTab(QWidget):
    def __init__(self, steam_id=None, parent=None):
        super().__init__(parent)

        if steam_id is None:
            account_text = "Steam account: Not set"
        else:
            account_text = f"Steam account: {steam_id}"

        self.account_label = QLabel(account_text)

        self.clear_images_button = QPushButton("Clear Image Cache")

        self.reset_database_button = QPushButton("Reset Local Database")

        layout = QVBoxLayout(self)

        layout.addWidget(self.account_label)
        layout.addWidget(self.clear_images_button)
        layout.addWidget(self.reset_database_button)
        layout.addStretch()
