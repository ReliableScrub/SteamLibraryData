from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

DARK_COLORS = {
    "window": "#151a20",
    "surface": "#1b222b",
    "surface_alt": "#222b35",
    "surface_hover": "#2a3745",
    "input": "#10151b",
    "border": "#34414f",
    "border_strong": "#4b6074",
    "text": "#e6edf3",
    "muted": "#9aa8b7",
    "accent": "#58a6d6",
    "accent_hover": "#72bce8",
    "accent_pressed": "#397da8",
    "accent_soft": "#213b4d",
    "selection": "#294f6b",
    "disabled_bg": "#20262d",
    "disabled_text": "#687482",
    "positive": "#78d49a",
    "danger": "#e4737b",
    "danger_bg": "#472a2e",
    "danger_hover": "#603238",
    "warning": "#e2b968",
}

LIGHT_COLORS = {
    "window": "#d6dde4",
    "surface": "#eef2f5",
    "surface_alt": "#e1e7ec",
    "surface_hover": "#d2e1eb",
    "input": "#f8fafb",
    "border": "#a9b6c1",
    "border_strong": "#7d92a4",
    "text": "#1b2731",
    "muted": "#596a78",
    "accent": "#1976b9",
    "accent_hover": "#278fd0",
    "accent_pressed": "#125d91",
    "accent_soft": "#cbdfea",
    "selection": "#b8d9ec",
    "disabled_bg": "#d5dce2",
    "disabled_text": "#7f8c97",
    "positive": "#247b47",
    "danger": "#a93d48",
    "danger_bg": "#ecd5d8",
    "danger_hover": "#e1bec2",
    "warning": "#87600f",
}


