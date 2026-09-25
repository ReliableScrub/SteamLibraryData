import requests


def get_game_metadata(app_id):
    url = "https://steamspy.com/api.php"

    params = {
        "request": "appdetails",
        "appid": app_id,
    }

    response = requests.get(
        url,
        params=params,
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()

    genre_text = data.get("genre") or ""

    genres = [genre.strip() for genre in genre_text.split(",") if genre.strip()]

    tags = data.get("tags") or {}

    if isinstance(tags, list):
        tags = {tag: 0 for tag in tags if isinstance(tag, str)}

    if not isinstance(tags, dict):
        tags = {}

    return genres, tags
