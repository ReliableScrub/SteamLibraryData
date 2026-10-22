from dataclasses import dataclass

from recommendations.features import cosine_similarity
from recommendations.neighbors import (
    PositiveNeighbor,
    score_unplayed_games as score_neighbor_games,
)

PROFILE_WEIGHT = 0.50
NEIGHBOR_WEIGHT = 0.50
PRODUCTION_NEIGHBOR_COUNT = 3


@dataclass(frozen=True)
class BaselineScore:
    app_id: int
    recommendation_score: float
    profile_similarity: float
    neighborhood_similarity: float
    neighbors: tuple[PositiveNeighbor, ...]


def score_unplayed_games(
    games,
    content_vectors,
    profile,
):
    """
    Score unplayed games using:

        50% aggregate preference-profile similarity
        50% K=3 feedback-weighted positive-neighborhood similarity
    """
    neighborhood_scores = score_neighbor_games(
        games,
        content_vectors,
        neighbor_count=PRODUCTION_NEIGHBOR_COUNT,
    )

    neighborhood_by_id = {
        score.app_id: score
        for score in neighborhood_scores
    }

    scores = []

    for game in games:
        if game.playtime_minutes > 0:
            continue

        candidate_vector = content_vectors.get(
            game.app_id
        )

        if not candidate_vector:
            continue

        profile_similarity = cosine_similarity(
            profile,
            candidate_vector,
        )

        neighborhood_score = neighborhood_by_id.get(
            game.app_id
        )

        if neighborhood_score is None:
            neighborhood_similarity = 0.0
            neighbors = ()
        else:
            neighborhood_similarity = (
                neighborhood_score.feedback_weighted_mean
            )
            neighbors = neighborhood_score.neighbors

        recommendation_score = (
            PROFILE_WEIGHT
            * profile_similarity
            + NEIGHBOR_WEIGHT
            * neighborhood_similarity
        )

        scores.append(
            BaselineScore(
                app_id=game.app_id,
                recommendation_score=recommendation_score,
                profile_similarity=profile_similarity,
                neighborhood_similarity=neighborhood_similarity,
                neighbors=neighbors,
            )
        )

    return scores
