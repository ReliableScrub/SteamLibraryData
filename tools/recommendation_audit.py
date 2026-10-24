import argparse
from math import isfinite

from recommendations.data import load_recommendation_games
from recommendations.diversity import rerank_mmr
from recommendations.engine import build_recommendations
from recommendations.features import build_content_features


def audit_recommendations(games, result):
    problems = []
    warnings = []
    games_by_id = {game.app_id: game for game in games}

    if not result.scores:
        warnings.append("No recommendation candidates were produced.")
        return problems, warnings

    score_values = [score.recommendation_score for score in result.scores]

    if score_values != sorted(score_values, reverse=True):
        problems.append("Recommendation scores are not sorted descending.")

    seen_ids = set()

    for score in result.scores:
        if score.app_id in seen_ids:
            problems.append(f"Duplicate recommendation App ID {score.app_id}.")
            continue

        seen_ids.add(score.app_id)

        game = games_by_id.get(score.app_id)

        if game is None:
            problems.append(
                f"Recommendation App ID {score.app_id} is not in the dataset."
            )
            continue

        if game.playtime_minutes > 0:
            problems.append(f"Played game {game.name} ({game.app_id}) was recommended.")

        if not isfinite(score.recommendation_score):
            problems.append(f"Non-finite score for {game.name} ({game.app_id}).")

        explanation = result.explanations.get(score.app_id)

        if explanation is None:
            problems.append(f"Missing explanation for {game.name} ({game.app_id}).")
            continue

        if len(explanation.supporting_games) > 3:
            problems.append(f"{game.name} has more than three supporting games.")

        support_ids = [support.app_id for support in explanation.supporting_games]

        if len(support_ids) != len(set(support_ids)):
            problems.append(f"{game.name} has duplicate supporting games.")

        if score.app_id in support_ids:
            problems.append(f"{game.name} references itself as support.")

        for support in explanation.supporting_games:
            reference = games_by_id.get(support.app_id)

            if reference is None:
                problems.append(
                    f"{game.name} references missing App ID {support.app_id}."
                )
                continue

            if reference.playtime_minutes <= 0:
                problems.append(
                    f"{game.name} uses unplayed {reference.name} as support."
                )

            for metric in (
                support.raw_similarity,
                support.adjusted_similarity,
                support.feedback_weight,
            ):
                if not isfinite(metric):
                    problems.append(f"{game.name} has non-finite supporting-game data.")

        for feature in explanation.taste_features:
            if not isfinite(feature.contribution):
                problems.append(f"{game.name} has non-finite taste contribution.")

    score_ids = {score.app_id for score in result.scores}
    top_ids = [score.app_id for score in result.top_picks]

    if len(top_ids) != len(set(top_ids)):
        problems.append("Top picks contain duplicates.")

    if not set(top_ids).issubset(score_ids):
        problems.append("Top picks contain games outside the scored candidates.")

    return problems, warnings


def print_top_recommendations(games, result, limit):
    games_by_id = {game.app_id: game for game in games}

    print()
    print("Top recommendations")
    print("-" * 100)

    for rank, score in enumerate(result.scores[:limit], start=1):
        game = games_by_id.get(score.app_id)
        name = game.name if game is not None else f"<{score.app_id}>"
        explanation = result.explanations.get(score.app_id)

        print(f"{rank:>2}. {score.recommendation_score:.4f}  {name}")

        if explanation is None:
            print("    No explanation")
            continue

        feature_names = [feature.name for feature in explanation.taste_features]
        support_names = [support.name for support in explanation.supporting_games]

        print(
            "    Traits: " + (" • ".join(feature_names) if feature_names else "<none>")
        )
        print(
            "    Based on: "
            + (" | ".join(support_names) if support_names else "<none>")
        )


def print_diversity_preview(games, result, relevance_weight, limit):
    vectors = build_content_features(games)
    games_by_id = {game.app_id: game for game in games}

    diversified = rerank_mmr(
        result.scores,
        vectors,
        limit=min(limit, len(result.scores)),
        relevance_weight=relevance_weight,
    )

    print()
    print(f"Diversity preview (MMR relevance weight={relevance_weight:.2f})")
    print("-" * 100)

    for rank, score in enumerate(diversified, start=1):
        game = games_by_id.get(score.app_id)
        name = game.name if game is not None else f"<{score.app_id}>"
        print(f"{rank:>2}. {score.recommendation_score:.4f}  {name}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only production recommendation audit covering ranking, "
            "explanations, supporting history, and top-pick integrity."
        )
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--diversity-weight",
        type=float,
        default=None,
        help="Also preview an MMR rerank at this relevance weight.",
    )
    args = parser.parse_args()

    games = load_recommendation_games()
    result = build_recommendations(games)

    problems, warnings = audit_recommendations(games, result)

    print("Steam Backlog DB - Recommendation Audit")
    print("=" * 43)
    print(f"Games loaded: {len(games)}")
    print(f"Method: {result.method}")
    print(
        "Cluster count: "
        + (str(result.cluster_count) if result.cluster_count is not None else "n/a")
    )
    print(f"Candidates: {len(result.scores)}")
    print(f"Top picks: {len(result.top_picks)}")
    print(f"Explanations: {len(result.explanations)}")

    print_top_recommendations(games, result, args.limit)

    if args.diversity_weight is not None:
        print_diversity_preview(
            games,
            result,
            args.diversity_weight,
            min(args.limit, 20),
        )

    print()
    print("Result")
    print("-" * 100)

    if problems:
        print("FAIL")
    elif warnings:
        print("PASS WITH WARNINGS")
    else:
        print("PASS")

    for message in problems:
        print(f"  ERROR: {message}")

    for message in warnings:
        print(f"  WARNING: {message}")

    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
