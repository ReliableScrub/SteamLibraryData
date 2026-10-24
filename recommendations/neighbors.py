from dataclasses import dataclass

from recommendations.features import cosine_similarity
from recommendations.feedback import final_feedback

MIN_POSITIVE_NEIGHBOR_WEIGHT = 0.05
MIN_NEGATIVE_NEIGHBOR_WEIGHT = 0.05
FEATURE_SUPPORT_SATURATION = 10
DEFAULT_NEIGHBOR_COUNT = 3
DEFAULT_NEGATIVE_NEIGHBOR_COUNT = 3


@dataclass(frozen=True)
class PositiveReference:
    app_id: int
    vector: dict[str, float]
    feedback_score: float
    feedback_confidence: float
    feedback_weight: float


@dataclass(frozen=True)
class PositiveNeighbor:
    app_id: int
    similarity: float
    adjusted_similarity: float
    shared_features: int
    feedback_score: float
    feedback_confidence: float
    feedback_weight: float


@dataclass(frozen=True)
class NeighborhoodScore:
    app_id: int
    similarity_mean: float
    feedback_weighted_mean: float
    neighbors: tuple[PositiveNeighbor, ...]


@dataclass(frozen=True)
class NegativeReference:
    app_id: int
    vector: dict[str, float]
    feedback_score: float
    feedback_confidence: float
    feedback_weight: float


@dataclass(frozen=True)
class NegativeNeighbor:
    app_id: int
    similarity: float
    adjusted_similarity: float
    shared_features: int
    feedback_score: float
    feedback_confidence: float
    feedback_weight: float


@dataclass(frozen=True)
class NegativeNeighborhoodScore:
    app_id: int
    weighted_penalty: float
    neighbors: tuple[NegativeNeighbor, ...]


def shared_feature_count(vector_a, vector_b):
    features_a = {feature for feature, value in vector_a.items() if value != 0}
    features_b = {feature for feature, value in vector_b.items() if value != 0}
    return len(features_a & features_b)


def support_adjusted_similarity(similarity, shared_count):
    support = min(shared_count / FEATURE_SUPPORT_SATURATION, 1.0)
    return similarity * support


def collect_positive_references(
    games,
    content_vectors,
    minimum_feedback_weight=MIN_POSITIVE_NEIGHBOR_WEIGHT,
):
    references = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        vector = content_vectors.get(game.app_id)
        if not vector:
            continue

        feedback = final_feedback(
            rating=game.rating,
            manual_status=game.manual_status,
            playtime_minutes=game.playtime_minutes,
            hltb_main=game.hltb_main,
            hltb_main_extra=game.hltb_main_extra,
            hltb_completionist=game.hltb_completionist,
            hltb_all_styles=game.hltb_all_styles,
            achievement_total=game.achievement_total,
            achievements_unlocked=game.achievements_unlocked,
        )

        if feedback is None or feedback.score <= 0:
            continue

        feedback_weight = feedback.score * feedback.confidence
        if feedback_weight < minimum_feedback_weight:
            continue

        references.append(
            PositiveReference(
                app_id=game.app_id,
                vector=vector,
                feedback_score=feedback.score,
                feedback_confidence=feedback.confidence,
                feedback_weight=feedback_weight,
            )
        )

    return references


def collect_negative_references(
    games,
    content_vectors,
    minimum_feedback_weight=MIN_NEGATIVE_NEIGHBOR_WEIGHT,
):
    references = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        vector = content_vectors.get(game.app_id)
        if not vector:
            continue

        feedback = final_feedback(
            rating=game.rating,
            manual_status=game.manual_status,
            playtime_minutes=game.playtime_minutes,
            hltb_main=game.hltb_main,
            hltb_main_extra=game.hltb_main_extra,
            hltb_completionist=game.hltb_completionist,
            hltb_all_styles=game.hltb_all_styles,
            achievement_total=game.achievement_total,
            achievements_unlocked=game.achievements_unlocked,
        )

        if feedback is None or feedback.score >= 0:
            continue

        feedback_weight = abs(feedback.score * feedback.confidence)
        if feedback_weight < minimum_feedback_weight:
            continue

        references.append(
            NegativeReference(
                app_id=game.app_id,
                vector=vector,
                feedback_score=feedback.score,
                feedback_confidence=feedback.confidence,
                feedback_weight=feedback_weight,
            )
        )

    return references


