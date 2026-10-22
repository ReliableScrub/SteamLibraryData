import pytest

from recommendations.data import RecommendationGameData
from recommendations.neighbors import (
    collect_positive_references,
    feedback_weighted_neighbor_similarity,
    find_positive_neighbors,
    mean_neighbor_similarity,
    score_unplayed_games,
    support_adjusted_similarity,
)


def make_game(
    app_id,
    name,
    rating=None,
    playtime_minutes=0,
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
    )


def test_support_adjustment_requires_feature_support():
    assert support_adjusted_similarity(
        1.0,
        1,
    ) == pytest.approx(0.1)

    assert support_adjusted_similarity(
        1.0,
        5,
    ) == pytest.approx(0.5)

    assert support_adjusted_similarity(
        1.0,
        10,
    ) == pytest.approx(1.0)

    assert support_adjusted_similarity(
        1.0,
        20,
    ) == pytest.approx(1.0)


def test_only_positive_played_games_become_references():
    games = [
        make_game(
            1,
            "Loved Game",
            rating=5,
            playtime_minutes=600,
        ),
        make_game(
            2,
            "Neutral Game",
            rating=3,
            playtime_minutes=600,
        ),
        make_game(
            3,
            "Disliked Game",
            rating=1,
            playtime_minutes=600,
        ),
        make_game(
            4,
            "Unplayed Game",
            rating=5,
            playtime_minutes=0,
        ),
    ]

    vectors = {
        game.app_id: {
            "tag:RPG": 1.0,
        }
        for game in games
    }

    references = collect_positive_references(
        games,
        vectors,
    )

    assert [reference.app_id for reference in references] == [
        1,
    ]


def test_neighbors_are_selected_by_similarity():
    references = collect_positive_references(
        [
            make_game(
                1,
                "Closest",
                rating=4,
                playtime_minutes=600,
            ),
            make_game(
                2,
                "Second Closest",
                rating=5,
                playtime_minutes=600,
            ),
            make_game(
                3,
                "Distant",
                rating=5,
                playtime_minutes=600,
            ),
        ],
        {
            1: {
                "tag:A": 0.9,
                "tag:B": 0.1,
            },
            2: {
                "tag:A": 0.7,
                "tag:B": 0.3,
            },
            3: {
                "tag:A": 0.1,
                "tag:B": 0.9,
            },
        },
    )

    candidate_vector = {
        "tag:A": 1.0,
        "tag:B": 0.0,
    }

    neighbors = find_positive_neighbors(
        candidate_vector,
        references,
        limit=2,
    )

    assert len(neighbors) == 2

    assert neighbors[0].app_id == 1
    assert neighbors[1].app_id == 2

    assert neighbors[0].adjusted_similarity > neighbors[1].adjusted_similarity


def test_neighbor_limit_is_respected():
    games = [
        make_game(
            app_id,
            f"Game {app_id}",
            rating=5,
            playtime_minutes=600,
        )
        for app_id in range(1, 6)
    ]

    vectors = {
        app_id: {
            "tag:RPG": 1.0,
            f"tag:Feature {app_id}": 0.5,
        }
        for app_id in range(1, 6)
    }

    references = collect_positive_references(
        games,
        vectors,
    )

    neighbors = find_positive_neighbors(
        {
            "tag:RPG": 1.0,
        },
        references,
        limit=3,
    )

    assert len(neighbors) == 3


def test_mean_neighbor_similarity_uses_multiple_neighbors():
    games = [
        make_game(
            1,
            "Reference A",
            rating=5,
            playtime_minutes=600,
        ),
        make_game(
            2,
            "Reference B",
            rating=5,
            playtime_minutes=600,
        ),
    ]

    vectors = {
        1: {
            "tag:A": 1.0,
            "tag:B": 1.0,
        },
        2: {
            "tag:A": 1.0,
            "tag:C": 1.0,
        },
    }

    references = collect_positive_references(
        games,
        vectors,
    )

    neighbors = find_positive_neighbors(
        {
            "tag:A": 1.0,
            "tag:B": 1.0,
        },
        references,
        limit=2,
    )

    expected = (neighbors[0].adjusted_similarity + neighbors[1].adjusted_similarity) / 2

    assert mean_neighbor_similarity(neighbors) == pytest.approx(expected)


def test_feedback_weighted_similarity_favors_stronger_evidence():
    games = [
        make_game(
            1,
            "Weak Positive",
            rating=4,
            playtime_minutes=600,
        ),
        make_game(
            2,
            "Strong Positive",
            rating=5,
            playtime_minutes=600,
        ),
    ]

    vectors = {
        1: {
            "tag:A": 1.0,
            "tag:B": 1.0,
        },
        2: {
            "tag:A": 1.0,
            "tag:C": 1.0,
        },
    }

    references = collect_positive_references(
        games,
        vectors,
    )

    neighbors = find_positive_neighbors(
        {
            "tag:A": 1.0,
            "tag:B": 0.8,
            "tag:C": 0.9,
        },
        references,
        limit=2,
    )

    expected = sum(
        neighbor.adjusted_similarity * neighbor.feedback_weight
        for neighbor in neighbors
    ) / sum(neighbor.feedback_weight for neighbor in neighbors)

    result = feedback_weighted_neighbor_similarity(neighbors)

    assert result == pytest.approx(expected)


def test_k1_matches_single_nearest_adjusted_similarity():
    games = [
        make_game(
            1,
            "Reference",
            rating=5,
            playtime_minutes=600,
        ),
        make_game(
            2,
            "Candidate",
        ),
    ]

    vectors = {
        1: {
            "tag:A": 1.0,
            "tag:B": 1.0,
        },
        2: {
            "tag:A": 1.0,
            "tag:B": 1.0,
        },
    }

    scores = score_unplayed_games(
        games,
        vectors,
        neighbor_count=1,
    )

    assert len(scores) == 1

    score = scores[0]

    assert len(score.neighbors) == 1

    assert score.similarity_mean == pytest.approx(
        score.neighbors[0].adjusted_similarity
    )

    assert score.feedback_weighted_mean == pytest.approx(
        score.neighbors[0].adjusted_similarity
    )


def test_score_unplayed_games_returns_requested_neighborhood():
    games = [
        make_game(
            1,
            "Reference A",
            rating=5,
            playtime_minutes=600,
        ),
        make_game(
            2,
            "Reference B",
            rating=5,
            playtime_minutes=600,
        ),
        make_game(
            3,
            "Reference C",
            rating=4,
            playtime_minutes=600,
        ),
        make_game(
            4,
            "Candidate",
        ),
    ]

    vectors = {
        1: {
            "tag:RPG": 1.0,
            "tag:A": 0.8,
        },
        2: {
            "tag:RPG": 1.0,
            "tag:B": 0.8,
        },
        3: {
            "tag:RPG": 1.0,
            "tag:C": 0.8,
        },
        4: {
            "tag:RPG": 1.0,
            "tag:A": 0.5,
            "tag:B": 0.5,
            "tag:C": 0.5,
        },
    }

    scores = score_unplayed_games(
        games,
        vectors,
        neighbor_count=3,
    )

    candidate = scores[0]

    assert candidate.app_id == 4
    assert len(candidate.neighbors) == 3
    assert candidate.similarity_mean > 0
    assert candidate.feedback_weighted_mean > 0
