import argparse
import math
import random
import statistics
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from recommendations.baseline import (
    score_unplayed_games as score_baseline_games,
)
from recommendations.clustering import (
    score_unplayed_games as score_cluster_games,
)
from recommendations.clustering import (
    train_taste_clusters,
)
from recommendations.data import load_recommendation_games
from recommendations.engine import build_recommendations
from recommendations.features import build_content_features
from recommendations.neighbors import (
    collect_positive_references,
)
from recommendations.neighbors import (
    score_unplayed_games as score_neighbor_games,
)
from recommendations.profile import build_preference_profile

RANDOM_SEED = 42
CUTOFFS = (10, 25, 50, 100)


def positive_ids(games, vectors):
    return [
        reference.app_id for reference in collect_positive_references(games, vectors)
    ]


def hide_feedback(game):
    return replace(
        game,
        playtime_minutes=0,
        playtime_2weeks_minutes=0,
        last_played_timestamp=0,
        manual_status=None,
        rating=None,
        hltb_main=None,
        hltb_main_extra=None,
        hltb_completionist=None,
        hltb_all_styles=None,
        achievement_total=None,
        achievements_unlocked=None,
        achievements_checked=False,
    )


def mask_games(games, visible_positive_ids):
    visible_positive_ids = set(visible_positive_ids)

    return [
        game
        if game.playtime_minutes <= 0 or game.app_id in visible_positive_ids
        else hide_feedback(game)
        for game in games
    ]


def holdout_games(games, held_out_ids):
    held_out_ids = set(held_out_ids)

    return [
        hide_feedback(game) if game.app_id in held_out_ids else game for game in games
    ]


def ndcg_at_k(ranked_ids, relevant_ids, cutoff):
    relevant_ids = set(relevant_ids)
    dcg = 0.0

    for rank, app_id in enumerate(ranked_ids[:cutoff], start=1):
        if app_id in relevant_ids:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(len(relevant_ids), cutoff)

    if ideal_hits == 0:
        return 0.0

    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

    return dcg / ideal


def evaluate_ranking(ranked_ids, relevant_ids):
    relevant_ids = set(relevant_ids)
    rank_by_id = {app_id: rank for rank, app_id in enumerate(ranked_ids, start=1)}

    ranks = [rank_by_id[app_id] for app_id in relevant_ids if app_id in rank_by_id]

    candidate_count = len(ranked_ids)

    percentiles = [1.0 - (rank - 1) / max(candidate_count - 1, 1) for rank in ranks]

    return {
        "ranks": ranks,
        "percentiles": percentiles,
        "recall": {
            cutoff: (
                sum(
                    1
                    for app_id in relevant_ids
                    if rank_by_id.get(app_id, cutoff + 1) <= cutoff
                )
                / max(len(relevant_ids), 1)
            )
            for cutoff in CUTOFFS
        },
        "ndcg": {
            cutoff: ndcg_at_k(
                ranked_ids,
                relevant_ids,
                cutoff,
            )
            for cutoff in CUTOFFS
        },
    }


def merge_metrics(target, metrics):
    target["ranks"].extend(metrics["ranks"])
    target["percentiles"].extend(metrics["percentiles"])

    for cutoff in CUTOFFS:
        target["recall"][cutoff].append(metrics["recall"][cutoff])
        target["ndcg"][cutoff].append(metrics["ndcg"][cutoff])


def empty_metrics():
    return {
        "ranks": [],
        "percentiles": [],
        "recall": {cutoff: [] for cutoff in CUTOFFS},
        "ndcg": {cutoff: [] for cutoff in CUTOFFS},
    }


def print_metrics(label, metrics):
    print()
    print(label)

    if not metrics["ranks"]:
        print("  No evaluated holdouts.")
        return

    print(f"  Median rank:       {statistics.median(metrics['ranks']):.1f}")
    print(f"  Median percentile: {statistics.median(metrics['percentiles']):.3f}")

    for cutoff in CUTOFFS:
        recall = statistics.mean(metrics["recall"][cutoff])
        ndcg = statistics.mean(metrics["ndcg"][cutoff])
        print(f"  @{cutoff:<3} recall={recall:.3f} | NDCG={ndcg:.3f}")


def build_folds(app_ids, fold_count):
    ids = list(app_ids)
    randomizer = random.Random(RANDOM_SEED)
    randomizer.shuffle(ids)

    folds = [[] for _ in range(fold_count)]

    for index, app_id in enumerate(ids):
        folds[index % fold_count].append(app_id)

    return folds


def rank_scores(scores):
    return [
        score.app_id
        for score in sorted(
            scores,
            key=lambda score: (
                -score.recommendation_score,
                score.app_id,
            ),
        )
    ]


