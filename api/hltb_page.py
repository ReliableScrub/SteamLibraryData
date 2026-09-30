import json
import re

import requests

HLTB_GAME_URL = "https://howlongtobeat.com/game/{game_id}"

HLTB_PAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://howlongtobeat.com/",
}


def clean_optional_text(value):
    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    return value


def positive_int(value):
    try:
        value = int(value)

    except (TypeError, ValueError):
        return None

    if value <= 0:
        return None

    return value


def split_comma_separated(value):
    value = clean_optional_text(value)

    if value is None:
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_release_date(value):
    value = clean_optional_text(value)

    if value in (None, "0000-00-00"):
        return None

    return value


def fetch_hltb_detail_payload(hltb_game_id):
    url = HLTB_GAME_URL.format(game_id=hltb_game_id)

    try:
        response = requests.get(
            url,
            headers=HLTB_PAGE_HEADERS,
            timeout=30,
        )

        response.raise_for_status()

    except requests.RequestException as error:
        print(f"HLTB detail request failed for {hltb_game_id}: {error}")

        return None

    next_data_match = re.search(
        (
            r"<script[^>]*"
            r'id=["\']__NEXT_DATA__["\']'
            r"[^>]*>(.*?)</script>"
        ),
        response.text,
        flags=re.DOTALL,
    )

    if next_data_match is None:
        print(f"HLTB detail page {hltb_game_id} has no __NEXT_DATA__")

        return None

    try:
        payload = json.loads(next_data_match.group(1))

    except json.JSONDecodeError:
        print(f"HLTB detail page {hltb_game_id} has invalid __NEXT_DATA__")

        return None

    try:
        return payload["props"]["pageProps"]["game"]["data"]

    except (KeyError, TypeError):
        print(f"HLTB detail page {hltb_game_id} has an unexpected data structure")

        return None


def serialize_relationship(relationship):
    if not isinstance(relationship, dict):
        return None

    return {
        "game_id": positive_int(relationship.get("game_id")),
        "game_name": clean_optional_text(relationship.get("game_name")),
        "game_type": clean_optional_text(relationship.get("game_type")),
    }


def get_hltb_detail_data(hltb_game_id):
    detail_payload = fetch_hltb_detail_payload(hltb_game_id)

    if detail_payload is None:
        return None

    games = detail_payload.get("game")

    if not isinstance(games, list) or not games or not isinstance(games[0], dict):
        print(f"HLTB detail page {hltb_game_id} has no usable game record")

        return None

    game_data = games[0]

    relationships = []

    for relationship in detail_payload.get("relationships") or []:
        serialized = serialize_relationship(relationship)

        if serialized is not None:
            relationships.append(serialized)

    return {
        "game_id": positive_int(game_data.get("game_id")),
        "game_name": clean_optional_text(game_data.get("game_name")),
        "game_type": clean_optional_text(game_data.get("game_type")),
        "steam_app_id": positive_int(game_data.get("profile_steam")),
        "developer": clean_optional_text(game_data.get("profile_dev")),
        "publisher": clean_optional_text(game_data.get("profile_pub")),
        "genres": split_comma_separated(game_data.get("profile_genre")),
        "platforms": split_comma_separated(game_data.get("profile_platform")),
        "release_date": normalize_release_date(game_data.get("release_world")),
        "relationships": relationships,
    }


def get_hltb_detail_steam_app_id(hltb_game_id):
    detail_data = get_hltb_detail_data(hltb_game_id)

    if detail_data is None:
        return None

    return detail_data["steam_app_id"]
