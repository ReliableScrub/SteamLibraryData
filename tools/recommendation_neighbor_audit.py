from recommendations.clustering import (
    train_taste_clusters,
)
from recommendations.data import (
    load_recommendation_games,
)
from recommendations.features import (
    build_content_features,
    cosine_similarity,
)
from recommendations.neighbors import (
    score_unplayed_games,
)

TOP_RESULTS = 30

CLUSTER_WEIGHT = 0.50
NEIGHBOR_WEIGHT = 0.50


def best_cluster_similarity(
    vector,
    cluster_model,
):
    if cluster_model is None:
        return 0.0

    return max(
        cosine_similarity(
            vector,
            center,
        )
        for center in cluster_model.cluster_centers
    )


def combine_score(
    cluster_similarity,
    neighborhood_similarity,
):
    return (
        CLUSTER_WEIGHT * cluster_similarity + NEIGHBOR_WEIGHT * neighborhood_similarity
    )


def print_neighbors(
    label,
    score,
    games_by_id,
):
    print(
        f"    {label}: "
        f"mean={score.similarity_mean:.4f}"
        " | "
        f"weighted="
        f"{score.feedback_weighted_mean:.4f}"
    )

    for index, neighbor in enumerate(
        score.neighbors,
        start=1,
    ):
        game = games_by_id.get(neighbor.app_id)

        name = game.name if game is not None else f"<{neighbor.app_id}>"

        rating = (
            f"{game.rating} stars"
            if (game is not None and game.rating is not None)
            else "implicit"
        )

        playtime = game.playtime_minutes / 60 if game is not None else 0.0

        print(f"        {index}. {name}")

        print(
            "           "
            f"similarity="
            f"{neighbor.similarity:.4f}"
            " | "
            f"adjusted="
            f"{neighbor.adjusted_similarity:.4f}"
            " | "
            f"shared="
            f"{neighbor.shared_features}"
        )

        print(
            "           "
            f"evidence="
            f"{rating}"
            " | "
            f"weight="
            f"{neighbor.feedback_weight:.3f}"
            " | "
            f"playtime="
            f"{playtime:.1f}h"
        )


def main():
    games = load_recommendation_games()

    games_by_id = {game.app_id: game for game in games}

    content_vectors = build_content_features(games)

    cluster_model = train_taste_clusters(
        games,
        content_vectors,
    )

    if cluster_model is None:
        print("Not enough positive history for K-Means.")
        return

    k1_scores = score_unplayed_games(
        games,
        content_vectors,
        neighbor_count=1,
    )

    k3_scores = score_unplayed_games(
        games,
        content_vectors,
        neighbor_count=3,
    )

    k5_scores = score_unplayed_games(
        games,
        content_vectors,
        neighbor_count=5,
    )

    k1_by_id = {score.app_id: score for score in k1_scores}

    k3_by_id = {score.app_id: score for score in k3_scores}

    k5_by_id = {score.app_id: score for score in k5_scores}

    rows = []

    for app_id, k3 in k3_by_id.items():
        vector = content_vectors.get(app_id)

        if not vector:
            continue

        cluster_similarity = best_cluster_similarity(
            vector,
            cluster_model,
        )

        k1 = k1_by_id[app_id]
        k5 = k5_by_id[app_id]

        rows.append(
            (
                app_id,
                cluster_similarity,
                combine_score(
                    cluster_similarity,
                    k1.similarity_mean,
                ),
                combine_score(
                    cluster_similarity,
                    k3.similarity_mean,
                ),
                combine_score(
                    cluster_similarity,
                    k3.feedback_weighted_mean,
                ),
                combine_score(
                    cluster_similarity,
                    k5.similarity_mean,
                ),
                combine_score(
                    cluster_similarity,
                    k5.feedback_weighted_mean,
                ),
            )
        )

    # Use K=3 feedback-weighted ranking for the human inspection.
    rows.sort(
        key=lambda row: (
            -row[4],
            row[0],
        )
    )

    print("Positive-neighborhood audit")
    print("=" * 100)
    print(f"Candidates: {len(rows)}")
    print("Displayed ranking: K=3 feedback-weighted neighborhood")
    print()

    for rank, row in enumerate(
        rows[:TOP_RESULTS],
        start=1,
    ):
        (
            app_id,
            cluster_similarity,
            k1_final,
            k3_mean_final,
            k3_weighted_final,
            k5_mean_final,
            k5_weighted_final,
        ) = row

        game = games_by_id[app_id]

        print(f"{rank:>2}. {k3_weighted_final:.4f}  {game.name}")

        print(f"    Cluster similarity: {cluster_similarity:.4f}")

        print(
            "    Combined scores: "
            f"K1={k1_final:.4f}"
            " | "
            f"K3 mean="
            f"{k3_mean_final:.4f}"
            " | "
            f"K3 weighted="
            f"{k3_weighted_final:.4f}"
            " | "
            f"K5 mean="
            f"{k5_mean_final:.4f}"
            " | "
            f"K5 weighted="
            f"{k5_weighted_final:.4f}"
        )

        print_neighbors(
            "K=1",
            k1_by_id[app_id],
            games_by_id,
        )

        print_neighbors(
            "K=3",
            k3_by_id[app_id],
            games_by_id,
        )

        print_neighbors(
            "K=5",
            k5_by_id[app_id],
            games_by_id,
        )

        print()

    print("-" * 100)
    print("Audit complete.")


if __name__ == "__main__":
    main()
