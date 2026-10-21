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
    DEFAULT_CLUSTER_COUNT,
    train_taste_clusters,
)
from recommendations.clustering import (
    score_unplayed_games as score_cluster_games,
)
from recommendations.data import load_recommendation_games
from recommendations.features import build_content_features
from recommendations.feedback import final_feedback
from recommendations.profile import build_preference_profile

FOLD_COUNT = 5
RANDOM_SEED = 42

K_VALUES = (
    10,
    25,
    50,
    100,
)


def feedback_weight(game):
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


def build_holdout_folds(
    games,
    content_vectors,
):
    eligible_ids = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        if not content_vectors.get(game.app_id):
            continue

        weight = feedback_weight(game)

        if weight < MIN_POSITIVE_REFERENCE_WEIGHT:
            continue

        eligible_ids.append(game.app_id)

    randomizer = random.Random(RANDOM_SEED)

    randomizer.shuffle(eligible_ids)

    folds = [[] for _ in range(FOLD_COUNT)]

    for index, app_id in enumerate(eligible_ids):
        folds[index % FOLD_COUNT].append(app_id)

    return folds


def mask_holdout_games(
    games,
    holdout_ids,
):
    masked_games = []

    for game in games:
        if game.app_id not in holdout_ids:
            masked_games.append(game)
            continue

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


def create_metrics():
    return {
        "ranks": [],
        "percentiles": [],
        "hits": {k: 0 for k in K_VALUES},
        "ndcg": {k: [] for k in K_VALUES},
    }


def record_metrics(
    metrics,
    ranked_scores,
    holdout_ids,
):
    rank_by_id = {
        score.app_id: rank
        for rank, score in enumerate(
            ranked_scores,
            start=1,
        )
    }

    candidate_count = len(ranked_scores)

    for app_id in holdout_ids:
        if app_id not in rank_by_id:
            raise RuntimeError(
                f"Held-out App ID {app_id} was not present in the candidate ranking."
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
                holdout_ids,
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
    total_holdouts,
):
    median_rank = statistics.median(metrics["ranks"])

    median_percentile = statistics.median(metrics["percentiles"])

    print()
    print(name)

    print(f"  Median held-out rank: {median_rank:.1f}")

    print(f"  Median percentile: {median_percentile:.3f}")

    for k in K_VALUES:
        recall = metrics["hits"][k] / total_holdouts

        average_ndcg = statistics.mean(metrics["ndcg"][k])

        print(f"  @{k:<3} Recall: {recall:.3f} | NDCG: {average_ndcg:.3f}")


def main():
    games = load_recommendation_games()

    content_vectors = build_content_features(games)

    folds = build_holdout_folds(
        games,
        content_vectors,
    )

    baseline_metrics = create_metrics()
    cluster_metrics = create_metrics()

    total_holdouts = sum(len(fold) for fold in folds)

    print(f"Evaluation folds: {FOLD_COUNT}")

    print(f"Eligible positive holdouts: {total_holdouts}")

    print(f"K-Means clusters: {DEFAULT_CLUSTER_COUNT}")

    print()

    for fold_number, fold in enumerate(
        folds,
        start=1,
    ):
        holdout_ids = set(fold)

        masked_games = mask_holdout_games(
            games,
            holdout_ids,
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

        cluster_model = train_taste_clusters(
            masked_games,
            content_vectors,
            cluster_count=DEFAULT_CLUSTER_COUNT,
        )

        cluster_scores = score_cluster_games(
            masked_games,
            content_vectors,
            cluster_model,
            baseline_scores,
        )

        baseline_ranked = rank_scores(baseline_scores)

        cluster_ranked = rank_scores(cluster_scores)

        if len(baseline_ranked) != len(cluster_ranked):
            raise RuntimeError(
                "Baseline and K-Means produced different candidate counts."
            )

        print(
            f"Fold {fold_number}: "
            f"{len(holdout_ids)} held out, "
            f"{len(baseline_ranked)} candidates"
        )

        record_metrics(
            baseline_metrics,
            baseline_ranked,
            holdout_ids,
        )

        record_metrics(
            cluster_metrics,
            cluster_ranked,
            holdout_ids,
        )

    print()
    print("Evaluation results")

    print("Higher percentile / NDCG / recall is better.")

    print("Lower median rank is better.")

    print_metrics(
        "Baseline 50/50",
        baseline_metrics,
        total_holdouts,
    )

    print_metrics(
        f"K-Means K={DEFAULT_CLUSTER_COUNT}",
        cluster_metrics,
        total_holdouts,
    )


if __name__ == "__main__":
    main()
