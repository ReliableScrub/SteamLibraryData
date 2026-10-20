import math
from types import SimpleNamespace

import pytest

from recommendations.data import RecommendationGameData
from recommendations.features import (
    build_content_features,
    cosine_similarity,
)


def test_rare_tag_gets_more_weight_than_common_tag():
    games = [
        SimpleNamespace(
            app_id=1,
            genres=[],
            tags={
                "Common Tag": 100,
                "Rare Tag": 100,
            },
        ),
        SimpleNamespace(
            app_id=2,
            genres=[],
            tags={
                "Common Tag": 100,
            },
        ),
        SimpleNamespace(
            app_id=3,
            genres=[],
            tags={
                "Common Tag": 100,
            },
        ),
    ]

    vectors = build_content_features(games)

    first_game = vectors[1]

    assert first_game["tag:Rare Tag"] > first_game["tag:Common Tag"]


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


def test_cosine_similarity():
    vector_a = {
        "tag:RPG": 0.6,
        "tag:Fantasy": 0.8,
    }

    same_vector = {
        "tag:RPG": 0.6,
        "tag:Fantasy": 0.8,
    }

    unrelated_vector = {
        "tag:Racing": 1.0,
    }

    assert cosine_similarity(vector_a, same_vector) == pytest.approx(1.0)
    assert cosine_similarity(vector_a, unrelated_vector) == pytest.approx(0.0)
    assert cosine_similarity(vector_a, {}) == 0.0
