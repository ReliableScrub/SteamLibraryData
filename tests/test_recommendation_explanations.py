from types import SimpleNamespace

import pytest

from recommendations.data import RecommendationGameData
from recommendations.explanations import (
    build_recommendation_explanations,
)


def make_game(
    app_id,
    name,
    playtime_minutes=0,
    rating=None,
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
        genres=[],
        tags={},
    )


def make_neighbor(
    app_id,
    raw_similarity=1.0,
    adjusted_similarity=1.0,
    shared_feature_count=2,
    evidence="implicit",
    feedback_weight=0.5,
):
    return SimpleNamespace(
        app_id=app_id,
        raw_similarity=raw_similarity,
        adjusted_similarity=adjusted_similarity,
        shared_feature_count=shared_feature_count,
        evidence=evidence,
        feedback_weight=feedback_weight,
    )


def build_one_explanation(
    games,
    vectors,
    profile,
    recommendation_score,
    method="baseline",
    cluster_model=None,
    feature_limit=3,
):
    baseline_score = SimpleNamespace(
        app_id=recommendation_score.app_id,
        neighbors=getattr(recommendation_score, "neighbors", ()),
    )

    return build_recommendation_explanations(
        games=games,
        content_vectors=vectors,
        profile=profile,
        baseline_scores=[baseline_score],
        recommendation_scores=[recommendation_score],
        method=method,
        cluster_model=cluster_model,
        feature_limit=feature_limit,
    )[recommendation_score.app_id]


def test_genre_and_tag_contributions_merge_into_one_feature():
    games = [make_game(10, "Candidate")]
    vectors = {
        10: {
            "genre:RPG": 1.0,
            "tag:RPG": 1.0,
            "tag:Turn-Based": 1.0,
        },
    }
    profile = {
        "genre:RPG": 1.0,
        "tag:RPG": 1.0,
    }
    score = SimpleNamespace(app_id=10, recommendation_score=0.9)

    explanation = build_one_explanation(games, vectors, profile, score)

    rpg = next(
        feature for feature in explanation.taste_features if feature.name == "RPG"
    )
    assert rpg.sources == ("genre", "tag")
    assert rpg.contribution == pytest.approx(2 / (2**0.5 * 3**0.5))
    assert all(feature.name != "genre:RPG" for feature in explanation.taste_features)


def test_generic_features_are_suppressed_case_insensitively():
    games = [make_game(10, "Candidate")]
    vectors = {
        10: {
            "tag:Free to Play": 1.0,
            "tag:Casual": 1.0,
            "genre:Indie": 1.0,
            "tag:RPG": 1.0,
        },
    }
    score = SimpleNamespace(app_id=10, recommendation_score=0.9)

    explanation = build_one_explanation(
        games,
        vectors,
        vectors[10],
        score,
    )

    assert [feature.name for feature in explanation.taste_features] == ["RPG"]


def test_negative_feature_contributions_are_excluded():
    games = [make_game(10, "Candidate")]
    vectors = {10: {"tag:RPG": 1.0, "tag:Racing": 1.0}}
    profile = {"tag:RPG": 1.0, "tag:Racing": -1.0}
    score = SimpleNamespace(app_id=10, recommendation_score=0.5)

    explanation = build_one_explanation(games, vectors, profile, score)

    assert [feature.name for feature in explanation.taste_features] == ["RPG"]
    assert explanation.taste_features[0].contribution > 0.0


def test_supporting_games_uses_three_played_references_and_scales_traits():
    games = [
        make_game(1, "Played One", playtime_minutes=120),
        make_game(2, "Played Two", playtime_minutes=240),
        make_game(3, "Played Three", playtime_minutes=360),
        make_game(4, "Played Four", playtime_minutes=480),
        make_game(10, "Candidate"),
    ]
    common_vector = {"tag:RPG": 1.0, "tag:Story Rich": 1.0}
    vectors = {
        1: dict(common_vector),
        2: dict(common_vector),
        3: dict(common_vector),
        4: dict(common_vector),
        10: dict(common_vector),
    }
    neighbors = [
        make_neighbor(1, 1.0, 0.75, 2),
        make_neighbor(2, 1.0, 0.70, 2),
        make_neighbor(3, 1.0, 0.65, 2),
        make_neighbor(4, 1.0, 0.60, 2),
    ]
    score = SimpleNamespace(
        app_id=10,
        recommendation_score=0.8,
        neighbors=neighbors,
    )

    explanation = build_one_explanation(
        games,
        vectors,
        common_vector,
        score,
        feature_limit=10,
    )

    assert [game.app_id for game in explanation.supporting_games] == [1, 2, 3]
    assert [game.name for game in explanation.supporting_games] == [
        "Played One",
        "Played Two",
        "Played Three",
    ]
    assert explanation.supporting_games[0].shared_feature_count == 2
    assert sum(
        feature.contribution
        for feature in explanation.supporting_games[0].shared_features
    ) == pytest.approx(0.75)
    assert all(game.playtime_minutes > 0 for game in explanation.supporting_games)


def test_unplayed_games_are_not_used_as_supporting_history():
    games = [
        make_game(1, "Not Actually Played"),
        make_game(10, "Candidate"),
    ]
    vectors = {
        1: {"tag:RPG": 1.0},
        10: {"tag:RPG": 1.0},
    }
    score = SimpleNamespace(
        app_id=10,
        recommendation_score=0.8,
        neighbors=[make_neighbor(1)],
    )

    explanation = build_one_explanation(
        games,
        vectors,
        vectors[10],
        score,
    )

    assert explanation.supporting_games == ()


def test_kmeans_uses_the_candidate_cluster_center_for_taste_features():
    games = [make_game(10, "Candidate")]
    vectors = {
        10: {
            "tag:Turn-Based": 1.0,
            "tag:Open World": 1.0,
        },
    }
    profile = {"tag:Open World": 1.0}
    cluster_model = SimpleNamespace(
        cluster_centers=[{"tag:Turn-Based": 1.0}],
    )
    score = SimpleNamespace(
        app_id=10,
        recommendation_score=0.9,
        cluster_index=0,
    )

    explanation = build_one_explanation(
        games,
        vectors,
        profile,
        score,
        method="kmeans",
        cluster_model=cluster_model,
    )

    assert explanation.taste_source == "cluster"
    assert [feature.name for feature in explanation.taste_features] == ["Turn-Based"]


def test_feature_limit_is_applied_after_merging_and_sorting():
    games = [make_game(10, "Candidate")]
    vectors = {
        10: {
            "tag:RPG": 1.0,
            "tag:Turn-Based": 1.0,
            "tag:Story Rich": 1.0,
            "tag:Choices Matter": 1.0,
        },
    }
    score = SimpleNamespace(app_id=10, recommendation_score=0.9)

    explanation = build_one_explanation(
        games,
        vectors,
        vectors[10],
        score,
        feature_limit=2,
    )

    assert len(explanation.taste_features) == 2
    assert all(feature.contribution > 0.0 for feature in explanation.taste_features)
