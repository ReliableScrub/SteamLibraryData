import keyring
from keyring.errors import KeyringError

SERVICE_NAME = "SteamLibraryData"
STEAM_API_KEY_USERNAME = "steam_api_key"


def get_steam_api_key():
    try:
        api_key = keyring.get_password(SERVICE_NAME, STEAM_API_KEY_USERNAME)
    except KeyringError:
        return None

    if not api_key:
        return None

    return api_key.strip() or None


def set_steam_api_key(api_key):
    api_key = str(api_key).strip()

    if not api_key:
        raise ValueError("Steam API key cannot be empty.")

    try:
        keyring.set_password(SERVICE_NAME, STEAM_API_KEY_USERNAME, api_key)
    except KeyringError as error:
        raise RuntimeError(
            "Could not save the Steam API key to the system credentials."
        ) from error


def delete_steam_api_key():
    try:
        keyring.delete_password(SERVICE_NAME, STEAM_API_KEY_USERNAME)
    except KeyringError as error:
        raise RuntimeError(
            "Could not delete the Steam API key from the system credentials."
        ) from error
