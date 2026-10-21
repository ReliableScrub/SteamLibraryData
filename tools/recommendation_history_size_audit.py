import math
import random
import statistics
from dataclasses import replace

from recommendations.baseline import (
    MIN_POSITIVE_REFERENCE_WEIGHT,
)
from recommendations.baseline import (
    score_unplayed_games as score_baseline_games,
)
from recommendations.clustering import (
    positive_feedback_weight,
    train_taste_clusters,
)
from recommendations.clustering import (
    score_unplayed_games as score_cluster_games,
)
from recommendations.data import load_recommendation_games
from recommendations.features import build_content_features
from recommendations.profile import build_preference_profile

RANDOM_SEED = 42
TRIAL_COUNT = 10

HISTORY_SIZES = (
    5,
    8,
    10,
    15,
    20,
    30,
    50,
    75,
    100,
    200,
    400,
)

CLUSTER_COUNTS = (
    2,
    3,
    4,
    5,
)

K_VALUES = (
    10,
    25,
    50,
    100,
)


def qualified_positive_ids(
    games,
    content_vectors,
):
    app_ids = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        if not content_vectors.get(game.app_id):
            continue

        weight = positive_feedback_weight(game)

        if weight < MIN_POSITIVE_REFERENCE_WEIGHT:
            continue

        app_ids.append(game.app_id)

    return app_ids


def mask_to_history(
    games,
    visible_history_ids,
):
    masked_games = []

    for game in games:
        # Only these played games remain visible to the recommender.
        if game.playtime_minutes > 0 and game.app_id in visible_history_ids:
            masked_games.append(game)
            continue

        # Already-unplayed games remain unchanged.
        if game.playtime_minutes <= 0:
            masked_games.append(game)
            continue

        # Every other played game is temporarily treated as unplayed.
        # This simulates a user with less recommendation history.
        masked_games.append(
            replace(
                game,
                playtime_minutes=0,
                playtime_2weeks_minutes=0,
                last_played_timestamp=0,
                manual_status=None,
                rating=None,
                achievement_total=None,
                achievements_unlocked=None,
                achievements_checked=False,
            )
        )

    return masked_games


def create_metrics():
    return {
        "ranks": [],
        "percentiles": [],
        "hits": {k: 0 for k in K_VALUES},
        "relevant_count": 0,
        "ndcg": {k: [] for k in K_VALUES},
    }


def ndcg_at_k(
    ranked_scores,
    relevant_ids,
    k,
):
    dcg = 0.0

    for rank, score in enumerate(
        ranked_scores[:k],
        start=1,
    ):
        if score.app_id not in relevant_ids:
            continue

        dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(
        len(relevant_ids),
        k,
    )

    if ideal_hits == 0:
        return 0.0

    ideal_dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(
            1,
            ideal_hits + 1,
        )
    )

    return dcg / ideal_dcg


def record_metrics(
    metrics,
    ranked_scores,
    relevant_ids,
):
    rank_by_id = {
        score.app_id: rank
        for rank, score in enumerate(
            ranked_scores,
            start=1,
        )
    }

    candidate_count = len(ranked_scores)

    metrics["relevant_count"] += len(relevant_ids)

    for app_id in relevant_ids:
        if app_id not in rank_by_id:
            raise RuntimeError(
                f"Hidden positive App ID {app_id} was not present in the ranking."
            )

        rank = rank_by_id[app_id]

        metrics["ranks"].append(rank)

        percentile = 1.0 - (
            (rank - 1)
            / max(
                candidate_count - 1,
                1,
            )
        )

        metrics["percentiles"].append(percentile)

        for k in K_VALUES:
            if rank <= k:
                metrics["hits"][k] += 1

    for k in K_VALUES:
        metrics["ndcg"][k].append(
            ndcg_at_k(
                ranked_scores,
                relevant_ids,
                k,
            )
        )


def rank_scores(scores):
    return sorted(
        scores,
        key=lambda score: (
            -score.recommendation_score,
            score.app_id,
        ),
    )


