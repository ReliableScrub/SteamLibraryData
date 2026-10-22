from dataclasses import dataclass

from sklearn.cluster import KMeans
from sklearn.feature_extraction import DictVectorizer

from recommendations.baseline import BaselineScore
from recommendations.features import (
    cosine_similarity,
    normalize_vector,
)
from recommendations.feedback import final_feedback

DEFAULT_CLUSTER_COUNT = 5
RANDOM_STATE = 42
MIN_CLUSTERING_HISTORY = 15
MIN_POSITIVE_TRAINING_WEIGHT = 0.05

CLUSTER_WEIGHT = 0.50
NEIGHBOR_WEIGHT = 0.50


@dataclass(frozen=True)
class TasteClusterModel:
    vectorizer: DictVectorizer
    cluster_centers: list[dict[str, float]]
    cluster_sizes: list[int]


@dataclass(frozen=True)
class ClusterScore:
    app_id: int
    recommendation_score: float
    cluster_similarity: float
    cluster_index: int

    # Compatibility fields used by current audits/explanation code.
    nearest_positive_similarity: float
    nearest_positive_app_id: int | None

    # New production history signal.
    neighborhood_similarity: float = 0.0


def choose_cluster_count(
    positive_count,
):
    if positive_count < MIN_CLUSTERING_HISTORY:
        return None

    if positive_count < 20:
        return 2

    if positive_count < 30:
        return 3

    if positive_count < 50:
        return 4

    return DEFAULT_CLUSTER_COUNT


def positive_feedback_weight(game):
    """
    Return the positive feedback weight for a played game.

    This function name is intentionally preserved because persistence and
    existing audits already import it.
    """
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
        return 0.0

    if feedback.score <= 0:
        return 0.0

    return feedback.score * feedback.confidence


def train_taste_clusters(
    games,
    content_vectors,
    cluster_count=None,
):
    training_vectors = []
    training_weights = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        vector = content_vectors.get(game.app_id)

        if not vector:
            continue

        weight = positive_feedback_weight(game)

        if weight < MIN_POSITIVE_TRAINING_WEIGHT:
            continue

        training_vectors.append(vector)

        training_weights.append(weight)

    positive_count = len(training_vectors)

    if cluster_count is None:
        cluster_count = choose_cluster_count(positive_count)

    if cluster_count is None:
        return None

    if positive_count < cluster_count:
        return None

    vectorizer = DictVectorizer(sparse=False)

    matrix = vectorizer.fit_transform(training_vectors)

    model = KMeans(
        n_clusters=cluster_count,
        n_init=10,
        random_state=RANDOM_STATE,
    )

    model.fit(
        matrix,
        sample_weight=training_weights,
    )

    feature_names = vectorizer.get_feature_names_out()

    cluster_centers = []

    for center in model.cluster_centers_:
        center_vector = {
            feature: float(value)
            for feature, value in zip(
                feature_names,
                center,
            )
            if value != 0
        }

        cluster_centers.append(normalize_vector(center_vector))

    cluster_sizes = [0 for _ in range(cluster_count)]

    for label in model.labels_:
        cluster_sizes[int(label)] += 1

    return TasteClusterModel(
        vectorizer=vectorizer,
        cluster_centers=cluster_centers,
        cluster_sizes=cluster_sizes,
    )


def best_cluster_match(
    candidate_vector,
    cluster_model,
):
    best_index = 0
    best_similarity = 0.0

    for index, center in enumerate(cluster_model.cluster_centers):
        similarity = cosine_similarity(
            candidate_vector,
            center,
        )

        if similarity > best_similarity:
            best_similarity = similarity
            best_index = index

    return (
        best_index,
        best_similarity,
    )


def score_unplayed_games(
    games,
    content_vectors,
    cluster_model,
    baseline_scores,
):
    """
    Production K-Means score:

        50% closest taste-cluster similarity
        50% K=3 feedback-weighted neighborhood similarity
    """
    baseline_by_id = {score.app_id: score for score in baseline_scores}

    scores = []

    for game in games:
        if game.playtime_minutes > 0:
            continue

        candidate_vector = content_vectors.get(game.app_id)

        if not candidate_vector:
            continue

        baseline_score = baseline_by_id.get(game.app_id)

        if baseline_score is None:
            continue

        (
            cluster_index,
            cluster_similarity,
        ) = best_cluster_match(
            candidate_vector,
            cluster_model,
        )

        neighborhood_similarity = baseline_score.neighborhood_similarity

        recommendation_score = (
            CLUSTER_WEIGHT * cluster_similarity
            + NEIGHBOR_WEIGHT * neighborhood_similarity
        )

        scores.append(
            ClusterScore(
                app_id=game.app_id,
                recommendation_score=recommendation_score,
                cluster_similarity=cluster_similarity,
                cluster_index=cluster_index,
                # Compatibility values only. The final score no longer
                # uses a single nearest-positive game.
                nearest_positive_similarity=(
                    baseline_score.nearest_positive_adjusted_similarity
                ),
                nearest_positive_app_id=(baseline_score.nearest_positive_app_id),
                neighborhood_similarity=neighborhood_similarity,
            )
        )

    return scores
