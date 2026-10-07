import os
import platform
from pathlib import Path

APP_NAME = "SteamLibraryData"


def get_app_data_directory():
    system = platform.system()

    if system == "Windows":
        base_directory = os.getenv("APPDATA")
        if base_directory:
            base_path = Path(base_directory)
        else:
            base_path = Path.home() / "AppData" / "Roaming"

    elif system == "Darwin":
        base_path = Path.home() / "Library" / "Application Support"

    else:
        base_directory = os.getenv("XDG_DATA_HOME")
        if base_directory:
            base_path = Path(base_directory)
        else:
            base_path = Path.home() / ".local" / "share"

    app_directory = base_path / APP_NAME
    app_directory.mkdir(parents=True, exist_ok=True)

    return app_directory


APP_DATA_DIRECTORY = get_app_data_directory()

DB_FILE = APP_DATA_DIRECTORY / "steam_backlog.db"
SETTINGS_FILE = APP_DATA_DIRECTORY / "settings.json"
IMAGE_CACHE = APP_DATA_DIRECTORY / "images"
