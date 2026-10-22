import math
import random
from dataclasses import replace
from statistics import median

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
from recommendations.feedback import (
    final_feedback,
)
from recommendations.neighbors import (
    MIN_POSITIVE_NEIGHBOR_WEIGHT,
    score_unplayed_games,
)

FOLD_COUNT = 5
CLUSTER_COUNT = 5
RANDOM_SEED = 42

CLUSTER_WEIGHT = 0.50
NEIGHBOR_WEIGHT = 0.50

CUTOFFS = (
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


def eligible_positive_ids(
    games,
    content_vectors,
):
    app_ids = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

        if not content_vectors.get(game.app_id):
            continue

        weight = feedback_weight(game)

        if weight < MIN_POSITIVE_NEIGHBOR_WEIGHT:
            continue

        app_ids.append(game.app_id)

    return app_ids


def make_folds(app_ids):
    app_ids = sorted(app_ids)

    random_generator = random.Random(RANDOM_SEED)

    random_generator.shuffle(app_ids)

    return [app_ids[fold_index::FOLD_COUNT] for fold_index in range(FOLD_COUNT)]


def hide_feedback(game):
    """
    Convert a played positive game into an unplayed evaluation candidate
    while preserving its content metadata.
    """
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
    )


def build_fold_games(
    games,
    held_out_ids,
):
    held_out_ids = set(held_out_ids)

    return [
        (hide_feedback(game) if game.app_id in held_out_ids else game) for game in games
    ]


def best_cluster_similarity(
    vector,
    cluster_model,
):
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


def rank_variant(
    games,
    content_vectors,
    cluster_model,
    neighborhood_scores,
    attribute,
):
    rows = []

    for score in neighborhood_scores:
        vector = content_vectors.get(score.app_id)

        if not vector:
            continue

        cluster_similarity = best_cluster_similarity(
            vector,
            cluster_model,
        )

        neighborhood_similarity = getattr(
            score,
            attribute,
        )

        recommendation_score = combine_score(
            cluster_similarity,
            neighborhood_similarity,
        )

        rows.append(
            (
                score.app_id,
                recommendation_score,
            )
        )

    rows.sort(
        key=lambda row: (
            -row[1],
            row[0],
        )
    )

    return rows


def ranks_for_holdouts(
    ranked_rows,
    held_out_ids,
):
    rank_by_id = {
        app_id: rank
        for rank, (
            app_id,
            _,
        ) in enumerate(
            ranked_rows,
            start=1,
        )
    }

    return [rank_by_id[app_id] for app_id in held_out_ids if app_id in rank_by_id]


def percentile_from_rank(
    rank,
    candidate_count,
):
    if candidate_count <= 1:
        return 1.0

    return 1.0 - (rank - 1) / (candidate_count - 1)


def recall_at(
    ranked_rows,
    held_out_ids,
    cutoff,
):
    held_out_ids = set(held_out_ids)

    if not held_out_ids:
        return 0.0

    top_ids = {app_id for app_id, _ in ranked_rows[:cutoff]}

    return len(top_ids & held_out_ids) / len(held_out_ids)


def dcg_at(
    ranked_rows,
    held_out_ids,
    cutoff,
):
    held_out_ids = set(held_out_ids)

    total = 0.0

    for rank, (
        app_id,
        _,
    ) in enumerate(
        ranked_rows[:cutoff],
        start=1,
    ):
        if app_id not in held_out_ids:
            continue

        total += 1.0 / math.log2(rank + 1)

    return total


def ndcg_at(
    ranked_rows,
    held_out_ids,
    cutoff,
):
    relevant_count = min(
        len(held_out_ids),
        cutoff,
    )

    if relevant_count <= 0:
        return 0.0

    ideal_dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank in range(
            1,
            relevant_count + 1,
        )
    )

    if ideal_dcg <= 0:
        return 0.0

    return (
        dcg_at(
            ranked_rows,
            held_out_ids,
            cutoff,
        )
        / ideal_dcg
    )


def empty_result():
    return {
        "ranks": [],
        "percentiles": [],
        "recall": {cutoff: [] for cutoff in CUTOFFS},
        "ndcg": {cutoff: [] for cutoff in CUTOFFS},
    }


