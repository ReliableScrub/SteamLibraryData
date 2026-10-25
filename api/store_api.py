import html
import re

import requests

STORE_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

_STORE_DATA_CACHE = {}


def _get_store_data(app_id):
    if app_id in _STORE_DATA_CACHE:
        return _STORE_DATA_CACHE[app_id]

    response = requests.get(
        STORE_DETAILS_URL,
        params={"appids": app_id, "cc": "US", "l": "english"},
        timeout=15,
    )
    response.raise_for_status()

    payload = response.json()
    result = payload.get(str(app_id)) if isinstance(payload, dict) else None

    if not result or not result.get("success"):
        _STORE_DATA_CACHE[app_id] = None
        return None

    data = result.get("data") or {}
    _STORE_DATA_CACHE[app_id] = data
    return data


def get_short_description(app_id):
    data = _get_store_data(app_id)

    if not data:
        return ""

    description = data.get("short_description") or ""

    if not isinstance(description, str):
        description = str(description)

    description = re.sub(r"<br\s*/?>", "\n", description, flags=re.IGNORECASE)
    description = re.sub(r"<[^>]+>", " ", description)
    description = html.unescape(description)
    description = re.sub(r"[ \t]+", " ", description)
    description = re.sub(r" *\n *", "\n", description)

    return description.strip()


def get_trailer_url(app_id):
    data = _get_store_data(app_id)

    if not data:
        return None

    movies = data.get("movies", [])

    if not movies:
        return None

    movie = movies[0]

    if movie.get("hls_h264"):
        return movie["hls_h264"]

    mp4 = movie.get("mp4") or {}

    if mp4.get("480"):
        return mp4["480"]

    if mp4.get("max"):
        return mp4["max"]

    webm = movie.get("webm") or {}

    if webm.get("480"):
        return webm["480"]

    if webm.get("max"):
        return webm["max"]

    return None
