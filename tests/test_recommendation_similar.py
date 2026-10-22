import pytest

from recommendations.data import RecommendationGameData
from recommendations.similar import SimilarGameIndex


def make_game(
    app_id,
    name,
    *,
    playtime_minutes=0,
    genres=None,
    tags=None,
):
    return RecommendationGameData(
        app_id=app_id,
        name=name,
        playtime_minutes=playtime_minutes,
        playtime_2weeks_minutes=0,
        last_played_timestamp=0,
        manual_status=None,
        rating=None,
        metadata_checked=True,
        genres=genres or [],
        tags=tags or {},
    )


def test_similar_games_are_ranked_by_content_match():
    games = [
        make_game(
            1,
            "Reference RPG",
            playtime_minutes=600,
            genres=["RPG"],
            tags={
                "Fantasy": 100,
                "Open World": 90,
                "Magic": 80,
            },
        ),
        make_game(
            2,
            "Strong Match",
            genres=["RPG"],
            tags={
                "Fantasy": 100,
                "Open World": 90,
                "Magic": 80,
            },
        ),
        make_game(
            3,
            "Weak Match",
            genres=["RPG"],
            tags={
                "Fantasy": 100,
            },
        ),
        make_game(
            4,
            "Unrelated",
            genres=["Racing"],
            tags={
                "Driving": 100,
            },
        ),
    ]

    index = SimilarGameIndex(games)
    scores = index.find_similar(1)

    assert [score.app_id for score in scores] == [2, 3]
    assert scores[0].adjusted_similarity > scores[1].adjusted_similarity


def test_similar_games_default_to_unplayed_candidates():
    games = [
        make_game(
            1,
            "Reference",
            playtime_minutes=600,
            tags={"Strategy": 100, "Management": 80},
        ),
        make_game(
            2,
            "Played Match",
            playtime_minutes=120,
            tags={"Strategy": 100, "Management": 80},
        ),
        make_game(
            3,
            "Unplayed Match",
            tags={"Strategy": 100, "Management": 80},
        ),
    ]

    index = SimilarGameIndex(games)
    scores = index.find_similar(1)

    assert [score.app_id for score in scores] == [3]


def test_sparse_perfect_match_is_support_adjusted():
    games = [
        make_game(
            1,
            "Reference",
            playtime_minutes=600,
            tags={"Action": 100, "Indie": 80},
        ),
        make_game(
            2,
            "Candidate",
            tags={"Action": 100, "Indie": 80},
        ),
    ]

    index = SimilarGameIndex(games)
    score = index.find_similar(1)[0]

    assert score.similarity == pytest.approx(1.0)
    assert score.shared_feature_count == 2
    assert score.adjusted_similarity == pytest.approx(0.2)


def test_shared_traits_merge_genre_and_tag_names():
    games = [
        make_game(
            1,
            "Reference",
            playtime_minutes=600,
            genres=["RPG"],
            tags={"RPG": 100, "Fantasy": 80},
        ),
        make_game(
            2,
            "Candidate",
            genres=["RPG"],
            tags={"RPG": 100, "Fantasy": 80},
        ),
    ]

    index = SimilarGameIndex(games)
    score = index.find_similar(1)[0]

    assert score.shared_traits.count("RPG") == 1
    assert "Fantasy" in score.shared_traits
