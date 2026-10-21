from recommendations.baseline import (
    MIN_POSITIVE_REFERENCE_WEIGHT,
)
from recommendations.clustering import (
    DEFAULT_CLUSTER_COUNT,
    positive_feedback_weight,
    train_taste_clusters,
)
from recommendations.data import load_recommendation_games
from recommendations.features import (
    build_content_features,
    cosine_similarity,
)

TOP_FEATURES = 15
TOP_GAMES = 12


def main():
    games = load_recommendation_games()

    content_vectors = build_content_features(games)

    cluster_model = train_taste_clusters(
        games,
        content_vectors,
        cluster_count=DEFAULT_CLUSTER_COUNT,
    )

    if cluster_model is None:
        print("Not enough positive games to build taste clusters.")
        return

    positive_games = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        vector = content_vectors.get(game.app_id)

        if not vector:
            continue

        weight = positive_feedback_weight(game)

        if weight < MIN_POSITIVE_REFERENCE_WEIGHT:
            continue

        positive_games.append(game)

    print(f"Taste clusters: {len(cluster_model.cluster_centers)}")

    print(f"Qualified positive games: {len(positive_games)}")

    print()

    for cluster_index, center in enumerate(cluster_model.cluster_centers):
        print(f"Cluster {cluster_index}")

        print(f"Stored cluster size: {cluster_model.cluster_sizes[cluster_index]}")

        top_features = sorted(
            center.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )[:TOP_FEATURES]

        print()
        print("Top features:")

        for feature, value in top_features:
            print(f"  {value:7.4f}  {feature}")

        game_matches = []

        for game in positive_games:
            vector = content_vectors.get(game.app_id)

            similarity = cosine_similarity(
                vector,
                center,
            )

            game_matches.append(
                (
                    similarity,
                    game.name,
                    game.app_id,
                )
            )

        game_matches.sort(
            key=lambda item: (
                -item[0],
                item[1].lower(),
            )
        )

        print()
        print("Closest qualified positive games:")

        for (
            similarity,
            name,
            app_id,
        ) in game_matches[:TOP_GAMES]:
            print(f"  {similarity:7.4f}  {name} ({app_id})")

        print()
        print("-" * 70)
        print()


if __name__ == "__main__":
    main()
