import math

import pytest

from recommendations.data import RecommendationGameData
from recommendations.features import build_content_features


def make_game(app_id, name, genres=None, tags=None):
    return RecommendationGameData(
        app_id=app_id,
        name=name,
        playtime_minutes=0,
        playtime_2weeks_minutes=0,
        last_played_timestamp=0,
        manual_status=None,
        rating=None,
        metadata_checked=True,
        genres=genres or [],
        tags=tags or {},
    )


def test_content_features_include_genres_and_tags():
    games = [
        make_game(
            1,
            "Test RPG",
            genres=["RPG"],
            tags={
                "Story Rich": 100,
                "Fantasy": 50,
            },
        )
    ]

    vectors = build_content_features(games)
    vector = vectors[1]

    assert "genre:RPG" in vector
    assert "tag:Story Rich" in vector
    assert "tag:Fantasy" in vector


def test_stronger_tag_gets_more_weight():
    games = [
        make_game(
            1,
            "Test Game",
            tags={
                "RPG": 100,
                "Strategy": 25,
            },
        )
    ]

    vector = build_content_features(games)

    assert vector[1]["tag:RPG"] > vector[1]["tag:Strategy"]


def test_content_vector_is_normalized():
    games = [
        make_game(
            1,
            "Test Game",
            genres=["RPG"],
            tags={"Story Rich": 100},
        )
    ]

    vector = build_content_features(games)[1]

    magnitude = math.sqrt(sum(value * value for value in vector.values()))

    assert magnitude == pytest.approx(1.0)
