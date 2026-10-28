import time

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


TOP_ACHIEVEMENTS_URL = (
    "https://api.steampowered.com/IPlayerService/GetTopAchievementsForGames/v1/"
)

TOP_ACHIEVEMENT_BATCH_SIZE = 100
TOP_ACHIEVEMENT_MAX_ATTEMPTS = 3


class SteamAchievementCancelled(Exception):
    pass


def _raise_if_achievement_cancelled(cancel_requested):
    if cancel_requested is not None and cancel_requested():
        raise SteamAchievementCancelled()


def _achievement_retry_delay(attempt, cancel_requested):
    end_time = time.monotonic() + (2 ** (attempt - 1))

    while time.monotonic() < end_time:
        _raise_if_achievement_cancelled(cancel_requested)

        remaining = end_time - time.monotonic()

        time.sleep(min(0.2, remaining))


def _get_top_achievement_batch(
    session,
    steam_id,
    steam_api_key,
    app_ids,
    cancel_requested=None,
):
    params = [
        ("key", steam_api_key),
        ("steamid", steam_id),
        ("language", "english"),
        ("max_achievements", "0"),
    ]

    params.extend(
        (
            f"appids[{index}]",
            str(app_id),
        )
        for index, app_id in enumerate(app_ids)
    )

    for attempt in range(
        1,
        TOP_ACHIEVEMENT_MAX_ATTEMPTS + 1,
    ):
        _raise_if_achievement_cancelled(cancel_requested)

        try:
            response = session.get(
                TOP_ACHIEVEMENTS_URL,
                params=params,
                timeout=30,
            )

        except requests.Timeout as error:
            if attempt == TOP_ACHIEVEMENT_MAX_ATTEMPTS:
                raise SteamUnavailableError(
                    "Steam did not respond in time while loading achievement totals."
                ) from error

            _achievement_retry_delay(
                attempt,
                cancel_requested,
            )
            continue

        except requests.ConnectionError as error:
            if attempt == TOP_ACHIEVEMENT_MAX_ATTEMPTS:
                raise SteamUnavailableError(
                    "Could not connect to Steam while loading achievement totals."
                ) from error

            _achievement_retry_delay(
                attempt,
                cancel_requested,
            )
            continue

        except requests.RequestException as error:
            raise SteamApiError(
                "The Steam achievement-total request could not be completed."
            ) from error

        if response.status_code == 401:
            raise SteamApiKeyRejected(
                "Steam rejected the Web API request. Check the API key in Maintenance."
            )

        if response.status_code == 403:
            raise SteamApiError(
                "Steam rejected the batched achievement-total "
                "request. Check the Steam account privacy settings."
            )

        if response.status_code == 429:
            if attempt == TOP_ACHIEVEMENT_MAX_ATTEMPTS:
                raise SteamRateLimitError(
                    "Steam is temporarily rate-limiting "
                    "achievement-total requests. Try again later."
                )

            _achievement_retry_delay(
                attempt,
                cancel_requested,
            )
            continue

        if 500 <= response.status_code < 600:
            if attempt == TOP_ACHIEVEMENT_MAX_ATTEMPTS:
                raise SteamUnavailableError(
                    "Steam's Web API is currently unavailable "
                    "while loading achievement totals."
                )

            _achievement_retry_delay(
                attempt,
                cancel_requested,
            )
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise SteamApiError(
                f"Steam returned HTTP {response.status_code} while "
                "loading achievement totals."
            ) from error

        data = _response_json(response)

        if data is None:
            raise SteamResponseError(
                "Steam returned an unexpected achievement-total response."
            )

        response_data = data.get("response")

        if not isinstance(response_data, dict):
            raise SteamResponseError(
                "Steam returned an unexpected achievement-total response."
            )

        games = response_data.get("games", [])

        if not isinstance(games, list):
            raise SteamResponseError(
                "Steam returned an unexpected achievement-total game list."
            )

        totals = {}

        for game in games:
            if not isinstance(game, dict):
                continue

            app_id = game.get("appid")

            if not isinstance(app_id, int):
                continue

            if "total_achievements" not in game:
                totals[app_id] = None
                continue

            total = game.get("total_achievements")

            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise SteamResponseError(
                    f"Steam returned an invalid achievement total for AppID {app_id}."
                )

            totals[app_id] = total

        return totals

    raise SteamUnavailableError(
        "Steam achievement-total requests could not be completed."
    )