def evaluate_history(games, vectors, history_sizes, trials):
    positives = positive_ids(games, vectors)

    print(f"Qualified positive games: {len(positives)}")
    print(f"Trials per history size: {trials}")

    for history_size in history_sizes:
        if history_size >= len(positives):
            continue

        metrics = empty_metrics()

        for trial in range(trials):
            randomizer = random.Random(RANDOM_SEED + trial)
            shuffled = list(positives)
            randomizer.shuffle(shuffled)

            visible = shuffled[:history_size]
            hidden = shuffled[history_size:]

            masked = mask_games(games, visible)
            result = build_recommendations(masked)

            merge_metrics(
                metrics,
                evaluate_ranking(
                    [score.app_id for score in result.scores],
                    hidden,
                ),
            )

        print_metrics(
            f"Production engine with {history_size} visible positives",
            metrics,
        )


def evaluate_neighbors(games, vectors, fold_count):
    positives = positive_ids(games, vectors)
    folds = build_folds(positives, fold_count)
    results = {
        1: empty_metrics(),
        3: empty_metrics(),
        5: empty_metrics(),
    }

    for fold in folds:
        masked = holdout_games(games, fold)
        masked_vectors = build_content_features(masked)

        for neighbor_count, metrics in results.items():
            scores = score_neighbor_games(
                masked,
                masked_vectors,
                neighbor_count=neighbor_count,
            )

            ranked_ids = [
                score.app_id
                for score in sorted(
                    scores,
                    key=lambda score: (
                        -score.feedback_weighted_mean,
                        score.app_id,
                    ),
                )
            ]

            merge_metrics(
                metrics,
                evaluate_ranking(ranked_ids, fold),
            )

    for neighbor_count, metrics in results.items():
        print_metrics(
            f"Neighborhood K={neighbor_count}",
            metrics,
        )


def evaluate_clusters(games, vectors, cluster_counts, fold_count):
    positives = positive_ids(games, vectors)
    folds = build_folds(positives, fold_count)

    results = {
        "baseline": empty_metrics(),
        **{
            f"kmeans-{cluster_count}": empty_metrics()
            for cluster_count in cluster_counts
        },
    }

    for fold in folds:
        masked = holdout_games(games, fold)
        masked_vectors = build_content_features(masked)
        profile = build_preference_profile(masked, masked_vectors)

        baseline_scores = score_baseline_games(
            masked,
            masked_vectors,
            profile,
        )

        merge_metrics(
            results["baseline"],
            evaluate_ranking(
                rank_scores(baseline_scores),
                fold,
            ),
        )

        for cluster_count in cluster_counts:
            model = train_taste_clusters(
                masked,
                masked_vectors,
                cluster_count=cluster_count,
            )

            if model is None:
                continue

            cluster_scores = score_cluster_games(
                masked,
                masked_vectors,
                model,
                baseline_scores,
            )

            merge_metrics(
                results[f"kmeans-{cluster_count}"],
                evaluate_ranking(
                    rank_scores(cluster_scores),
                    fold,
                ),
            )

    print_metrics("Baseline", results["baseline"])

    for cluster_count in cluster_counts:
        print_metrics(
            f"K-Means clusters={cluster_count}",
            results[f"kmeans-{cluster_count}"],
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Offline recommendation evaluation. "
            "Use a mode instead of maintaining separate experiment scripts."
        )
    )
    subparsers = parser.add_subparsers(
        dest="mode",
        required=True,
    )

    history = subparsers.add_parser("history")
    history.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[5, 10, 15, 20, 30, 50, 100],
    )
    history.add_argument("--trials", type=int, default=5)

    neighbors = subparsers.add_parser("neighbors")
    neighbors.add_argument("--folds", type=int, default=5)

    clusters = subparsers.add_parser("clusters")
    clusters.add_argument(
        "--counts",
        type=int,
        nargs="+",
        default=[2, 3, 4, 5],
    )
    clusters.add_argument("--folds", type=int, default=5)

    args = parser.parse_args()

    games = load_recommendation_games()
    vectors = build_content_features(games)

    print("Steam Backlog DB - Recommendation Evaluation")
    print("=" * 48)
    print(f"Games loaded: {len(games)}")
    print(f"Mode: {args.mode}")

    if args.mode == "history":
        evaluate_history(
            games,
            vectors,
            args.sizes,
            args.trials,
        )
    elif args.mode == "neighbors":
        evaluate_neighbors(
            games,
            vectors,
            args.folds,
        )
    else:
        evaluate_clusters(
            games,
            vectors,
            args.counts,
            args.folds,
        )


if __name__ == "__main__":
    main()