def print_metrics(
    name,
    metrics,
):
    median_rank = statistics.median(metrics["ranks"])

    median_percentile = statistics.median(metrics["percentiles"])

    print(
        f"  {name:<16}"
        f"rank {median_rank:7.1f} | "
        f"pct {median_percentile:.3f} | "
        f"NDCG@10 {statistics.mean(metrics['ndcg'][10]):.3f} | "
        f"NDCG@25 {statistics.mean(metrics['ndcg'][25]):.3f} | "
        f"R@100 "
        f"{metrics['hits'][100] / metrics['relevant_count']:.3f}"
    )


def main():
    games = load_recommendation_games()

    content_vectors = build_content_features(games)

    positive_ids = qualified_positive_ids(
        games,
        content_vectors,
    )

    print(f"Qualified positive games available: {len(positive_ids)}")

    print(f"Trials per history size: {TRIAL_COUNT}")

    print("History sizes: " + ", ".join(str(size) for size in HISTORY_SIZES))

    print("Cluster counts: " + ", ".join(str(count) for count in CLUSTER_COUNTS))

    print()

    usable_history_sizes = [size for size in HISTORY_SIZES if size < len(positive_ids)]

    metrics_by_history = {}

    for history_size in usable_history_sizes:
        metrics_by_history[history_size] = {
            "Baseline": create_metrics(),
        }

        for cluster_count in CLUSTER_COUNTS:
            metrics_by_history[history_size][f"K={cluster_count}"] = create_metrics()

    for trial_index in range(TRIAL_COUNT):
        randomizer = random.Random(RANDOM_SEED + trial_index)

        shuffled_positive_ids = list(positive_ids)

        randomizer.shuffle(shuffled_positive_ids)

        print(f"Trial {trial_index + 1}/{TRIAL_COUNT}")

        for history_size in usable_history_sizes:
            visible_history_ids = set(shuffled_positive_ids[:history_size])

            hidden_positive_ids = set(shuffled_positive_ids[history_size:])

            masked_games = mask_to_history(
                games,
                visible_history_ids,
            )

            profile = build_preference_profile(
                masked_games,
                content_vectors,
            )

            baseline_scores = score_baseline_games(
                masked_games,
                content_vectors,
                profile,
            )

            baseline_ranked = rank_scores(baseline_scores)

            record_metrics(
                metrics_by_history[history_size]["Baseline"],
                baseline_ranked,
                hidden_positive_ids,
            )

            for cluster_count in CLUSTER_COUNTS:
                if cluster_count > history_size:
                    continue

                cluster_model = train_taste_clusters(
                    masked_games,
                    content_vectors,
                    cluster_count=cluster_count,
                )

                if cluster_model is None:
                    continue

                cluster_scores = score_cluster_games(
                    masked_games,
                    content_vectors,
                    cluster_model,
                    baseline_scores,
                )

                cluster_ranked = rank_scores(cluster_scores)

                if len(cluster_ranked) != len(baseline_ranked):
                    raise RuntimeError(
                        f"History={history_size}, "
                        f"K={cluster_count} produced "
                        "a different candidate count."
                    )

                record_metrics(
                    metrics_by_history[history_size][f"K={cluster_count}"],
                    cluster_ranked,
                    hidden_positive_ids,
                )

            print(
                f"  history={history_size:<3} | "
                f"hidden positives="
                f"{len(hidden_positive_ids):<3} | "
                f"candidates="
                f"{len(baseline_ranked)}"
            )

        print()

    print("=" * 90)

    print("History-size evaluation")

    print("Compare methods within each history size.")

    print("Higher percentile/NDCG/recall is better; lower rank is better.")

    print("=" * 90)

    for history_size in usable_history_sizes:
        print()
        print(f"Visible positive history: {history_size} games")

        history_metrics = metrics_by_history[history_size]

        print_metrics(
            "Baseline",
            history_metrics["Baseline"],
        )

        for cluster_count in CLUSTER_COUNTS:
            name = f"K={cluster_count}"

            metrics = history_metrics[name]

            if not metrics["ranks"]:
                continue

            print_metrics(
                name,
                metrics,
            )


if __name__ == "__main__":
    main()
