import requests

def get_game_metadata(app_id):
    url = "https://steamspy.com/api.php"

    params = {
        "request": "appdetails",
        "appid": app_id
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    genre_text = data.get("genre", "")
    # Split the genre string into a list of genres, removing any leading/trailing whitespace
    # WHAT TO ADD for ITEM in SOURCE if CONDITION
    genres = [
        genre.strip()
        for genre in genre_text.split(",")
        if genre.strip()
    ]

    tags = data.get("tags", {})

    return genres, tags