def get_achievement_totals(
    steam_id,
    steam_api_key,
    app_ids,
    batch_size=TOP_ACHIEVEMENT_BATCH_SIZE,
    cancel_requested=None,
):
    app_ids = list(
        dict.fromkeys(
            app_id
            for app_id in app_ids
            if (isinstance(app_id, int) and not isinstance(app_id, bool) and app_id > 0)
        )
    )

    if not app_ids:
        return {}

    batch_size = max(
        int(batch_size),
        1,
    )

    totals = {}

    with requests.Session() as session:
        for start in range(
            0,
            len(app_ids),
            batch_size,
        ):
            _raise_if_achievement_cancelled(cancel_requested)

            batch = app_ids[start : start + batch_size]

            totals.update(
                _get_top_achievement_batch(
                    session=session,
                    steam_id=steam_id,
                    steam_api_key=steam_api_key,
                    app_ids=batch,
                    cancel_requested=cancel_requested,
                )
            )

    return totals


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


def _is_profile_not_public_error(error_message):
    return "profile is not public" in (error_message or "").casefold()


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
    known_total=None,
):
    """
    Load player achievement progress.

    known_total may be supplied when GetTopAchievementsForGames has already
    established a positive current achievement total. In that case, avoid
    redundant schema checks and retain the independently established total.
    """
    if known_total is not None and (
        not isinstance(known_total, int)
        or isinstance(known_total, bool)
        or known_total < 0
    ):
        raise ValueError("known_total must be a non-negative integer or None.")

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
        if known_total is not None and known_total > 0:
            raise SteamResponseError(
                f"Steam reported no player achievement stats "
                f"for AppID {app_id}, but the batched endpoint "
                f"reports {known_total} achievements."
            )

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
        if not known_total and _fallback_confirms_no_achievements(
            steam_api_key,
            app_id,
        ):
            return 0, 0

        detail = error_message or response.text.strip() or "No response details"

        print(f"Steam achievement 403 for AppID {app_id}: {detail[:1000]}")

        if _is_profile_not_public_error(error_message):
            raise SteamApiError(
                "Steam could not provide achievement data because it reported "
                "'Profile is not public.' Before updating achievements, set both "
                "My Profile and Game details to Public under Profile > Edit Profile "
                "> Privacy Settings. After the update finishes, you can restore "
                "your preferred privacy settings. If those settings are already "
                "Public, Steam may still be propagating the change. If only this "
                "game fails, check whether the game itself is marked Private in Steam."
            )

        raise SteamApiError(
            f"Steam returned HTTP 403 while loading achievements: {detail[:300]}"
        )

    if 500 <= response.status_code < 600:
        if not known_total and _fallback_confirms_no_achievements(
            steam_api_key,
            app_id,
        ):
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

    returned_total = len(achievements)

    unlocked = sum(
        1
        for achievement in achievements
        if isinstance(achievement, dict) and achievement.get("achieved") == 1
    )

    if known_total is not None and known_total > 0:
        if unlocked > known_total:
            raise SteamResponseError(
                f"Steam returned {unlocked} unlocked achievements "
                f"for AppID {app_id}, which exceeds the known "
                f"total of {known_total}."
            )

        if returned_total != known_total:
            print(
                f"Steam achievement total mismatch for AppID {app_id}: "
                f"batch={known_total}, player={returned_total}"
            )

        return known_total, unlocked

    return returned_total, unlocked
