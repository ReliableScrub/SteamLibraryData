import requests

from game import Game

def get_owned_games(steam_api_key: str, steam_id: str) -> list[Game]:
    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"

    params = {
        "key": steam_api_key,
        "steamid": steam_id,
        "include_appinfo": True,
        "include_played_free_games": True,
    }

    response = requests.get(url, params=params)

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
        )

        game_list.append(game)

    return game_list