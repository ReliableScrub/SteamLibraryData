import math
from dataclasses import dataclass

from recommendations.features import cosine_similarity
from recommendations.neighbors import (
    PositiveNeighbor,
    score_negative_unplayed_games,
)
from recommendations.neighbors import (
    score_unplayed_games as score_neighbor_games,
)

PROFILE_WEIGHT = 0.50
POSITIVE_NEIGHBOR_WEIGHT = 0.50
NEGATIVE_NEIGHBOR_PENALTY_WEIGHT = 0.45

PUBLIC_RECEPTION_START_RATIO = 0.70
PUBLIC_RECEPTION_FULL_PENALTY_RATIO = 0.30
PUBLIC_RECEPTION_MIN_REVIEWS = 100
PUBLIC_RECEPTION_MAX_PENALTY = 0.18

PRODUCTION_NEIGHBOR_COUNT = 3
PRODUCTION_NEGATIVE_NEIGHBOR_COUNT = 3


@dataclass(frozen=True)
class BaselineScore:
    app_id: int
    recommendation_score: float
    profile_similarity: float
    neighborhood_similarity: float
    neighbors: tuple[PositiveNeighbor, ...]


def public_reception_penalty(game):
    positive = game.steamspy_positive
    negative = game.steamspy_negative

    if positive is None or negative is None:
        return 0.0

    total_reviews = positive + negative

    if total_reviews < PUBLIC_RECEPTION_MIN_REVIEWS:
        return 0.0

    positive_ratio = positive / total_reviews

    if positive_ratio >= PUBLIC_RECEPTION_START_RATIO:
        return 0.0

    penalty_range = PUBLIC_RECEPTION_START_RATIO - PUBLIC_RECEPTION_FULL_PENALTY_RATIO

    badness = (PUBLIC_RECEPTION_START_RATIO - positive_ratio) / penalty_range

    badness = min(max(badness, 0.0), 1.0)

    confidence = min(
        1.0,
        math.log10(total_reviews + 1) / 3.0,
    )

    return PUBLIC_RECEPTION_MAX_PENALTY * badness * confidence


def score_unplayed_games(
    games,
    content_vectors,
    profile,
):
    """
    Score unplayed games using:

        50% signed aggregate preference-profile similarity
        50% K=3 feedback-weighted positive-neighborhood similarity
        minus a similarity-weighted K=3 negative-neighborhood penalty

    The negative penalty preserves explicit rating strength:
    a 1-star near-neighbor penalizes more than an equally similar 2-star game.
    """
    neighborhood_scores = score_neighbor_games(
        games,
        content_vectors,
        neighbor_count=PRODUCTION_NEIGHBOR_COUNT,
    )

    negative_scores = score_negative_unplayed_games(
        games,
        content_vectors,
        neighbor_count=PRODUCTION_NEGATIVE_NEIGHBOR_COUNT,
    )

    neighborhood_by_id = {score.app_id: score for score in neighborhood_scores}

    negative_by_id = {score.app_id: score for score in negative_scores}

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

        negative_score = negative_by_id.get(game.app_id)
        negative_penalty = (
            0.0 if negative_score is None else negative_score.weighted_penalty
        )

        reception_penalty = public_reception_penalty(game)

        recommendation_score = (
            PROFILE_WEIGHT * profile_similarity
            + POSITIVE_NEIGHBOR_WEIGHT * neighborhood_similarity
            - NEGATIVE_NEIGHBOR_PENALTY_WEIGHT * negative_penalty
            - reception_penalty
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
