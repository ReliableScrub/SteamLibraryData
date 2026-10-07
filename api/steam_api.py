import json
import time

import requests

from game import Game

STORE_APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"

STORE_APP_TYPE_FLAGS = {
    "game": "include_games",
    "dlc": "include_dlc",
    "software": "include_software",
    "video": "include_videos",
    "hardware": "include_hardware",
}

STORE_PAGE_SIZE = 50_000
STORE_REQUEST_TIMEOUT = 30
STORE_MAX_ATTEMPTS = 3
STEAM_API_VALIDATION_TIMEOUT = 10


class SteamApiKeyRejected(Exception):
    pass


class SteamApiValidationError(Exception):
    pass


class SteamClassificationCancelled(Exception):
    pass


def get_game_image_url(app_id):
    return f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg"


def get_owned_games(steam_id: str, steam_api_key: str) -> list[Game]:
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"

    headers = {
        "x-webapi-key": steam_api_key,
    }

    params = {
        "steamid": steam_id,
        "include_appinfo": True,
        "include_played_free_games": True,
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30,
    )

    # Check if the request was successful
    response.raise_for_status()

    data = response.json()

    # Check if the response contains the expected data
    games = data.get("response", {}).get("games", [])

    game_list = []

    for game_data in games:
        game = Game(
            app_id=game_data["appid"],
            name=game_data["name"],
            playtime_minutes=game_data.get("playtime_forever", 0),
            playtime_2weeks_minutes=game_data.get("playtime_2weeks", 0),
            last_played_timestamp=game_data.get("rtime_last_played", 0),
        )

        game_list.append(game)

    return game_list


def _raise_if_classification_cancelled(cancel_requested):
    if cancel_requested is not None and cancel_requested():
        raise SteamClassificationCancelled()


def _get_store_app_list_page(
    session,
    steam_api_key,
    app_type,
    last_appid,
    cancel_requested=None,
):
    if app_type not in STORE_APP_TYPE_FLAGS:
        raise ValueError(f"Unknown Steam app type: {app_type}")

    request_data = {
        "include_games": False,
        "include_dlc": False,
        "include_software": False,
        "include_videos": False,
        "include_hardware": False,
        "last_appid": last_appid,
        "max_results": STORE_PAGE_SIZE,
    }

    request_data[STORE_APP_TYPE_FLAGS[app_type]] = True

    headers = {
        "x-webapi-key": steam_api_key,
    }

    params = {
        "input_json": json.dumps(request_data),
    }

    for attempt in range(1, STORE_MAX_ATTEMPTS + 1):
        _raise_if_classification_cancelled(cancel_requested)

        try:
            response = session.get(
                STORE_APP_LIST_URL,
                headers=headers,
                params=params,
                timeout=STORE_REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            response_data = data.get("response")

            if not isinstance(response_data, dict):
                raise TypeError(
                    "Steam GetAppList response did not contain a valid response object."
                )

            apps = response_data.get("apps", [])

            if not isinstance(apps, list):
                raise TypeError("Steam GetAppList response.apps was not a list.")

            return response_data

        except (
            requests.RequestException,
            ValueError,
            RuntimeError,
        ) as error:
            if attempt == STORE_MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Steam GetAppList failed for type "
                    f"{app_type!r} after "
                    f"{STORE_MAX_ATTEMPTS} attempts."
                ) from error

            delay = 2 ** (attempt - 1)

            print(
                f"Steam classification request failed for "
                f"{app_type}. Retrying in {delay}s..."
            )

            end_time = time.monotonic() + delay

            while time.monotonic() < end_time:
                _raise_if_classification_cancelled(cancel_requested)

                remaining = end_time - time.monotonic()

                time.sleep(min(0.2, remaining))