def find_positive_neighbors(
    candidate_vector,
    references,
    limit=DEFAULT_NEIGHBOR_COUNT,
):
    if limit <= 0:
        return ()

    neighbors = []

    for reference in references:
        similarity = cosine_similarity(candidate_vector, reference.vector)
        if similarity <= 0:
            continue

        shared_count = shared_feature_count(candidate_vector, reference.vector)
        adjusted_similarity = support_adjusted_similarity(similarity, shared_count)
        if adjusted_similarity <= 0:
            continue

        neighbors.append(
            PositiveNeighbor(
                app_id=reference.app_id,
                similarity=similarity,
                adjusted_similarity=adjusted_similarity,
                shared_features=shared_count,
                feedback_score=reference.feedback_score,
                feedback_confidence=reference.feedback_confidence,
                feedback_weight=reference.feedback_weight,
            )
        )

    neighbors.sort(
        key=lambda neighbor: (
            -neighbor.adjusted_similarity,
            -neighbor.similarity,
            -neighbor.feedback_weight,
            neighbor.app_id,
        )
    )

    return tuple(neighbors[:limit])


def find_negative_neighbors(
    candidate_vector,
    references,
    limit=DEFAULT_NEGATIVE_NEIGHBOR_COUNT,
):
    if limit <= 0:
        return ()

    neighbors = []

    for reference in references:
        similarity = cosine_similarity(candidate_vector, reference.vector)
        if similarity <= 0:
            continue

        shared_count = shared_feature_count(candidate_vector, reference.vector)
        adjusted_similarity = support_adjusted_similarity(similarity, shared_count)
        if adjusted_similarity <= 0:
            continue

        neighbors.append(
            NegativeNeighbor(
                app_id=reference.app_id,
                similarity=similarity,
                adjusted_similarity=adjusted_similarity,
                shared_features=shared_count,
                feedback_score=reference.feedback_score,
                feedback_confidence=reference.feedback_confidence,
                feedback_weight=reference.feedback_weight,
            )
        )

    neighbors.sort(
        key=lambda neighbor: (
            -neighbor.adjusted_similarity,
            -neighbor.feedback_weight,
            -neighbor.similarity,
            neighbor.app_id,
        )
    )

    return tuple(neighbors[:limit])


def mean_neighbor_similarity(neighbors):
    if not neighbors:
        return 0.0

    return sum(neighbor.adjusted_similarity for neighbor in neighbors) / len(neighbors)


def feedback_weighted_neighbor_similarity(neighbors):
    if not neighbors:
        return 0.0

    total_weight = sum(neighbor.feedback_weight for neighbor in neighbors)
    if total_weight <= 0:
        return mean_neighbor_similarity(neighbors)

    weighted_similarity = sum(
        neighbor.adjusted_similarity * neighbor.feedback_weight
        for neighbor in neighbors
    )

    return weighted_similarity / total_weight


def negative_neighbor_penalty(neighbors):
    if not neighbors:
        return 0.0

    # Do not normalize away rating strength. A 1-star neighbor carries twice
    # the avoidance strength of an equally similar 2-star neighbor.
    return sum(
        neighbor.adjusted_similarity * neighbor.feedback_weight
        for neighbor in neighbors
    ) / len(neighbors)


def score_unplayed_games(
    games,
    content_vectors,
    neighbor_count=DEFAULT_NEIGHBOR_COUNT,
    minimum_feedback_weight=MIN_POSITIVE_NEIGHBOR_WEIGHT,
):
    references = collect_positive_references(
        games,
        content_vectors,
        minimum_feedback_weight=minimum_feedback_weight,
    )

    scores = []

    for game in games:
        if game.playtime_minutes > 0:
            continue

        candidate_vector = content_vectors.get(game.app_id)
        if not candidate_vector:
            continue

        neighbors = find_positive_neighbors(
            candidate_vector,
            references,
            limit=neighbor_count,
        )

        scores.append(
            NeighborhoodScore(
                app_id=game.app_id,
                similarity_mean=mean_neighbor_similarity(neighbors),
                feedback_weighted_mean=feedback_weighted_neighbor_similarity(neighbors),
                neighbors=neighbors,
            )
        )

    return scores


def score_negative_unplayed_games(
    games,
    content_vectors,
    neighbor_count=DEFAULT_NEGATIVE_NEIGHBOR_COUNT,
    minimum_feedback_weight=MIN_NEGATIVE_NEIGHBOR_WEIGHT,
):
    references = collect_negative_references(
        games,
        content_vectors,
        minimum_feedback_weight=minimum_feedback_weight,
    )

    scores = []

    for game in games:
        if game.playtime_minutes > 0:
            continue

        candidate_vector = content_vectors.get(game.app_id)
        if not candidate_vector:
            continue

        neighbors = find_negative_neighbors(
            candidate_vector,
            references,
            limit=neighbor_count,
        )

        scores.append(
            NegativeNeighborhoodScore(
                app_id=game.app_id,
                weighted_penalty=negative_neighbor_penalty(neighbors),
                neighbors=neighbors,
            )
        )

    return scores
