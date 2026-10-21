from dataclasses import dataclass

from sklearn.cluster import KMeans
from sklearn.feature_extraction import DictVectorizer

from recommendations.baseline import (
    MIN_POSITIVE_REFERENCE_WEIGHT,
    combine_baseline_score,
)
from recommendations.features import (
    cosine_similarity,
    normalize_vector,
)
from recommendations.feedback import final_feedback

DEFAULT_CLUSTER_COUNT = 5
RANDOM_STATE = 42
MIN_CLUSTERING_HISTORY = 15


def choose_cluster_count(positive_count):
    if positive_count < MIN_CLUSTERING_HISTORY:
        return None

    if positive_count < 20:
        return 2

    if positive_count < 30:
        return 3

    if positive_count < 50:
        return 4

    return 5


@dataclass
class TasteClusterModel:
    vectorizer: DictVectorizer
    cluster_centers: list[dict[str, float]]
    cluster_sizes: list[int]


@dataclass(frozen=True)
class ClusterScore:
    app_id: int
    recommendation_score: float

    cluster_similarity: float
    cluster_index: int | None

    nearest_positive_similarity: float
    nearest_positive_app_id: int | None


def positive_feedback_weight(game):
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


def center_to_dict(vectorizer, center):
    feature_names = vectorizer.get_feature_names_out()

    return {
        feature_names[index]: float(value)
        for index, value in enumerate(center)
        if value != 0
    }


def train_taste_clusters(
    games,
    content_vectors,
    cluster_count=None,
):
    positive_vectors = []
    sample_weights = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        vector = content_vectors.get(game.app_id)

        if not vector:
            continue

        weight = positive_feedback_weight(game)

        if weight < MIN_POSITIVE_REFERENCE_WEIGHT:
            continue

        positive_vectors.append(vector)
        sample_weights.append(weight)

    # Production behavior:
    # choose K automatically from the amount of qualified positive history.
    #
    # Audits/tests can still explicitly pass cluster_count to force a
    # particular K value.
    if cluster_count is None:
        cluster_count = choose_cluster_count(len(positive_vectors))

    # Too little qualified history for clustering.
    if cluster_count is None:
        return None

    # Protect explicit audit/test requests from asking for more clusters
    # than there are usable training games.
    if len(positive_vectors) < cluster_count:
        return None

    vectorizer = DictVectorizer(
        sparse=False,
    )

    matrix = vectorizer.fit_transform(positive_vectors)

    model = KMeans(
        n_clusters=cluster_count,
        random_state=RANDOM_STATE,
        n_init=10,
    )

    model.fit(
        matrix,
        sample_weight=sample_weights,
    )

    cluster_sizes = [0 for _ in range(cluster_count)]

    for label in model.labels_:
        cluster_sizes[int(label)] += 1

    cluster_centers = []

    for center in model.cluster_centers_:
        center_dict = center_to_dict(
            vectorizer,
            center,
        )

        cluster_centers.append(normalize_vector(center_dict))

    return TasteClusterModel(
        vectorizer=vectorizer,
        cluster_centers=cluster_centers,
        cluster_sizes=cluster_sizes,
    )


def score_unplayed_games(
    games,
    content_vectors,
    cluster_model,
    baseline_scores,
):
    if cluster_model is None:
        return []

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

        best_similarity = 0.0
        best_cluster_index = None

        for cluster_index, center in enumerate(cluster_model.cluster_centers):
            similarity = cosine_similarity(
                candidate_vector,
                center,
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster_index = cluster_index

        recommendation_score = combine_baseline_score(
            best_similarity,
            baseline_score.nearest_positive_adjusted_similarity,
        )

        scores.append(
            ClusterScore(
                app_id=game.app_id,
                recommendation_score=recommendation_score,
                cluster_similarity=best_similarity,
                cluster_index=best_cluster_index,
                nearest_positive_similarity=(
                    baseline_score.nearest_positive_adjusted_similarity
                ),
                nearest_positive_app_id=baseline_score.nearest_positive_app_id,
            )
        )

    return scores
