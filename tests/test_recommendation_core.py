import math

import pytest

from recommendations.features import build_content_features, cosine_similarity
from recommendations.feedback import (
    FeedbackSignal,
    PlaytimeRatios,
    achievement_progress,
    combine_implicit_feedback,
    explicit_rating_feedback,
    final_feedback,
    implicit_feedback,
    manual_status_feedback,
    playtime_ratios,
)
from recommendations.neighbors import (
    collect_positive_references,
    find_positive_neighbors,
    support_adjusted_similarity,
)
from recommendations.neighbors import (
    score_unplayed_games as score_neighbor_games,
)
from recommendations.profile import build_preference_profile
from recommendations.similar import SimilarGameIndex


def test_content_features_include_weighted_genres_tags_and_normalize(make_game):
    game = make_game(
        1,
        "Test RPG",
        genres=["RPG"],
        tags={
            "Story Rich": 100,
            "Fantasy": 25,
        },
    )

    vector = build_content_features([game])[1]

    assert "genre:RPG" in vector
    assert "tag:Story Rich" in vector
    assert "tag:Fantasy" in vector
    assert vector["tag:Story Rich"] > vector["tag:Fantasy"]

    magnitude = math.sqrt(sum(value * value for value in vector.values()))
    assert magnitude == pytest.approx(1.0)


def test_rare_tag_gets_more_weight_than_common_tag(make_game):
    games = [
        make_game(1, "One", tags={"Common": 100, "Rare": 100}),
        make_game(2, "Two", tags={"Common": 100}),
        make_game(3, "Three", tags={"Common": 100}),
    ]

    vector = build_content_features(games)[1]

    assert vector["tag:Rare"] > vector["tag:Common"]


def test_cosine_similarity_handles_same_unrelated_and_empty_vectors():
    vector = {
        "tag:RPG": 0.6,
        "tag:Fantasy": 0.8,
    }

    assert cosine_similarity(vector, vector) == pytest.approx(1.0)
    assert cosine_similarity(vector, {"tag:Racing": 1.0}) == pytest.approx(0.0)
    assert cosine_similarity(vector, {}) == 0.0


@pytest.mark.parametrize(
    ("rating", "expected"),
    [
        (1, -1.0),
        (2, -0.5),
        (3, 0.0),
        (4, 0.5),
        (5, 1.0),
    ],
)
def test_explicit_rating_feedback_mapping(rating, expected):
    assert explicit_rating_feedback(rating) == FeedbackSignal(
        score=expected,
        confidence=1.0,
    )


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_explicit_rating_rejects_invalid_values(rating):
    with pytest.raises(ValueError):
        explicit_rating_feedback(rating)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Completed", FeedbackSignal(score=0.35, confidence=0.30)),
        ("Dropped", FeedbackSignal(score=-0.45, confidence=0.35)),
        ("On Hold", None),
        (None, None),
    ],
)
def test_manual_status_feedback_mapping(status, expected):
    assert manual_status_feedback(status) == expected


def test_achievement_progress_validates_and_calculates():
    assert achievement_progress(100, 25) == pytest.approx(0.25)
    assert achievement_progress(40, 40) == pytest.approx(1.0)
    assert achievement_progress(None, None) is None
    assert achievement_progress(0, 0) is None

    with pytest.raises(ValueError):
        achievement_progress(10, 11)


def test_playtime_ratios_preserve_available_hltb_metrics():
    ratios = playtime_ratios(
        playtime_minutes=600,
        hltb_main=5,
        hltb_main_extra=10,
        hltb_completionist=20,
        hltb_all_styles=None,
    )

    assert ratios == PlaytimeRatios(
        main_story=pytest.approx(2.0),
        main_extra=pytest.approx(1.0),
        completionist=pytest.approx(0.5),
        all_styles=None,
    )


def test_implicit_feedback_requires_meaningful_play_and_combines_signals():
    assert (
        implicit_feedback(
            playtime_minutes=0,
            hltb_main=10,
            hltb_main_extra=20,
            hltb_completionist=30,
            hltb_all_styles=15,
            achievement_total=100,
            achievements_unlocked=50,
        )
        is None
    )

    feedback = implicit_feedback(
        playtime_minutes=600,
        hltb_main=8,
        hltb_main_extra=12,
        hltb_completionist=20,
        hltb_all_styles=10,
        achievement_total=40,
        achievements_unlocked=20,
    )

    assert feedback is not None
    assert feedback.score > 0
    assert 0 < feedback.confidence <= 0.60

    combined = combine_implicit_feedback(
        FeedbackSignal(score=0.50, confidence=0.40),
        FeedbackSignal(score=0.50, confidence=0.40),
        None,
    )

    assert combined.score == pytest.approx(0.50)
    assert combined.confidence > 0.40


def test_explicit_rating_overrides_implicit_feedback():
    feedback = final_feedback(
        rating=1,
        manual_status="Completed",
        playtime_minutes=100 * 60,
        hltb_main=10,
        hltb_main_extra=20,
        hltb_completionist=30,
        hltb_all_styles=15,
        achievement_total=100,
        achievements_unlocked=100,
    )

    assert feedback == FeedbackSignal(
        score=-1.0,
        confidence=1.0,
    )


