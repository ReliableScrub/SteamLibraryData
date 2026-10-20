from dataclasses import dataclass

from recommendations.features import cosine_similarity
from recommendations.feedback import final_feedback

MIN_POSITIVE_REFERENCE_WEIGHT = 0.05
FEATURE_SUPPORT_SATURATION = 10


@dataclass(frozen=True)
class BaselineScore:
    app_id: int

    profile_similarity: float

    nearest_positive_similarity: float
    nearest_positive_adjusted_similarity: float
    nearest_positive_shared_features: int
    nearest_positive_app_id: int | None

    nearest_positive_feedback_score: float
    nearest_positive_feedback_confidence: float
    nearest_positive_feedback_weight: float


def shared_feature_count(vector_a, vector_b):
    features_a = {feature for feature, value in vector_a.items() if value != 0}

    features_b = {feature for feature, value in vector_b.items() if value != 0}

    return len(features_a & features_b)


def support_adjusted_similarity(
    similarity,
    shared_count,
):
    if similarity <= 0 or shared_count <= 0:
        return 0.0

    support = min(
        shared_count / FEATURE_SUPPORT_SATURATION,
        1.0,
    )

    return similarity * support


def score_unplayed_games(
    games,
    content_vectors,
    profile,
):
    positive_references = []

    for game in games:
        # A nearest-positive reference must be a game the user actually played.
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

        if feedback is None:
            continue

        if feedback.score <= 0:
            continue

        feedback_weight = feedback.score * feedback.confidence

        if feedback_weight < MIN_POSITIVE_REFERENCE_WEIGHT:
            continue

        positive_references.append(
            (
                game.app_id,
                vector,
                feedback.score,
                feedback.confidence,
                feedback_weight,
            )
        )

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

        nearest_positive_similarity = 0.0
        nearest_positive_adjusted_similarity = 0.0
        nearest_positive_shared_features = 0
        nearest_positive_app_id = None

        nearest_feedback_score = 0.0
        nearest_feedback_confidence = 0.0
        nearest_feedback_weight = 0.0

        for (
            reference_app_id,
            reference_vector,
            feedback_score,
            feedback_confidence,
            feedback_weight,
        ) in positive_references:
            similarity = cosine_similarity(
                candidate_vector,
                reference_vector,
            )

            shared_count = shared_feature_count(
                candidate_vector,
                reference_vector,
            )

            adjusted_similarity = support_adjusted_similarity(
                similarity,
                shared_count,
            )

            if adjusted_similarity <= 0:
                continue

            better_match = adjusted_similarity > nearest_positive_adjusted_similarity

            same_adjusted_but_better_raw = (
                adjusted_similarity == nearest_positive_adjusted_similarity
                and similarity > nearest_positive_similarity
            )

            same_similarity_but_stronger_feedback = (
                adjusted_similarity == nearest_positive_adjusted_similarity
                and similarity == nearest_positive_similarity
                and feedback_weight > nearest_feedback_weight
            )

            if (
                better_match
                or same_adjusted_but_better_raw
                or same_similarity_but_stronger_feedback
            ):
                nearest_positive_similarity = similarity
                nearest_positive_adjusted_similarity = adjusted_similarity
                nearest_positive_shared_features = shared_count
                nearest_positive_app_id = reference_app_id

                nearest_feedback_score = feedback_score
                nearest_feedback_confidence = feedback_confidence
                nearest_feedback_weight = feedback_weight

        scores.append(
            BaselineScore(
                app_id=game.app_id,
                profile_similarity=profile_similarity,
                nearest_positive_similarity=nearest_positive_similarity,
                nearest_positive_adjusted_similarity=nearest_positive_adjusted_similarity,
                nearest_positive_shared_features=nearest_positive_shared_features,
                nearest_positive_app_id=nearest_positive_app_id,
                nearest_positive_feedback_score=nearest_feedback_score,
                nearest_positive_feedback_confidence=nearest_feedback_confidence,
                nearest_positive_feedback_weight=nearest_feedback_weight,
            )
        )

    return scores
