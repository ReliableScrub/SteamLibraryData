import pytest

from recommendations.baseline import (
    NEIGHBOR_WEIGHT,
    PROFILE_WEIGHT,
    score_unplayed_games,
)
from recommendations.data import RecommendationGameData
from recommendations.features import build_content_features
from recommendations.profile import build_preference_profile


def make_game(
    app_id,
    name,
    rating=None,
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
        rating=rating,
        metadata_checked=True,
        genres=genres or [],
        tags=tags or {},
    )


def build_scores(games):
    vectors = build_content_features(
        games
    )

    profile = build_preference_profile(
        games,
        vectors,
    )

    scores = score_unplayed_games(
        games,
        vectors,
        profile,
    )

    return {
        score.app_id: score
        for score in scores
    }


def test_baseline_prefers_candidate_matching_positive_taste():
    games = [
        make_game(
            app_id=1,
            name="Loved RPG",
            rating=5,
            playtime_minutes=600,
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
                "Choices Matter": 80,
            },
        ),
        make_game(
            app_id=2,
            name="Disliked Racing Game",
            rating=1,
            playtime_minutes=600,
            genres=["Racing"],
            tags={
                "Racing": 100,
                "Driving": 80,
            },
        ),
        make_game(
            app_id=3,
            name="RPG Candidate",
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
                "Choices Matter": 80,
            },
        ),
        make_game(
            app_id=4,
            name="Racing Candidate",
            genres=["Racing"],
            tags={
                "Racing": 100,
                "Driving": 80,
            },
        ),
    ]

    scores = build_scores(
        games
    )

    assert (
        scores[3].profile_similarity
        > scores[4].profile_similarity
    )

    assert (
        scores[3].neighborhood_similarity
        > scores[4].neighborhood_similarity
    )

    assert [
        neighbor.app_id
        for neighbor in scores[3].neighbors
    ] == [1]


def test_neighborhood_membership_is_chosen_by_similarity_not_rating_strength():
    games = [
        make_game(
            app_id=1,
            name="Five Star Fantasy RPG",
            rating=5,
            playtime_minutes=600,
            genres=["RPG"],
            tags={
                "Fantasy": 100,
                "Open World": 80,
            },
        ),
        make_game(
            app_id=2,
            name="Four Star Tactical RPG",
            rating=4,
            playtime_minutes=600,
            genres=["RPG"],
            tags={
                "Turn-Based Tactics": 100,
                "Party-Based RPG": 80,
                "Strategy": 70,
            },
        ),
        make_game(
            app_id=3,
            name="Tactical RPG Candidate",
            genres=["RPG"],
            tags={
                "Turn-Based Tactics": 100,
                "Party-Based RPG": 80,
                "Strategy": 70,
            },
        ),
    ]

    scores = build_scores(
        games
    )

    candidate = scores[3]

    assert candidate.neighbors
    assert candidate.neighbors[0].app_id == 2
    assert candidate.neighbors[0].similarity > 0
    assert candidate.neighbors[0].feedback_score == 0.5
    assert candidate.neighbors[0].feedback_confidence == 1.0
    assert candidate.neighbors[0].feedback_weight == 0.5


def test_very_weak_implicit_feedback_is_not_used_as_neighbor():
    games = [
        make_game(
            app_id=1,
            name="Barely Played Game",
            playtime_minutes=30,
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
            },
        ),
        make_game(
            app_id=2,
            name="Candidate",
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
            },
        ),
    ]

    scores = build_scores(
        games
    )

    candidate = scores[2]

    assert candidate.neighbors == ()
    assert candidate.neighborhood_similarity == 0.0


def test_recommendation_score_uses_profile_and_neighborhood():
    games = [
        make_game(
            app_id=1,
            name="Loved RPG",
            rating=5,
            playtime_minutes=600,
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
                "Story Rich": 80,
            },
        ),
        make_game(
            app_id=2,
            name="Candidate",
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
                "Story Rich": 80,
            },
        ),
    ]

    scores = build_scores(
        games
    )

    candidate = scores[2]

    expected = (
        PROFILE_WEIGHT
        * candidate.profile_similarity
        + NEIGHBOR_WEIGHT
        * candidate.neighborhood_similarity
    )

    assert candidate.recommendation_score == pytest.approx(
        expected
    )
