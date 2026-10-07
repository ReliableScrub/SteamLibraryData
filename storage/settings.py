import json

from storage.paths import SETTINGS_FILE


def load_settings():
    if not SETTINGS_FILE.exists():
        return {}

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def save_settings(settings):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, indent=4)


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
