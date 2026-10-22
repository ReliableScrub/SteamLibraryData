import json
import time

from recommendations.clustering import positive_feedback_weight
from recommendations.neighbors import MIN_POSITIVE_NEIGHBOR_WEIGHT
from storage.database import get_connection

MODEL_VERSION = 2
FEATURE_VERSION = 2


def count_training_games(games):
    count = 0

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        if not game.genres and not game.tags:
            continue

        weight = positive_feedback_weight(game)

        if weight < MIN_POSITIVE_NEIGHBOR_WEIGHT:
            continue

        count += 1

    return count


def count_rated_games(games):
    return sum(1 for game in games if game.rating is not None)


def count_implicit_games(games):
    return sum(
        1 for game in games if (game.playtime_minutes > 0 and game.rating is None)
    )


def serialize_feature(feature):
    return {
        "name": feature.name,
        "contribution": feature.contribution,
        "sources": list(feature.sources),
    }


def serialize_supporting_game(
    supporting_game,
):
    return {
        "app_id": supporting_game.app_id,
        "name": supporting_game.name,
        "raw_similarity": supporting_game.raw_similarity,
        "adjusted_similarity": supporting_game.adjusted_similarity,
        "shared_feature_count": supporting_game.shared_feature_count,
        "evidence": supporting_game.evidence,
        "feedback_weight": supporting_game.feedback_weight,
        "playtime_minutes": supporting_game.playtime_minutes,
        "shared_features": [
            serialize_feature(feature) for feature in supporting_game.shared_features
        ],
    }


def serialize_explanation(
    explanation,
):
    if explanation is None:
        return None

    data = {
        "taste_source": explanation.taste_source,
        "taste_features": [
            serialize_feature(feature) for feature in explanation.taste_features
        ],
        "supporting_games": [
            serialize_supporting_game(supporting_game)
            for supporting_game in explanation.supporting_games
        ],
    }

    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def save_recommendation_build(
    build,
    games,
):
    generated_at = int(time.time())

    training_game_count = count_training_games(games)

    rated_game_count = count_rated_games(games)

    implicit_game_count = count_implicit_games(games)

    explanations = (
        getattr(
            build,
            "explanations",
            {},
        )
        or {}
    )

    recommendation_rows = [
        (
            score.app_id,
            score.recommendation_score,
            None,
            serialize_explanation(explanations.get(score.app_id)),
            generated_at,
        )
        for score in build.scores
    ]

    with get_connection() as connection:
        # Replace the previous disposable recommendation build atomically.
        connection.execute("DELETE FROM game_recommendations")

        connection.execute("DELETE FROM recommendation_state")

        connection.executemany(
            """
            INSERT INTO game_recommendations (
                app_id,
                score,
                match_tier,
                explanation_json,
                generated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            recommendation_rows,
        )

        connection.execute(
            """
            INSERT INTO recommendation_state (
                id,
                method,
                model_version,
                feature_version,
                generated_at,
                training_game_count,
                rated_game_count,
                implicit_game_count,
                candidate_game_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                build.method,
                MODEL_VERSION,
                FEATURE_VERSION,
                generated_at,
                training_game_count,
                rated_game_count,
                implicit_game_count,
                len(build.scores),
            ),
        )


def load_recommendation_state():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                method,
                model_version,
                feature_version,
                generated_at,
                training_game_count,
                rated_game_count,
                implicit_game_count,
                candidate_game_count
            FROM recommendation_state
            WHERE id = 1
            """
        ).fetchone()


def load_saved_recommendations():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                app_id,
                score,
                match_tier,
                explanation_json,
                generated_at
            FROM game_recommendations
            ORDER BY score DESC, app_id
            """
        ).fetchall()
