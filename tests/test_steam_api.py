import json

import requests

from api import steam_api


def make_response(data, status_code=200):
    """
    Create a real requests.Response object without making a network request.

    This lets the production Steam code use normal Response attributes such as:
    - status_code
    - headers
    - text
    - json()
    - raise_for_status()
    """
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(data).encode("utf-8")
    response.encoding = "utf-8"
    response.headers["Content-Type"] = "application/json"
    response.url = "https://api.steampowered.com/test"

    return response


def request_contains_value(request, expected_value):
    """
    Check both query parameters and headers for a value.

    We deliberately do not require the API key to be stored in one specific
    location. The application may send credentials through parameters or
    headers depending on the current Steam API implementation.
    """
    params = request.get("params") or {}
    headers = request.get("headers") or {}

    values = list(params.values()) + list(headers.values())

    return any(expected_value in str(value) for value in values)


def test_get_owned_games_requests_and_parses_library(monkeypatch):
    """
    Verify that get_owned_games():

    1. Calls Steam's official GetOwnedGames endpoint.
    2. Sends the configured SteamID.
    3. Sends the API credential.
    4. Requests game information and played free games.
    5. Converts Steam's JSON response into Game objects correctly.
    6. Safely defaults optional Steam fields when they are missing.
    """

    request = {}

    def fake_get(url, params=None, headers=None, **kwargs):
        # Record what the real production function attempted to send.
        request["url"] = url
        request["params"] = params or {}
        request["headers"] = headers or {}
        request["kwargs"] = kwargs

        # Pretend Steam returned two owned games.
        return make_response(
            {
                "response": {
                    "game_count": 2,
                    "games": [
                        {
                            "appid": 10,
                            "name": "Played Test Game",
                            "playtime_forever": 600,
                            "playtime_2weeks": 120,
                            "rtime_last_played": 1234567890,
                        },
                        {
                            "appid": 20,
                            "name": "Unplayed Test Game",
                            "playtime_forever": 0,
                        },
                    ],
                }
            }
        )

    # Replace requests.get only for this test.
    # The real get_owned_games() function still runs.
    monkeypatch.setattr(
        steam_api.requests,
        "get",
        fake_get,
    )

    # ACT
    games = steam_api.get_owned_games(
        "0",
        "fake_api_key",
    )

    # ASSERT:
    # The official Steam owned-library endpoint should be used.
    assert request["url"] == (
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    )

    # The configured SteamID should be sent with the request.
    assert request["params"]["steamid"] == "0"

    # The API key must be included somewhere in the request.
    # We do not care whether the current implementation uses a parameter
    # or an HTTP header.
    assert request_contains_value(
        request,
        "fake_api_key",
    )

    # These flags are important to our library import.
    assert request["params"]["include_appinfo"] is True
    assert request["params"]["include_played_free_games"] is True

    # Steam returned two games.
    assert len(games) == 2

    played_game = games[0]

    # Steam's JSON fields should map correctly to our Game object.
    assert played_game.app_id == 10
    assert played_game.name == "Played Test Game"
    assert played_game.playtime_minutes == 600
    assert played_game.playtime_2weeks_minutes == 120
    assert played_game.last_played_timestamp == 1234567890

    unplayed_game = games[1]

    # Missing optional Steam fields should safely become zero.
    assert unplayed_game.app_id == 20
    assert unplayed_game.name == "Unplayed Test Game"
    assert unplayed_game.playtime_minutes == 0
    assert unplayed_game.playtime_2weeks_minutes == 0
    assert unplayed_game.last_played_timestamp == 0


def test_get_owned_games_handles_empty_library(monkeypatch):
    """
    A valid Steam response containing no games should return an empty list,
    not raise an exception.
    """

    def fake_get(url, params=None, headers=None, **kwargs):
        return make_response(
            {
                "response": {
                    "game_count": 0,
                    "games": [],
                }
            }
        )

    monkeypatch.setattr(
        steam_api.requests,
        "get",
        fake_get,
    )

    games = steam_api.get_owned_games(
        "0",
        "fake_api_key",
    )

    assert games == []
