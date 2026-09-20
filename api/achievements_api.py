import requests


def game_has_achievements(api_key, app_id):
    url = (
        "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
    )

    params = {
        "key": api_key,
        "appid": app_id
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    game_stats = data.get("game", {}).get("availableGameStats", {})
    achievements = game_stats.get("achievements", [])

    return len(achievements) > 0


def get_achievement_progress(steam_id, api_key, app_id):
    if not game_has_achievements(api_key, app_id):
        return 0, 0

    url = (
        "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
    )

    params = {
        "key": api_key,
        "steamid": steam_id,
        "appid": app_id
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    player_stats = data.get("playerstats", {})
    achievements = player_stats.get("achievements", [])

    total = len(achievements)

    unlocked = sum(1 for achievement in achievements if achievement.get("achieved") == 1)

    return total, unlocked