def _scan_store_app_type(
    session,
    steam_api_key,
    app_type,
    owned_app_ids,
    cancel_requested=None,
    progress_callback=None,
):
    if not owned_app_ids:
        return set()

    matched_app_ids = set()

    highest_owned_app_id = max(owned_app_ids)

    last_appid = 0
    page_number = 0

    while True:
        _raise_if_classification_cancelled(cancel_requested)

        response_data = _get_store_app_list_page(
            session=session,
            steam_api_key=steam_api_key,
            app_type=app_type,
            last_appid=last_appid,
            cancel_requested=cancel_requested,
        )

        page_number += 1

        apps = response_data.get("apps", [])

        for app in apps:
            if not isinstance(app, dict):
                continue

            app_id = app.get("appid")

            if not isinstance(app_id, int):
                continue

            if app_id in owned_app_ids:
                matched_app_ids.add(app_id)

        if progress_callback is not None:
            progress_callback(
                app_type,
                page_number,
                len(matched_app_ids),
            )

        if matched_app_ids == owned_app_ids:
            break

        if not response_data.get(
            "have_more_results",
            False,
        ):
            break

        next_last_appid = response_data.get("last_appid")

        if not isinstance(next_last_appid, int) or next_last_appid <= last_appid:
            raise RuntimeError("Steam GetAppList pagination did not advance correctly.")

        # Steam documents results as sorted by App ID.
        # Once the continuation point is beyond every
        # App ID we own, later pages cannot match anything.
        if next_last_appid >= highest_owned_app_id:
            break

        last_appid = next_last_appid

    return matched_app_ids


def classify_owned_apps(
    owned_app_ids,
    steam_api_key,
    cancel_requested=None,
    progress_callback=None,
):
    owned_app_ids = {
        app_id for app_id in owned_app_ids if isinstance(app_id, int) and app_id > 0
    }

    if not owned_app_ids:
        return {}

    matches_by_app_id = {app_id: set() for app_id in owned_app_ids}

    with requests.Session() as session:
        for app_type in STORE_APP_TYPE_FLAGS:
            _raise_if_classification_cancelled(cancel_requested)

            matched_app_ids = _scan_store_app_type(
                session=session,
                steam_api_key=steam_api_key,
                app_type=app_type,
                owned_app_ids=owned_app_ids,
                cancel_requested=cancel_requested,
                progress_callback=progress_callback,
            )

            for app_id in matched_app_ids:
                matches_by_app_id[app_id].add(app_type)

    classifications = {}

    for app_id, matched_types in matches_by_app_id.items():
        if len(matched_types) == 1:
            classifications[app_id] = next(iter(matched_types))

        elif len(matched_types) == 0:
            classifications[app_id] = "unknown"

        else:
            # Be conservative if Steam unexpectedly reports
            # the same App ID under multiple filtered types.
            classifications[app_id] = "unknown"

            print(
                f"Steam classification ambiguous for "
                f"AppID {app_id}: "
                f"{sorted(matched_types)}"
            )

    return classifications


def validate_steam_api_key(steam_api_key):
    steam_api_key = str(steam_api_key).strip()

    if not steam_api_key:
        raise SteamApiKeyRejected("Steam API key cannot be empty.")

    request_data = {
        "include_games": True,
        "include_dlc": False,
        "include_software": False,
        "include_videos": False,
        "include_hardware": False,
        "last_appid": 0,
        "max_results": 1,
    }

    try:
        response = requests.get(
            STORE_APP_LIST_URL,
            headers={
                "x-webapi-key": steam_api_key,
            },
            params={
                "input_json": json.dumps(request_data),
            },
            timeout=STEAM_API_VALIDATION_TIMEOUT,
        )
    except requests.RequestException as error:
        raise SteamApiValidationError(
            "Steam could not be reached, so the API key could not be verified."
        ) from error

    if response.status_code in (401, 403):
        raise SteamApiKeyRejected(
            "Steam rejected this API key. Check that it was copied correctly "
            "and that it is a standard Steam Web API key."
        )

    if response.status_code == 429:
        raise SteamApiValidationError(
            "Steam temporarily rate-limited the validation request."
        )

    try:
        response.raise_for_status()
    except requests.RequestException as error:
        raise SteamApiValidationError(
            f"Steam returned HTTP {response.status_code} while validating the API key."
        ) from error

    try:
        data = response.json()
    except ValueError as error:
        raise SteamApiValidationError(
            "Steam returned an unexpected response while validating the API key."
        ) from error

    if not isinstance(data.get("response"), dict):
        raise SteamApiValidationError(
            "Steam returned an unexpected response while validating the API key."
        )

    return True
