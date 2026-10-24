import requests

from api.steam_api import (
    SteamApiError,
    SteamApiKeyRejected,
    SteamRateLimitError,
    SteamResponseError,
    SteamUnavailableError,
)

PLAYER_ACHIEVEMENTS_URL = (
    "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/"
)

ACHIEVEMENT_SCHEMA_URL = (
    "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
)


def _request(url, steam_api_key, params, timeout=30):
    try:
        return requests.get(
            url,
            headers={"x-webapi-key": steam_api_key},
            params=params,
            timeout=timeout,
        )
    except requests.Timeout as error:
        raise SteamUnavailableError(
            "Steam did not respond in time. Try again later."
        ) from error
    except requests.ConnectionError as error:
        raise SteamUnavailableError(
            "Could not connect to Steam. Check your internet connection."
        ) from error
    except requests.RequestException as error:
        raise SteamApiError("The Steam request could not be completed.") from error


def _response_json(response):
    try:
        data = response.json()
    except ValueError:
        return None

    if not isinstance(data, dict):
        return None

    return data


def _player_stats_error(data):
    if not isinstance(data, dict):
        return None

    player_stats = data.get("playerstats")

    if not isinstance(player_stats, dict):
        return None

    if player_stats.get("success") is not False:
        return None

    return str(player_stats.get("error", "")).strip()


def _is_no_stats_error(error_message):
    text = (error_message or "").casefold()

    return "no stats" in text or "no achievements" in text


def game_has_achievements(steam_api_key, app_id):
    """
    Ask Steam for the game's achievement schema.

    This is intentionally a fallback check. Normal achievement updates use
    GetPlayerAchievements first so ordinary games still cost only one request.
    """
    response = _request(
        ACHIEVEMENT_SCHEMA_URL,
        steam_api_key,
        {
            "appid": app_id,
            "l": "english",
        },
    )

    if response.status_code in (401, 403):
        raise SteamApiKeyRejected(
            "Steam rejected the Web API request. Check the API key in Maintenance."
        )

    if response.status_code == 429:
        raise SteamRateLimitError(
            "Steam is temporarily rate-limiting requests. Try again later."
        )

    if 500 <= response.status_code < 600:
        raise SteamUnavailableError(
            "Steam's Web API is currently unavailable. Try again later."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise SteamApiError(
            f"Steam returned HTTP {response.status_code} "
            "while checking the achievement schema."
        ) from error

    data = _response_json(response)

    if data is None:
        raise SteamResponseError(
            "Steam returned an unexpected achievement schema response."
        )

    game = data.get("game")

    if not isinstance(game, dict):
        raise SteamResponseError("Steam returned an unexpected achievement schema.")

    game_stats = game.get("availableGameStats")

    if game_stats is None:
        return False

    if not isinstance(game_stats, dict):
        raise SteamResponseError("Steam returned an unexpected achievement schema.")

    achievements = game_stats.get("achievements")

    if achievements is None:
        return False

    if not isinstance(achievements, list):
        raise SteamResponseError("Steam returned an unexpected achievement schema.")

    return len(achievements) > 0


def _fallback_confirms_no_achievements(steam_api_key, app_id):
    """
    Return True only when the schema successfully confirms there are no
    achievements.

    If the fallback itself fails, keep the original player-achievement error.
    This prevents a secondary Steam problem from being mistaken for a valid
    zero-achievement result.
    """
    try:
        return not game_has_achievements(steam_api_key, app_id)
    except SteamApiError:
        return False


def get_achievement_progress(
    steam_id,
    steam_api_key,
    app_id,
):
    """
    Load player achievement progress.

    Normal case: one GetPlayerAchievements request.

    Edge case: if Steam returns an ambiguous per-app 403 or 5xx response,
    check GetSchemaForGame. If the schema confirms that the app publishes no
    achievements, return (0, 0) and allow the caller to mark it checked.
    """
    response = _request(
        PLAYER_ACHIEVEMENTS_URL,
        steam_api_key,
        {
            "steamid": steam_id,
            "appid": app_id,
            "l": "english",
        },
    )

    data = _response_json(response)
    error_message = _player_stats_error(data)

    if _is_no_stats_error(error_message):
        return 0, 0

    if response.status_code == 401:
        raise SteamApiKeyRejected(
            "Steam rejected the Web API request. Check the API key in Maintenance."
        )

    if response.status_code == 429:
        raise SteamRateLimitError(
            "Steam is temporarily rate-limiting requests. Try again later."
        )

    if response.status_code == 403:
        if _fallback_confirms_no_achievements(steam_api_key, app_id):
            return 0, 0

        raise SteamApiKeyRejected(
            "Steam rejected the Web API request. Check the API key in Maintenance."
        )

    if 500 <= response.status_code < 600:
        if _fallback_confirms_no_achievements(steam_api_key, app_id):
            return 0, 0

        raise SteamUnavailableError(
            "Steam's Web API is currently unavailable. Try again later."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise SteamApiError(
            f"Steam returned HTTP {response.status_code} while loading achievements."
        ) from error

    if data is None:
        raise SteamResponseError("Steam returned an unexpected achievement response.")

    player_stats = data.get("playerstats")

    if not isinstance(player_stats, dict):
        raise SteamResponseError("Steam returned an unexpected achievement response.")

    if player_stats.get("success") is False:
        raise SteamResponseError(
            error_message or "Steam could not return achievement data."
        )

    achievements = player_stats.get("achievements", [])

    if not isinstance(achievements, list):
        raise SteamResponseError("Steam returned an unexpected achievement list.")

    total = len(achievements)

    unlocked = sum(
        1
        for achievement in achievements
        if isinstance(achievement, dict) and achievement.get("achieved") == 1
    )

    return total, unlocked
