from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


def repolish(widget):
    style = widget.style()

    if style is None:
        return

    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_dynamic_property(widget, name, value):
    if widget.property(name) == value:
        return

    widget.setProperty(name, value)
    repolish(widget)


class BadgeLabel(QLabel):
    def __init__(self, text="", tone="neutral", parent=None):
        super().__init__(text, parent)

        self.setProperty("badge", True)
        self.setProperty("badgeTone", tone)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(24)

    def set_badge(self, text, tone=None, tooltip=None):
        self.setText(text)

        if tone is not None:
            set_dynamic_property(self, "badgeTone", tone)

        self.setToolTip(tooltip or "")


class SectionHeading(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)

        self.setProperty("sectionHeading", True)


class StatTile(QFrame):
    def __init__(self, label, value="-", parent=None):
        super().__init__(parent)

        self.setProperty("statTile", True)
        self.setMinimumWidth(105)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self.label = QLabel(label)
        self.label.setProperty("statLabel", True)

        self.value = QLabel(value)
        self.value.setProperty("statValue", True)
        self.value.setWordWrap(True)

        layout.addWidget(self.label)
        layout.addWidget(self.value)

    def set_value(self, value):
        self.value.setText(value)