def add_fold_result(
    result,
    ranked_rows,
    held_out_ids,
):
    candidate_count = len(ranked_rows)

    ranks = ranks_for_holdouts(
        ranked_rows,
        held_out_ids,
    )

    result["ranks"].extend(ranks)

    result["percentiles"].extend(
        percentile_from_rank(
            rank,
            candidate_count,
        )
        for rank in ranks
    )

    for cutoff in CUTOFFS:
        result["recall"][cutoff].append(
            recall_at(
                ranked_rows,
                held_out_ids,
                cutoff,
            )
        )

        result["ndcg"][cutoff].append(
            ndcg_at(
                ranked_rows,
                held_out_ids,
                cutoff,
            )
        )


def mean(values):
    if not values:
        return 0.0

    return sum(values) / len(values)


def print_result(
    label,
    result,
):
    print(label)

    if not result["ranks"]:
        print("  No evaluated holdouts.")
        print()
        return

    print(f"  Median held-out rank: {median(result['ranks']):.1f}")

    print(f"  Median percentile: {median(result['percentiles']):.3f}")

    for cutoff in CUTOFFS:
        print(
            f"  @{cutoff:<3} "
            f"Recall: "
            f"{mean(result['recall'][cutoff]):.3f}"
            " | "
            f"NDCG: "
            f"{mean(result['ndcg'][cutoff]):.3f}"
        )

    print()


def main():
    games = load_recommendation_games()

    original_vectors = build_content_features(games)

    positive_ids = eligible_positive_ids(
        games,
        original_vectors,
    )

    folds = make_folds(positive_ids)

    print(f"Evaluation folds: {FOLD_COUNT}")

    print(f"Eligible positive holdouts: {len(positive_ids)}")

    print(f"K-Means clusters: {CLUSTER_COUNT}")

    print()

    results = {
        "k1": empty_result(),
        "k3_mean": empty_result(),
        "k3_weighted": empty_result(),
        "k5_mean": empty_result(),
        "k5_weighted": empty_result(),
    }

    for fold_number, held_out_ids in enumerate(
        folds,
        start=1,
    ):
        fold_games = build_fold_games(
            games,
            held_out_ids,
        )

        content_vectors = build_content_features(fold_games)

        cluster_model = train_taste_clusters(
            fold_games,
            content_vectors,
            cluster_count=CLUSTER_COUNT,
        )

        if cluster_model is None:
            raise RuntimeError("K-Means training unexpectedly returned no model.")

        k1_scores = score_unplayed_games(
            fold_games,
            content_vectors,
            neighbor_count=1,
        )

        k3_scores = score_unplayed_games(
            fold_games,
            content_vectors,
            neighbor_count=3,
        )

        k5_scores = score_unplayed_games(
            fold_games,
            content_vectors,
            neighbor_count=5,
        )

        ranked_variants = {
            "k1": rank_variant(
                fold_games,
                content_vectors,
                cluster_model,
                k1_scores,
                "similarity_mean",
            ),
            "k3_mean": rank_variant(
                fold_games,
                content_vectors,
                cluster_model,
                k3_scores,
                "similarity_mean",
            ),
            "k3_weighted": rank_variant(
                fold_games,
                content_vectors,
                cluster_model,
                k3_scores,
                "feedback_weighted_mean",
            ),
            "k5_mean": rank_variant(
                fold_games,
                content_vectors,
                cluster_model,
                k5_scores,
                "similarity_mean",
            ),
            "k5_weighted": rank_variant(
                fold_games,
                content_vectors,
                cluster_model,
                k5_scores,
                "feedback_weighted_mean",
            ),
        }

        candidate_count = len(ranked_variants["k1"])

        print(
            f"Fold {fold_number}: "
            f"{len(held_out_ids)} held out, "
            f"{candidate_count} candidates"
        )

        for key, ranked_rows in ranked_variants.items():
            add_fold_result(
                results[key],
                ranked_rows,
                held_out_ids,
            )

    print()
    print("Neighborhood evaluation results")

    print("Higher percentile / NDCG / recall is better.")

    print("Lower median rank is better.")

    print()

    print_result(
        "K=1 nearest positive",
        results["k1"],
    )

    print_result(
        "K=3 similarity mean",
        results["k3_mean"],
    )

    print_result(
        "K=3 feedback-weighted",
        results["k3_weighted"],
    )

    print_result(
        "K=5 similarity mean",
        results["k5_mean"],
    )

    print_result(
        "K=5 feedback-weighted",
        results["k5_weighted"],
    )


if __name__ == "__main__":
    main()
