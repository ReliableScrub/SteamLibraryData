import requests

from api.steam_api import (
    SteamApiError,
    SteamApiKeyRejected,
    SteamRateLimitError,
    SteamResponseError,
    SteamUnavailableError,
)


def game_has_achievements(api_key, app_id):
    url = "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"

    params = {"key": api_key, "appid": app_id}

    response = requests.get(url, params=params, timeout=10)

    response.raise_for_status()

    data = response.json()

    game_stats = data.get("game", {}).get("availableGameStats", {})
    achievements = game_stats.get("achievements", [])

    return len(achievements) > 0


def get_achievement_progress(
    steam_id,
    steam_api_key,
    app_id,
):
    url = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/"

    params = {
        "steamid": steam_id,
        "appid": app_id,
        "l": "english",
    }

    try:
        response = requests.get(
            url,
            headers={
                "x-webapi-key": steam_api_key,
            },
            params=params,
            timeout=30,
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
        raise SteamApiError(
            "The Steam achievement request could not be completed."
        ) from error

    if response.status_code in (401, 403):
        raise SteamApiKeyRejected(
            "Steam rejected your Web API key. Update it from the Settings tab."
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
        data = response.json()
    except ValueError as error:
        raise SteamResponseError(
            "Steam returned an unexpected achievement response."
        ) from error

    player_stats = data.get("playerstats")

    if not isinstance(player_stats, dict):
        raise SteamResponseError("Steam returned an unexpected achievement response.")

    if player_stats.get("success") is False:
        error_message = str(player_stats.get("error", ""))

        if "no stats" in error_message.lower():
            return 0, 0

        raise SteamResponseError(
            error_message or "Steam could not return achievement data."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise SteamApiError(
            f"Steam returned HTTP {response.status_code} while loading achievements."
        ) from error

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
