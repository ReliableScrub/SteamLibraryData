from dataclasses import dataclass

from recommendations.baseline import (
    BaselineScore,
)
from recommendations.baseline import (
    score_unplayed_games as score_baseline_games,
)
from recommendations.clustering import (
    ClusterScore,
    train_taste_clusters,
)
from recommendations.clustering import (
    score_unplayed_games as score_cluster_games,
)
from recommendations.data import load_recommendation_games
from recommendations.diversity import rerank_mmr
from recommendations.features import build_content_features
from recommendations.persistence import save_recommendation_build
from recommendations.profile import build_preference_profile

METHOD_BASELINE = "baseline"
METHOD_KMEANS = "kmeans"
TOP_PICK_COUNT = 10


@dataclass(frozen=True)
class RecommendationBuild:
    method: str
    cluster_count: int | None
    scores: list[BaselineScore | ClusterScore]
    top_picks: list[BaselineScore | ClusterScore]


def rank_scores(scores):
    return sorted(
        scores,
        key=lambda score: (
            -score.recommendation_score,
            score.app_id,
        ),
    )


def build_recommendations(games):
    content_vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        content_vectors,
    )

    baseline_scores = score_baseline_games(
        games,
        content_vectors,
        profile,
    )

    cluster_model = train_taste_clusters(
        games,
        content_vectors,
    )

    if cluster_model is None:
        method = METHOD_BASELINE
        cluster_count = None

        scores = rank_scores(baseline_scores)
    else:
        method = METHOD_KMEANS
        cluster_count = len(cluster_model.cluster_centers)

        cluster_scores = score_cluster_games(
            games,
            content_vectors,
            cluster_model,
            baseline_scores,
        )

        scores = rank_scores(cluster_scores)

    top_picks = rerank_mmr(
        scores,
        content_vectors,
        limit=min(
            TOP_PICK_COUNT,
            len(scores),
        ),
    )

    return RecommendationBuild(
        method=method,
        cluster_count=cluster_count,
        scores=scores,
        top_picks=top_picks,
    )


def generate_recommendations():
    games = load_recommendation_games()

    return build_recommendations(games)


def generate_and_save_recommendations():
    games = load_recommendation_games()

    result = build_recommendations(games)

    save_recommendation_build(
        result,
        games,
    )

    return result
