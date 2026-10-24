import json

import pytest
import requests

from api import steam_api
from recommendations.data import load_recommendation_games
from storage import database


def make_response(data, status_code=200):
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(data).encode("utf-8")
    response.encoding = "utf-8"
    response.headers["Content-Type"] = "application/json"
    response.url = "https://api.steampowered.com/test"
    return response


def request_contains_value(request, expected_value):
    params = request.get("params") or {}
    headers = request.get("headers") or {}
    values = list(params.values()) + list(headers.values())
    return any(expected_value in str(value) for value in values)


def test_rating_crud(temporary_database):
    database.set_game_rating(123, 5)
    assert database.get_game_rating(123) == 5

    database.set_game_rating(123, 4)
    assert database.get_game_rating(123) == 4

    database.clear_game_rating(123)
    assert database.get_game_rating(123) is None


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_rating_rejects_invalid_values(temporary_database, rating):
    with pytest.raises(ValueError):
        database.set_game_rating(123, rating)


def test_rating_survives_library_game_deletion(temporary_database):
    with database.get_connection() as connection:
        connection.execute(
            "INSERT INTO games (app_id, name) VALUES (?, ?)",
            (123, "Test Game"),
        )

    database.set_game_rating(123, 5)
    database.delete_games_not_in([])

    with database.get_connection() as connection:
        row = connection.execute(
            "SELECT app_id FROM games WHERE app_id = ?",
            (123,),
        ).fetchone()

    assert row is None
    assert database.get_game_rating(123) == 5


def test_recommendation_data_loads_metadata_and_rating(temporary_database):
    with database.get_connection() as connection:
        connection.execute(
            """
            INSERT INTO games (
                app_id,
                name,
                steam_type,
                playtime_minutes,
                metadata_checked
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (123, "Test RPG", "game", 600, 1),
        )
        connection.execute(
            "INSERT INTO genres (name) VALUES (?)",
            ("RPG",),
        )
        genre_id = connection.execute(
            "SELECT genre_id FROM genres WHERE name = ?",
            ("RPG",),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO game_genres (app_id, genre_id) VALUES (?, ?)",
            (123, genre_id),
        )

        connection.execute(
            "INSERT INTO tags (name) VALUES (?)",
            ("Story Rich",),
        )
        tag_id = connection.execute(
            "SELECT tag_id FROM tags WHERE name = ?",
            ("Story Rich",),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO game_tags (app_id, tag_id, weight) VALUES (?, ?, ?)",
            (123, tag_id, 250),
        )

    database.set_game_rating(123, 5)

    games = load_recommendation_games()

    assert len(games) == 1
    game = games[0]

    assert game.app_id == 123
    assert game.name == "Test RPG"
    assert game.playtime_minutes == 600
    assert game.rating == 5
    assert game.genres == ["RPG"]
    assert game.tags == {"Story Rich": 250}


def test_get_owned_games_requests_and_parses_library(monkeypatch):
    request = {}

    def fake_get(url, params=None, headers=None, **kwargs):
        request["url"] = url
        request["params"] = params or {}
        request["headers"] = headers or {}
        request["kwargs"] = kwargs

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

    monkeypatch.setattr(steam_api.requests, "get", fake_get)

    games = steam_api.get_owned_games("0", "fake_api_key")

    assert request["url"] == (
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
    )
    assert request["params"]["steamid"] == "0"
    assert request_contains_value(request, "fake_api_key")
    assert request["params"]["include_appinfo"] is True
    assert request["params"]["include_played_free_games"] is True

    assert len(games) == 2

    assert games[0].app_id == 10
    assert games[0].name == "Played Test Game"
    assert games[0].playtime_minutes == 600
    assert games[0].playtime_2weeks_minutes == 120
    assert games[0].last_played_timestamp == 1234567890

    assert games[1].app_id == 20
    assert games[1].name == "Unplayed Test Game"
    assert games[1].playtime_minutes == 0
    assert games[1].playtime_2weeks_minutes == 0
    assert games[1].last_played_timestamp == 0


def test_get_owned_games_handles_empty_library(monkeypatch):
    def fake_get(url, params=None, headers=None, **kwargs):
        return make_response(
            {
                "response": {
                    "game_count": 0,
                    "games": [],
                }
            }
        )

    monkeypatch.setattr(steam_api.requests, "get", fake_get)

    assert steam_api.get_owned_games("0", "fake_api_key") == []
