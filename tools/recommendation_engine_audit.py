from collections import Counter

from recommendations.data import load_recommendation_games
from recommendations.engine import build_recommendations

TOP_RESULTS = 50


def main():
    games = load_recommendation_games()

    games_by_id = {game.app_id: game for game in games}

    result = build_recommendations(games)

    print(f"Recommendation method: {result.method}")

    print(f"Cluster count: {result.cluster_count}")

    print(f"Recommendation candidates: {len(result.scores)}")

    print()
    print(f"Top {min(TOP_RESULTS, len(result.scores))} recommendations")

    print("-" * 110)

    cluster_counts = Counter()

    for rank, score in enumerate(
        result.scores[:TOP_RESULTS],
        start=1,
    ):
        game = games_by_id.get(score.app_id)

        name = game.name if game is not None else "<unknown>"

        print(f"{rank:>3}. {score.recommendation_score:.4f}  {name} ({score.app_id})")

        cluster_similarity = getattr(
            score,
            "cluster_similarity",
            None,
        )

        cluster_index = getattr(
            score,
            "cluster_index",
            None,
        )

        nearest_similarity = getattr(
            score,
            "nearest_positive_similarity",
            None,
        )

        nearest_app_id = getattr(
            score,
            "nearest_positive_app_id",
            None,
        )

        if cluster_index is not None:
            cluster_counts[cluster_index] += 1

        if nearest_app_id is not None:
            nearest_game = games_by_id.get(nearest_app_id)

            nearest_name = (
                nearest_game.name if nearest_game is not None else "<unknown>"
            )
        else:
            nearest_name = "<none>"

        if cluster_similarity is not None:
            print(
                f"     cluster="
                f"{cluster_index} | "
                f"cluster similarity="
                f"{cluster_similarity:.4f}"
            )

        if nearest_similarity is not None:
            print(
                f"     nearest positive="
                f"{nearest_similarity:.4f} | "
                f"{nearest_name} "
                f"({nearest_app_id})"
            )

    if cluster_counts:
        print()
        print("Top-result cluster distribution")

        print("-" * 110)

        for cluster_index in sorted(cluster_counts):
            count = cluster_counts[cluster_index]

            percentage = (
                count
                / min(
                    TOP_RESULTS,
                    len(result.scores),
                )
                * 100
            )

            print(f"Cluster {cluster_index}: {count} ({percentage:.1f}%)")

    print()
    print("Audit complete.")


if __name__ == "__main__":
    main()
