import pytest

from recommendations.baseline import score_unplayed_games
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

    vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        vectors,
    )

    scores = score_unplayed_games(
        games,
        vectors,
        profile,
    )

    scores_by_id = {score.app_id: score for score in scores}

    assert scores_by_id[3].profile_similarity > scores_by_id[4].profile_similarity

    assert scores_by_id[3].nearest_positive_app_id == 1

    assert (
        scores_by_id[3].nearest_positive_adjusted_similarity
        > scores_by_id[4].nearest_positive_adjusted_similarity
    )


def test_nearest_game_is_chosen_by_similarity_not_rating_strength():
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

    vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        vectors,
    )

    scores = score_unplayed_games(
        games,
        vectors,
        profile,
    )

    candidate = next(score for score in scores if score.app_id == 3)

    assert candidate.nearest_positive_app_id == 2
    assert candidate.nearest_positive_similarity > 0
    assert candidate.nearest_positive_adjusted_similarity > 0

    assert candidate.nearest_positive_feedback_score == 0.5

    assert candidate.nearest_positive_feedback_confidence == 1.0

    assert candidate.nearest_positive_feedback_weight == 0.5


def test_very_weak_implicit_feedback_is_not_used_as_reference():
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

    vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        vectors,
    )

    scores = score_unplayed_games(
        games,
        vectors,
        profile,
    )

    candidate = next(score for score in scores if score.app_id == 2)

    assert candidate.nearest_positive_app_id is None
    assert candidate.nearest_positive_similarity == 0.0
    assert candidate.nearest_positive_adjusted_similarity == 0.0


def test_sparse_perfect_match_is_discounted():
    games = [
        make_game(
            app_id=1,
            name="Sparse Reference",
            rating=5,
            playtime_minutes=600,
            tags={
                "Action": 100,
                "Indie": 80,
            },
        ),
        make_game(
            app_id=2,
            name="Sparse Candidate",
            tags={
                "Action": 100,
                "Indie": 80,
            },
        ),
    ]

    vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        vectors,
    )

    scores = score_unplayed_games(
        games,
        vectors,
        profile,
    )

    candidate = next(score for score in scores if score.app_id == 2)

    assert candidate.nearest_positive_similarity == pytest.approx(1.0)
    assert candidate.nearest_positive_shared_features == 2

    assert candidate.nearest_positive_adjusted_similarity == pytest.approx(0.2)


def test_rich_perfect_match_keeps_full_similarity():
    shared_tags = {f"Tag {index}": 100 - index for index in range(10)}

    games = [
        make_game(
            app_id=1,
            name="Rich Reference",
            rating=5,
            playtime_minutes=600,
            tags=shared_tags,
        ),
        make_game(
            app_id=2,
            name="Rich Candidate",
            tags=shared_tags,
        ),
    ]

    vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        vectors,
    )

    scores = score_unplayed_games(
        games,
        vectors,
        profile,
    )

    candidate = next(score for score in scores if score.app_id == 2)

    assert candidate.nearest_positive_similarity == pytest.approx(1.0)
    assert candidate.nearest_positive_shared_features == 10

    assert candidate.nearest_positive_adjusted_similarity == pytest.approx(1.0)


def test_zero_similarity_does_not_create_nearest_reference():
    games = [
        make_game(
            app_id=1,
            name="Loved RPG",
            rating=5,
            playtime_minutes=600,
            tags={
                "Turn-Based": 100,
                "Fantasy": 80,
            },
        ),
        make_game(
            app_id=2,
            name="Unrelated Candidate",
            tags={
                "Racing": 100,
                "Driving": 80,
            },
        ),
    ]

    vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        vectors,
    )

    scores = score_unplayed_games(
        games,
        vectors,
        profile,
    )

    candidate = next(score for score in scores if score.app_id == 2)

    assert candidate.nearest_positive_app_id is None
    assert candidate.nearest_positive_similarity == 0.0
    assert candidate.nearest_positive_adjusted_similarity == 0.0
    assert candidate.nearest_positive_shared_features == 0
