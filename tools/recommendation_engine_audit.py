from recommendations.baseline import (
    NEIGHBOR_WEIGHT as BASELINE_NEIGHBOR_WEIGHT,
)
from recommendations.baseline import (
    PROFILE_WEIGHT,
)
from recommendations.baseline import (
    score_unplayed_games as score_baseline_games,
)
from recommendations.clustering import (
    CLUSTER_WEIGHT,
)
from recommendations.clustering import (
    NEIGHBOR_WEIGHT as CLUSTER_NEIGHBOR_WEIGHT,
)
from recommendations.data import load_recommendation_games
from recommendations.engine import build_recommendations
from recommendations.features import build_content_features
from recommendations.profile import build_preference_profile

TOP_RESULTS = 30
TOLERANCE = 1e-9


def feedback_weighted_similarity(neighbors):
    if not neighbors:
        return 0.0

    total_weight = sum(neighbor.feedback_weight for neighbor in neighbors)

    if total_weight <= 0:
        return 0.0

    return (
        sum(
            neighbor.adjusted_similarity * neighbor.feedback_weight
            for neighbor in neighbors
        )
        / total_weight
    )


def format_rating(game):
    if game is None:
        return "unknown"

    if game.rating is None:
        return "implicit"

    return f"{game.rating} stars"


def main():
    games = load_recommendation_games()

    games_by_id = {game.app_id: game for game in games}

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

    baseline_by_id = {score.app_id: score for score in baseline_scores}

    build = build_recommendations(games)

    print("Production recommendation engine audit")
    print("=" * 100)
    print(f"Method: {build.method}")
    print(f"Cluster count: {build.cluster_count}")
    print(f"Candidates: {len(build.scores)}")
    print("Specific-history model: K=3 feedback-weighted positive neighborhood")
    print()

    problems = 0

    for rank, score in enumerate(
        build.scores[:TOP_RESULTS],
        start=1,
    ):
        game = games_by_id.get(score.app_id)

        baseline = baseline_by_id.get(score.app_id)

        if game is None or baseline is None:
            problems += 1
            continue

        neighbors = baseline.neighbors

        reconstructed_neighborhood = feedback_weighted_similarity(neighbors)

        if (
            abs(reconstructed_neighborhood - baseline.neighborhood_similarity)
            > TOLERANCE
        ):
            problems += 1

        if len(neighbors) > 3:
            problems += 1

        for previous, current in zip(
            neighbors,
            neighbors[1:],
        ):
            if current.adjusted_similarity > previous.adjusted_similarity + TOLERANCE:
                problems += 1

        if build.method == "kmeans":
            reconstructed_score = (
                CLUSTER_WEIGHT * score.cluster_similarity
                + CLUSTER_NEIGHBOR_WEIGHT * baseline.neighborhood_similarity
            )

            if (
                abs(score.neighborhood_similarity - baseline.neighborhood_similarity)
                > TOLERANCE
            ):
                problems += 1
        else:
            reconstructed_score = (
                PROFILE_WEIGHT * baseline.profile_similarity
                + BASELINE_NEIGHBOR_WEIGHT * baseline.neighborhood_similarity
            )

        if abs(score.recommendation_score - reconstructed_score) > TOLERANCE:
            problems += 1

        print(
            f"{rank:>2}. {score.recommendation_score:.4f}  {game.name} ({game.app_id})"
        )

        if build.method == "kmeans":
            print(f"    Cluster similarity: {score.cluster_similarity:.4f}")
        else:
            print(f"    Profile similarity: {baseline.profile_similarity:.4f}")

        print(f"    Neighborhood similarity: {baseline.neighborhood_similarity:.4f}")

        print("    Supporting played games:")

        if not neighbors:
            print("        <none>")

        for index, neighbor in enumerate(
            neighbors,
            start=1,
        ):
            reference = games_by_id.get(neighbor.app_id)

            reference_name = (
                reference.name if reference is not None else f"<{neighbor.app_id}>"
            )

            playtime_hours = (
                reference.playtime_minutes / 60 if reference is not None else 0.0
            )

            print(f"        {index}. {reference_name}")

            print(
                "           "
                f"raw="
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
                f"{format_rating(reference)}"
                " | "
                f"weight="
                f"{neighbor.feedback_weight:.3f}"
                " | "
                f"playtime="
                f"{playtime_hours:.1f}h"
            )

        print(f"    Reconstructed neighborhood: {reconstructed_neighborhood:.4f}")

        print(f"    Reconstructed recommendation: {reconstructed_score:.4f}")

        print(
            "    Score delta: "
            f"{abs(score.recommendation_score - reconstructed_score):.12f}"
        )

        print("-" * 100)

    print()

    if problems:
        print(f"Audit problems detected: {problems}")
    else:
        print("Audit problems detected: 0")
        print("Production engine matches the K=3 feedback-weighted neighborhood model.")


if __name__ == "__main__":
    main()
