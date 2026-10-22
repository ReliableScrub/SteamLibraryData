from dataclasses import dataclass

from recommendations.features import cosine_similarity
from recommendations.neighbors import (
    FEATURE_SUPPORT_SATURATION as NEIGHBOR_FEATURE_SUPPORT_SATURATION,
)
from recommendations.neighbors import (
    MIN_POSITIVE_NEIGHBOR_WEIGHT,
    PositiveNeighbor,
)
from recommendations.neighbors import (
    score_unplayed_games as score_neighbor_games,
)
from recommendations.neighbors import (
    shared_feature_count as neighbor_shared_feature_count,
)
from recommendations.neighbors import (
    support_adjusted_similarity as neighbor_support_adjusted_similarity,
)

# Compatibility name used by existing persistence/tests/audits.
MIN_POSITIVE_REFERENCE_WEIGHT = MIN_POSITIVE_NEIGHBOR_WEIGHT

# Compatibility name used by existing baseline tests/audits.
FEATURE_SUPPORT_SATURATION = NEIGHBOR_FEATURE_SUPPORT_SATURATION

PROFILE_WEIGHT = 0.50

# Keep the old constant name available while its meaning becomes the
# positive-neighborhood half of the score.
NEAREST_POSITIVE_WEIGHT = 0.50
NEIGHBOR_WEIGHT = NEAREST_POSITIVE_WEIGHT

PRODUCTION_NEIGHBOR_COUNT = 3


@dataclass(frozen=True)
class BaselineScore:
    app_id: int
    recommendation_score: float

    profile_similarity: float

    # Compatibility fields.
    #
    # These now describe the strongest individual member of the K=3
    # neighborhood. They no longer determine the recommendation score.
    nearest_positive_similarity: float
    nearest_positive_adjusted_similarity: float
    nearest_positive_shared_features: int
    nearest_positive_app_id: int | None

    nearest_positive_feedback_score: float
    nearest_positive_feedback_confidence: float
    nearest_positive_feedback_weight: float

    # New production signal.
    neighborhood_similarity: float = 0.0
    neighbors: tuple[PositiveNeighbor, ...] = ()


def shared_feature_count(
    vector_a,
    vector_b,
):
    """
    Compatibility wrapper for existing callers.
    """
    return neighbor_shared_feature_count(
        vector_a,
        vector_b,
    )


def support_adjusted_similarity(
    similarity,
    shared_count,
):
    """
    Compatibility wrapper for existing callers.
    """
    return neighbor_support_adjusted_similarity(
        similarity,
        shared_count,
    )


def score_unplayed_games(
    games,
    content_vectors,
    profile,
):
    """
    Production baseline:

        50% preference-profile similarity
        50% K=3 feedback-weighted positive-neighborhood similarity

    The nearest-positive fields remain temporarily so older code can
    continue to inspect the strongest individual neighbor.
    """
    neighborhood_scores = score_neighbor_games(
        games,
        content_vectors,
        neighbor_count=PRODUCTION_NEIGHBOR_COUNT,
    )

    neighborhood_by_id = {score.app_id: score for score in neighborhood_scores}

    scores = []

    for game in games:
        if game.playtime_minutes > 0:
            continue

        candidate_vector = content_vectors.get(game.app_id)

        if not candidate_vector:
            continue

        profile_similarity = cosine_similarity(
            profile,
            candidate_vector,
        )

        neighborhood_score = neighborhood_by_id.get(game.app_id)

        if neighborhood_score is None:
            neighborhood_similarity = 0.0
            neighbors = ()
        else:
            neighborhood_similarity = neighborhood_score.feedback_weighted_mean

            neighbors = neighborhood_score.neighbors

        if neighbors:
            nearest = neighbors[0]

            nearest_positive_similarity = nearest.similarity

            nearest_positive_adjusted_similarity = nearest.adjusted_similarity

            nearest_positive_shared_features = nearest.shared_features

            nearest_positive_app_id = nearest.app_id

            nearest_feedback_score = nearest.feedback_score

            nearest_feedback_confidence = nearest.feedback_confidence

            nearest_feedback_weight = nearest.feedback_weight
        else:
            nearest_positive_similarity = 0.0
            nearest_positive_adjusted_similarity = 0.0
            nearest_positive_shared_features = 0
            nearest_positive_app_id = None

            nearest_feedback_score = 0.0
            nearest_feedback_confidence = 0.0
            nearest_feedback_weight = 0.0

        recommendation_score = (
            PROFILE_WEIGHT * profile_similarity
            + NEIGHBOR_WEIGHT * neighborhood_similarity
        )

        scores.append(
            BaselineScore(
                app_id=game.app_id,
                recommendation_score=recommendation_score,
                profile_similarity=profile_similarity,
                nearest_positive_similarity=nearest_positive_similarity,
                nearest_positive_adjusted_similarity=nearest_positive_adjusted_similarity,
                nearest_positive_shared_features=nearest_positive_shared_features,
                nearest_positive_app_id=nearest_positive_app_id,
                nearest_positive_feedback_score=nearest_feedback_score,
                nearest_positive_feedback_confidence=nearest_feedback_confidence,
                nearest_positive_feedback_weight=nearest_feedback_weight,
                neighborhood_similarity=neighborhood_similarity,
                neighbors=neighbors,
            )
        )

    return scores
