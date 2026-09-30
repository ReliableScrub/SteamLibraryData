from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QWidget,
)


class DataUpdatesTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._review_available = False
        self._busy = False

        self._create_controls()
        self._create_layout()

    def _create_controls(self):
        self.update_all_status = QLabel('Missing Data')
        self.update_all_button = QPushButton('Update Missing Data')
        self.cancel_updates_button = QPushButton('Cancel Updates')

        self.cancel_updates_button.setEnabled(False)

        self.update_all_progress = QProgressBar()

        self.update_all_progress.setVisible(False)
        self.update_all_progress.setFormat('%v / %m')

        self.library_status = QLabel()
        self.library_button = QPushButton('Refresh Steam Library')
        self.library_progress = QProgressBar()

        self.library_progress.setRange(0, 0)
        self.library_progress.setTextVisible(False)
        self.library_progress.setVisible(False)

        self.steam_classification_status = QLabel()
        self.steam_classification_button = QPushButton('Refresh Steam Classification')
        self.steam_classification_progress = QProgressBar()

        self.steam_classification_progress.setRange(0, 0)
        self.steam_classification_progress.setTextVisible(False)
        self.steam_classification_progress.setVisible(False)

        self.hltb_status = QLabel()
        self.hltb_button = QPushButton('Update HLTB Data')
        self.hltb_progress = QProgressBar()

        self.hltb_progress.setVisible(False)
        self.hltb_progress.setFormat('%v / %m')

        self.hltb_review_button = QPushButton('Review HLTB Matches')

        self.hltb_review_button.setEnabled(False)

        self.metadata_status = QLabel()
        self.metadata_button = QPushButton('Update Genre / Tag Data')
        self.metadata_progress = QProgressBar()

        self.metadata_progress.setVisible(False)
        self.metadata_progress.setFormat('%v / %m')

        self.achievement_status = QLabel()
        self.achievement_button = QPushButton('Update Achievement Data')
        self.achievement_progress = QProgressBar()

        self.achievement_progress.setVisible(False)
        self.achievement_progress.setFormat('%v / %m')

    def _create_layout(self):
        layout = QGridLayout(self)

        layout.addWidget(self.update_all_status, 0, 0)
        layout.addWidget(self.update_all_progress, 0, 1)

        update_all_buttons = QHBoxLayout()

        update_all_buttons.addWidget(self.update_all_button)
        update_all_buttons.addWidget(self.cancel_updates_button)
        layout.addLayout(update_all_buttons, 0, 2)

        layout.addWidget(self.library_status, 1, 0)
        layout.addWidget(self.library_progress, 1, 1)
        layout.addWidget(self.library_button, 1, 2)
        layout.addWidget(self.steam_classification_status, 2, 0)

        layout.addWidget(self.steam_classification_progress, 2, 1)
        layout.addWidget(self.steam_classification_button, 2, 2)
        layout.addWidget(self.hltb_status, 3, 0)
        layout.addWidget(self.hltb_progress, 3, 1)

        hltb_buttons = QHBoxLayout()

        hltb_buttons.addWidget(self.hltb_button)
        hltb_buttons.addWidget(self.hltb_review_button)
        layout.addLayout(hltb_buttons, 3, 2)

        layout.addWidget(self.metadata_status, 4, 0)
        layout.addWidget(self.metadata_progress, 4, 1)
        layout.addWidget(self.metadata_button, 4, 2)
        layout.addWidget(self.achievement_status, 5, 0)

        layout.addWidget(self.achievement_progress, 5, 1)
        layout.addWidget(self.achievement_button, 5, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        layout.setColumnStretch(2, 1)
        layout.setRowStretch(6, 1)

    def set_status(self, source, text):
        labels = {'all': self.update_all_status, 'library': self.library_status, 'classification': self.steam_classification_status, 'hltb': self.hltb_status, 'metadata': self.metadata_status, 'achievements': self.achievement_status}
        label = labels.get(source)

        if label is not None:
            label.setText(text)

    def set_progress(self, source, completed, total, visible):
        bars = {'all': self.update_all_progress, 'library': self.library_progress, 'classification': self.steam_classification_progress, 'hltb': self.hltb_progress, 'metadata': self.metadata_progress, 'achievements': self.achievement_progress}
        bar = bars.get(source)

        if bar is None:
            return

        bar.setVisible(visible)

        if not visible:
            return

        if source in {'library', 'classification'}:
            bar.setRange(0, 0)

            return

        bar.setRange(0, total)
        bar.setValue(completed)

    def set_review_available(self, available):
        self._review_available = available

        self.hltb_review_button.setEnabled(available and (not self._busy))

    def set_busy(self, busy):
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