STYLE_TEMPLATE = r"""
QMainWindow#mainWindow,
QDialog {
    background-color: @WINDOW@;
    color: @TEXT@;
}

QToolTip {
    color: @TEXT@;
    background-color: @SURFACE_ALT@;
    border: 1px solid @BORDER_STRONG@;
    padding: 5px 7px;
}

QTabWidget#mainTabs::pane {
    border: 1px solid @BORDER@;
    border-radius: 7px;
    background-color: @SURFACE@;
    top: -1px;
}

QTabWidget#mainTabs > QTabBar::tab {
    color: @MUTED@;
    background: transparent;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 10px 18px;
    margin-right: 2px;
    font-weight: 600;
}

QTabWidget#mainTabs > QTabBar::tab:hover {
    color: @TEXT@;
    background-color: @SURFACE_HOVER@;
    border-bottom-color: @BORDER_STRONG@;
}

QTabWidget#mainTabs > QTabBar::tab:selected {
    color: @TEXT@;
    background-color: @SURFACE@;
    border-bottom-color: @ACCENT@;
}

QPushButton {
    color: @TEXT@;
    background-color: @SURFACE_ALT@;
    border: 1px solid @BORDER@;
    border-radius: 6px;
    padding: 7px 12px;
    min-height: 18px;
}

QPushButton:hover {
    color: @TEXT@;
    background-color: @SURFACE_HOVER@;
    border-color: @ACCENT@;
}

QPushButton:pressed {
    background-color: @ACCENT_SOFT@;
    border-color: @ACCENT_PRESSED@;
}

QPushButton:focus {
    border-color: @ACCENT@;
}

QPushButton:disabled {
    color: @DISABLED_TEXT@;
    background-color: @DISABLED_BG@;
    border-color: @BORDER@;
}

QPushButton[role="primary"] {
    color: #ffffff;
    background-color: @ACCENT_PRESSED@;
    border-color: @ACCENT@;
    font-weight: 600;
}

QPushButton[role="primary"]:hover {
    background-color: @ACCENT@;
    border-color: @ACCENT_HOVER@;
}

QPushButton[role="primary"]:pressed {
    background-color: @ACCENT_PRESSED@;
    border-color: @ACCENT_PRESSED@;
}

QPushButton[role="danger"] {
    color: @DANGER@;
    background-color: @DANGER_BG@;
    border-color: @DANGER@;
}

QPushButton[role="danger"]:hover {
    color: @TEXT@;
    background-color: @DANGER_HOVER@;
    border-color: @DANGER@;
}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox,
QDateEdit,
QTimeEdit,
QDateTimeEdit {
    color: @TEXT@;
    background-color: @INPUT@;
    border: 1px solid @BORDER@;
    border-radius: 5px;
    padding: 5px 7px;
    selection-background-color: @ACCENT@;
    selection-color: #ffffff;
}

QLineEdit:hover,
QComboBox:hover,
QSpinBox:hover,
QDoubleSpinBox:hover,
QDateEdit:hover,
QTimeEdit:hover,
QDateTimeEdit:hover {
    border-color: @BORDER_STRONG@;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QDateEdit:focus,
QTimeEdit:focus,
QDateTimeEdit:focus {
    border-color: @ACCENT@;
}

QComboBox {
    padding-right: 24px;
}

QComboBox QAbstractItemView {
    color: @TEXT@;
    background-color: @SURFACE@;
    border: 1px solid @BORDER_STRONG@;
    selection-background-color: @SELECTION@;
    selection-color: @TEXT@;
    outline: 0;
}

QTextEdit,
QPlainTextEdit,
QTextBrowser,
QListView,
QTreeView,
QTableView {
    color: @TEXT@;
    background-color: @INPUT@;
    alternate-background-color: @SURFACE@;
    border: 1px solid @BORDER@;
    border-radius: 6px;
    selection-background-color: @SELECTION@;
    selection-color: @TEXT@;
}

QTableView {
    gridline-color: @BORDER@;
    outline: 0;
}

QTableView::item,
QListView::item,
QTreeView::item {
    padding: 4px 6px;
}

QTableView::item:hover,
QListView::item:hover,
QTreeView::item:hover {
    background-color: @SURFACE_HOVER@;
}

QTableView::item:selected,
QListView::item:selected,
QTreeView::item:selected {
    background-color: @SELECTION@;
    color: @TEXT@;
}

QHeaderView::section {
    color: @TEXT@;
    background-color: @SURFACE_ALT@;
    border: none;
    border-right: 1px solid @BORDER@;
    border-bottom: 1px solid @BORDER@;
    padding: 7px 6px;
    font-weight: 600;
}

QHeaderView::section:hover {
    background-color: @SURFACE_HOVER@;
}

QGroupBox {
    color: @TEXT@;
    background-color: @SURFACE@;
    border: 1px solid @BORDER@;
    border-radius: 7px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: @TEXT@;
    background-color: @SURFACE@;
}

QProgressBar {
    color: @TEXT@;
    background-color: @INPUT@;
    border: 1px solid @BORDER@;
    border-radius: 5px;
    text-align: center;
    min-height: 18px;
}

QProgressBar::chunk {
    background-color: @ACCENT@;
    border-radius: 4px;
}

QSlider::groove:horizontal {
    height: 5px;
    background-color: @BORDER@;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background-color: @ACCENT@;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    width: 15px;
    margin: -5px 0;
    background-color: @TEXT@;
    border: 2px solid @ACCENT@;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background-color: @ACCENT_HOVER@;
    border-color: @ACCENT_HOVER@;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}

QScrollBar:vertical:disabled {
    background: transparent;
}

QScrollBar::handle:vertical {
    background: @BORDER_STRONG@;
    min-height: 28px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: @ACCENT@;
}

QScrollBar::handle:vertical:disabled {
    background: transparent;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 2px;
}

QScrollBar::handle:horizontal {
    background: @BORDER_STRONG@;
    min-width: 28px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: @ACCENT@;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    width: 0;
}

QCheckBox,
QRadioButton {
    color: @TEXT@;
    spacing: 7px;
}

QCheckBox:hover,
QRadioButton:hover {
    color: @ACCENT_HOVER@;
}

QSplitter::handle {
    background-color: @BORDER@;
}

QSplitter::handle:hover {
    background-color: @ACCENT@;
}

QStatusBar {
    color: @MUTED@;
    background-color: @SURFACE@;
    border-top: 1px solid @BORDER@;
}

QMenu {
    color: @TEXT@;
    background-color: @SURFACE@;
    border: 1px solid @BORDER_STRONG@;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px 6px 10px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: @SELECTION@;
}

QLabel[status="positive"] {
    color: @POSITIVE@;
    font-weight: 600;
}

QLabel[status="warning"] {
    color: @WARNING@;
    font-weight: 600;
}

QLabel[status="danger"] {
    color: @DANGER@;
    font-weight: 600;
}

QFrame[card="true"] {
    background-color: @SURFACE@;
    border: 1px solid @BORDER@;
    border-radius: 8px;
}
"""


def _make_palette(colors):
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["input"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(colors["danger"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["muted"]))
    return palette


def _build_stylesheet(colors):
    stylesheet = STYLE_TEMPLATE

    for name, value in colors.items():
        stylesheet = stylesheet.replace(f"@{name.upper()}@", value)

    return stylesheet


def apply_theme(
    app: QApplication,
    appearance: str,
    system_style_name: str,
    system_palette: QPalette,
):
    if appearance == "System":
        app.setStyleSheet("")
        system_style = QStyleFactory.create(system_style_name)

        if system_style is not None:
            app.setStyle(system_style)

        app.setPalette(system_palette)
        return

    colors = LIGHT_COLORS if appearance == "Light" else DARK_COLORS

    app.setStyle("Fusion")
    app.setPalette(_make_palette(colors))
    app.setStyleSheet(_build_stylesheet(colors))
