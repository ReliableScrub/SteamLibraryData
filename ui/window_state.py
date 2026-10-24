from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from storage.settings import get_window_settings, set_window_settings

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 800
DEFAULT_SCREEN_RATIO = 0.90

MIN_WIDTH = 1000
MIN_HEIGHT = 650

MIN_VISIBLE_WIDTH = 160
MIN_VISIBLE_HEIGHT = 80


def _default_geometry():
    screen = QApplication.primaryScreen()

    if screen is None:
        return QRect(100, 100, DEFAULT_WIDTH, DEFAULT_HEIGHT)

    available = screen.availableGeometry()

    width = min(DEFAULT_WIDTH, int(available.width() * DEFAULT_SCREEN_RATIO))
    height = min(DEFAULT_HEIGHT, int(available.height() * DEFAULT_SCREEN_RATIO))

    width = max(MIN_WIDTH, width)
    height = max(MIN_HEIGHT, height)

    x = available.x() + (available.width() - width) // 2
    y = available.y() + (available.height() - height) // 2

    return QRect(x, y, width, height)


def _saved_geometry(settings):
    values = (
        settings.get("x"),
        settings.get("y"),
        settings.get("width"),
        settings.get("height"),
    )

    if not all(isinstance(value, int) for value in values):
        return None

    x, y, width, height = values

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return None

    return QRect(x, y, width, height)


def _best_screen(rect):
    best_screen = None
    best_area = 0

    for screen in QApplication.screens():
        available = screen.availableGeometry()
        intersection = rect.intersected(available)

        if (
            intersection.width() < MIN_VISIBLE_WIDTH
            or intersection.height() < MIN_VISIBLE_HEIGHT
        ):
            continue

        area = intersection.width() * intersection.height()

        if area > best_area:
            best_screen = screen
            best_area = area

    return best_screen


def _clamp_to_screen(rect, screen):
    available = screen.availableGeometry()

    width = min(rect.width(), available.width())
    height = min(rect.height(), available.height())

    width = max(MIN_WIDTH, width)
    height = max(MIN_HEIGHT, height)

    max_x = available.right() - width + 1
    max_y = available.bottom() - height + 1

    x = min(max(rect.x(), available.left()), max_x)
    y = min(max(rect.y(), available.top()), max_y)

    return QRect(x, y, width, height)


def restore_window_state(window):
    settings = get_window_settings()
    geometry = _saved_geometry(settings)

    if geometry is None:
        geometry = _default_geometry()
    else:
        screen = _best_screen(geometry)

        if screen is None:
            geometry = _default_geometry()
        else:
            geometry = _clamp_to_screen(geometry, screen)

    window.setGeometry(geometry)

    return settings.get("maximized") is True


def save_window_state(window):
    geometry = window.normalGeometry()

    set_window_settings(
        {
            "x": geometry.x(),
            "y": geometry.y(),
            "width": geometry.width(),
            "height": geometry.height(),
            "maximized": window.isMaximized(),
        }
    )
