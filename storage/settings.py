import json
import os
import time

from storage.paths import SETTINGS_FILE

VALID_APPEARANCES = {"System", "Light", "Dark"}
VALID_MAIN_TABS = {"Library", "Recommendations", "Maintenance", "Contact"}


def _preserve_invalid_settings_file():
    if not SETTINGS_FILE.exists():
        return None

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"{time.time_ns() % 1_000_000_000:09d}"
    preserved = SETTINGS_FILE.with_name(
        f"{SETTINGS_FILE.stem}.invalid-{timestamp}-{suffix}{SETTINGS_FILE.suffix}"
    )
    os.replace(SETTINGS_FILE, preserved)
    return preserved


def load_settings():
    if not SETTINGS_FILE.exists():
        return {}

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        _preserve_invalid_settings_file()
        return {}
    except OSError:
        raise

    if not isinstance(data, dict):
        _preserve_invalid_settings_file()
        return {}

    return data


def save_settings(settings):
    if not isinstance(settings, dict):
        raise TypeError("Settings must be saved as a dictionary.")

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS_FILE.with_name(f".{SETTINGS_FILE.name}.{time.time_ns()}.tmp")

    try:
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(settings, file, indent=4)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary, SETTINGS_FILE)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def get_steam_id():
    settings = load_settings()
    steam_id = settings.get("steam_id")

    if not isinstance(steam_id, str):
        return None

    steam_id = steam_id.strip()
    return steam_id or None


def set_steam_id(steam_id):
    steam_id = str(steam_id).strip()

    if not steam_id:
        raise ValueError("SteamID64 cannot be empty.")

    settings = load_settings()
    settings["steam_id"] = steam_id
    save_settings(settings)


def get_library_view_settings():
    settings = load_settings()
    library_view = settings.get("library_view")

    if not isinstance(library_view, dict):
        return {}

    return library_view


def set_library_view_settings(library_view):
    settings = load_settings()
    settings["library_view"] = library_view
    save_settings(settings)


def get_appearance():
    settings = load_settings()
    appearance = settings.get("appearance", "Dark")

    if appearance not in VALID_APPEARANCES:
        return "Dark"

    return appearance


def set_appearance(appearance):
    if appearance not in VALID_APPEARANCES:
        raise ValueError(f"Invalid appearance: {appearance}")

    settings = load_settings()
    settings["appearance"] = appearance
    save_settings(settings)


def get_active_main_tab():
    settings = load_settings()
    tab_name = settings.get("active_main_tab", "Library")

    if tab_name not in VALID_MAIN_TABS:
        return "Library"

    return tab_name


def set_active_main_tab(tab_name):
    if tab_name not in VALID_MAIN_TABS:
        return

    settings = load_settings()
    settings["active_main_tab"] = tab_name
    save_settings(settings)


def get_startup_refresh_library():
    settings = load_settings()
    value = settings.get("startup_refresh_library", True)
    return value if isinstance(value, bool) else True


def set_startup_refresh_library(enabled):
    settings = load_settings()
    settings["startup_refresh_library"] = bool(enabled)
    save_settings(settings)


def get_startup_update_missing_data():
    settings = load_settings()
    value = settings.get("startup_update_missing_data", True)
    return value if isinstance(value, bool) else True


def set_startup_update_missing_data(enabled):
    settings = load_settings()
    settings["startup_update_missing_data"] = bool(enabled)
    save_settings(settings)


def get_window_settings():
    settings = load_settings()
    window = settings.get("window")

    if not isinstance(window, dict):
        return {}

    return window


def set_window_settings(window):
    settings = load_settings()
    settings["window"] = window
    save_settings(settings)
