import pytest

from recommendations.baseline import (
    score_unplayed_games as score_baseline_games,
)
from recommendations.clustering import (
    CLUSTER_WEIGHT,
    NEIGHBOR_WEIGHT,
    choose_cluster_count,
    train_taste_clusters,
)
from recommendations.clustering import (
    score_unplayed_games as score_cluster_games,
)
from recommendations.data import RecommendationGameData
from recommendations.features import build_content_features
from recommendations.profile import build_preference_profile


def make_game(
    app_id,
    name,
    *,
    playtime_minutes=0,
    rating=None,
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
        hltb_main=None,
        hltb_main_extra=None,
        hltb_completionist=None,
        hltb_all_styles=None,
        hltb_checked=False,
        hltb_match_status=None,
        achievement_total=None,
        achievements_unlocked=None,
        achievements_checked=False,
    )


def build_games():
    return [
        make_game(
            1,
            "Fantasy RPG",
            playtime_minutes=600,
            rating=5,
            genres=["RPG"],
            tags={
                "Fantasy": 100,
                "Story Rich": 80,
            },
        ),
        make_game(
            2,
            "Tactical RPG",
            playtime_minutes=500,
            rating=5,
            genres=["RPG", "Strategy"],
            tags={
                "Turn-Based": 100,
                "Strategy": 80,
            },
        ),
        make_game(
            3,
            "Action Game",
            playtime_minutes=400,
            rating=4,
            genres=["Action"],
            tags={
                "Action": 100,
                "Hack and Slash": 80,
            },
        ),
        make_game(
            4,
            "Adventure Game",
            playtime_minutes=300,
            rating=4,
            genres=["Adventure"],
            tags={
                "Story Rich": 100,
                "Exploration": 80,
            },
        ),
        make_game(
            5,
            "RPG Candidate",
            genres=["RPG"],
            tags={
                "Fantasy": 100,
                "Story Rich": 80,
            },
        ),
        make_game(
            6,
            "Action Candidate",
            genres=["Action"],
            tags={
                "Action": 100,
                "Hack and Slash": 80,
            },
        ),
    ]


def build_positive_games(count):
    games = []

    for index in range(count):
        games.append(
            make_game(
                index + 1,
                f"Positive Game {index + 1}",
                playtime_minutes=600,
                rating=5,
                genres=["RPG"],
                tags={
                    "RPG": 100,
                    f"Feature {index % 5}": 80,
                },
            )
        )

    return games


def build_baseline_scores(
    games,
    vectors,
):
    profile = build_preference_profile(
        games,
        vectors,
    )

    return score_baseline_games(
        games,
        vectors,
        profile,
    )


def test_choose_cluster_count_uses_baseline_for_tiny_history():
    assert choose_cluster_count(0) is None
    assert choose_cluster_count(5) is None
    assert choose_cluster_count(14) is None


def test_choose_cluster_count_uses_two_clusters_for_15_to_19():
    assert choose_cluster_count(15) == 2
    assert choose_cluster_count(19) == 2


def test_choose_cluster_count_uses_three_clusters_for_20_to_29():
    assert choose_cluster_count(20) == 3
    assert choose_cluster_count(29) == 3


def test_choose_cluster_count_uses_four_clusters_for_30_to_49():
    assert choose_cluster_count(30) == 4
    assert choose_cluster_count(49) == 4


def test_choose_cluster_count_uses_five_clusters_for_50_or_more():
    assert choose_cluster_count(50) == 5
    assert choose_cluster_count(100) == 5
    assert choose_cluster_count(500) == 5


def test_kmeans_builds_requested_clusters():
    games = build_games()
    vectors = build_content_features(games)

    model = train_taste_clusters(
        games,
        vectors,
        cluster_count=2,
    )

    assert model is not None
    assert len(model.cluster_centers) == 2
    assert len(model.cluster_sizes) == 2
    assert sum(model.cluster_sizes) == 4


def test_kmeans_centers_are_nonempty():
    games = build_games()
    vectors = build_content_features(games)

    model = train_taste_clusters(
        games,
        vectors,
        cluster_count=2,
    )

    assert model is not None

    assert all(center for center in model.cluster_centers)


def test_kmeans_scores_only_unplayed_games():
    games = build_games()
    vectors = build_content_features(games)

    baseline_scores = build_baseline_scores(
        games,
        vectors,
    )

    model = train_taste_clusters(
        games,
        vectors,
        cluster_count=2,
    )

    scores = score_cluster_games(
        games,
        vectors,
        model,
        baseline_scores,
    )

    assert {score.app_id for score in scores} == {5, 6}


def test_kmeans_candidate_has_cluster_match():
    games = build_games()
    vectors = build_content_features(games)

    baseline_scores = build_baseline_scores(
        games,
        vectors,
    )

    model = train_taste_clusters(
        games,
        vectors,
        cluster_count=2,
    )

    scores = score_cluster_games(
        games,
        vectors,
        model,
        baseline_scores,
    )

    assert all(score.cluster_index is not None for score in scores)

    assert all(score.cluster_similarity > 0 for score in scores)


def test_kmeans_uses_neighborhood_component():
    games = build_games()
    vectors = build_content_features(games)

    baseline_scores = build_baseline_scores(
        games,
        vectors,
    )

    baseline_by_id = {score.app_id: score for score in baseline_scores}

    model = train_taste_clusters(
        games,
        vectors,
        cluster_count=2,
    )

    scores = score_cluster_games(
        games,
        vectors,
        model,
        baseline_scores,
    )

    for score in scores:
        baseline_score = baseline_by_id[score.app_id]

        assert score.neighborhood_similarity == pytest.approx(
            baseline_score.neighborhood_similarity
        )

        expected_score = (
            CLUSTER_WEIGHT * score.cluster_similarity
            + NEIGHBOR_WEIGHT * baseline_score.neighborhood_similarity
        )

        assert score.recommendation_score == pytest.approx(expected_score)


def test_kmeans_returns_none_when_cluster_count_is_too_large():
    games = build_games()
    vectors = build_content_features(games)

    model = train_taste_clusters(
        games,
        vectors,
        cluster_count=10,
    )

    assert model is None


def test_kmeans_automatically_selects_cluster_count():
    games = build_positive_games(20)
    vectors = build_content_features(games)

    model = train_taste_clusters(
        games,
        vectors,
    )

    assert model is not None
    assert len(model.cluster_centers) == 3
    assert len(model.cluster_sizes) == 3
    assert sum(model.cluster_sizes) == 20


def test_kmeans_automatic_mode_returns_none_for_tiny_history():
    games = build_positive_games(14)
    vectors = build_content_features(games)

    model = train_taste_clusters(
        games,
        vectors,
    )

    assert model is None