def test_game_without_feedback_returns_none():
    assert (
        final_feedback(
            rating=None,
            manual_status=None,
            playtime_minutes=0,
            hltb_main=None,
            hltb_main_extra=None,
            hltb_completionist=None,
            hltb_all_styles=None,
            achievement_total=None,
            achievements_unlocked=None,
        )
        is None
    )


def test_preference_profile_points_toward_liked_content(make_game):
    games = [
        make_game(
            1,
            "Liked RPG",
            rating=5,
            playtime_minutes=600,
            genres=["RPG"],
            tags={"Turn-Based": 100, "Story Rich": 80},
        ),
        make_game(
            2,
            "Disliked Racer",
            rating=1,
            playtime_minutes=600,
            genres=["Racing"],
            tags={"Driving": 100, "Sports": 80},
        ),
        make_game(
            3,
            "RPG Candidate",
            genres=["RPG"],
            tags={"Turn-Based": 100, "Story Rich": 80},
        ),
        make_game(
            4,
            "Racing Candidate",
            genres=["Racing"],
            tags={"Driving": 100, "Sports": 80},
        ),
    ]

    vectors = build_content_features(games)
    profile = build_preference_profile(games, vectors)

    rpg_score = cosine_similarity(profile, vectors[3])
    racing_score = cosine_similarity(profile, vectors[4])

    assert rpg_score > 0
    assert racing_score < 0
    assert rpg_score > racing_score


@pytest.mark.parametrize(
    ("shared_count", "expected"),
    [
        (1, 0.1),
        (5, 0.5),
        (10, 1.0),
        (20, 1.0),
    ],
)
def test_support_adjustment_caps_at_full_similarity(shared_count, expected):
    assert support_adjusted_similarity(1.0, shared_count) == pytest.approx(expected)


def test_neighbors_use_only_positive_played_references_and_rank_similarity(make_game):
    games = [
        make_game(1, "Closest", rating=4, playtime_minutes=600),
        make_game(2, "Second", rating=5, playtime_minutes=600),
        make_game(3, "Disliked", rating=1, playtime_minutes=600),
        make_game(4, "Unplayed", rating=5),
    ]

    vectors = {
        1: {"tag:A": 0.9, "tag:B": 0.1},
        2: {"tag:A": 0.7, "tag:B": 0.3},
        3: {"tag:A": 1.0},
        4: {"tag:A": 1.0},
    }

    references = collect_positive_references(games, vectors)

    assert {reference.app_id for reference in references} == {1, 2}

    neighbors = find_positive_neighbors(
        {"tag:A": 1.0, "tag:B": 0.0},
        references,
        limit=2,
    )

    assert [neighbor.app_id for neighbor in neighbors] == [1, 2]
    assert neighbors[0].adjusted_similarity > neighbors[1].adjusted_similarity


def test_neighbor_scoring_returns_requested_neighborhood(make_game):
    games = [
        make_game(1, "A", rating=5, playtime_minutes=600),
        make_game(2, "B", rating=5, playtime_minutes=600),
        make_game(3, "C", rating=4, playtime_minutes=600),
        make_game(4, "Candidate"),
    ]

    vectors = {
        1: {"tag:RPG": 1.0, "tag:A": 0.8},
        2: {"tag:RPG": 1.0, "tag:B": 0.8},
        3: {"tag:RPG": 1.0, "tag:C": 0.8},
        4: {
            "tag:RPG": 1.0,
            "tag:A": 0.5,
            "tag:B": 0.5,
            "tag:C": 0.5,
        },
    }

    scores = score_neighbor_games(
        games,
        vectors,
        neighbor_count=3,
    )

    assert len(scores) == 1
    assert scores[0].app_id == 4
    assert len(scores[0].neighbors) == 3
    assert scores[0].feedback_weighted_mean > 0


def test_similar_games_rank_content_and_default_to_unplayed(make_game):
    games = [
        make_game(
            1,
            "Reference",
            playtime_minutes=600,
            genres=["RPG"],
            tags={"Fantasy": 100, "Open World": 90, "Magic": 80},
        ),
        make_game(
            2,
            "Strong Unplayed Match",
            genres=["RPG"],
            tags={"Fantasy": 100, "Open World": 90, "Magic": 80},
        ),
        make_game(
            3,
            "Weak Unplayed Match",
            genres=["RPG"],
            tags={"Fantasy": 100},
        ),
        make_game(
            4,
            "Played Match",
            playtime_minutes=120,
            genres=["RPG"],
            tags={"Fantasy": 100, "Open World": 90, "Magic": 80},
        ),
    ]

    scores = SimilarGameIndex(games).find_similar(1)

    assert [score.app_id for score in scores] == [2, 3]
    assert scores[0].adjusted_similarity > scores[1].adjusted_similarity


def test_similar_games_support_adjust_sparse_matches_and_merge_trait_names(make_game):
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

    score = SimilarGameIndex(games).find_similar(1)[0]

    assert score.similarity == pytest.approx(1.0)
    assert score.adjusted_similarity < score.similarity
    assert score.shared_traits.count("RPG") == 1
    assert "Fantasy" in score.shared_traits
