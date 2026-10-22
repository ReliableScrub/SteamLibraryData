from math import isfinite

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
from recommendations.engine import (
    METHOD_BASELINE,
    METHOD_KMEANS,
    rank_scores,
)
from recommendations.explanations import (
    DEFAULT_FEATURE_LIMIT,
    SUPPRESSED_FEATURES,
    build_recommendation_explanations,
)
from recommendations.features import build_content_features
from recommendations.profile import build_preference_profile

AUDIT_LIMIT = 30


def format_features(features):
    return " • ".join(feature.name for feature in features) or "No distinctive features"


def format_feature_label(feature):
    if not feature.sources:
        return feature.name

    if len(feature.sources) == 1:
        source_label = feature.sources[0]
    else:
        source_label = "+".join(feature.sources)

    return f"{feature.name} [{source_label}]"


def build_audit_data():
    games = load_recommendation_games()
    content_vectors = build_content_features(games)
    profile = build_preference_profile(games, content_vectors)
    baseline_scores = score_baseline_games(games, content_vectors, profile)
    cluster_model = train_taste_clusters(games, content_vectors)

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

    explanations = build_recommendation_explanations(
        games=games,
        content_vectors=content_vectors,
        profile=profile,
        baseline_scores=baseline_scores,
        recommendation_scores=scores,
        method=method,
        cluster_model=cluster_model,
        feature_limit=DEFAULT_FEATURE_LIMIT,
    )

    return (
        games,
        content_vectors,
        scores,
        explanations,
        method,
        cluster_count,
    )


def audit_explanations(games, content_vectors, scores, explanations):
    problems = []
    games_by_id = {game.app_id: game for game in games}

    for score in scores[:AUDIT_LIMIT]:
        app_id = score.app_id
        explanation = explanations.get(app_id)

        if explanation is None:
            problems.append(f"{app_id}: missing explanation")
            continue

        if not explanation.taste_features:
            problems.append(
                f"{app_id}: no taste features survived explanation filtering"
            )

        for feature in explanation.taste_features:
            if feature.contribution <= 0.0 or not isfinite(feature.contribution):
                problems.append(
                    f"{app_id}: invalid taste contribution for {feature.name}"
                )

            if feature.name.casefold() in SUPPRESSED_FEATURES:
                problems.append(
                    f"{app_id}: suppressed taste feature leaked: {feature.name}"
                )

        support_ids = [support.app_id for support in explanation.supporting_games]

        if len(support_ids) > 3:
            problems.append(f"{app_id}: more than three supporting games")

        if len(support_ids) != len(set(support_ids)):
            problems.append(f"{app_id}: duplicate supporting game")

        if app_id in support_ids:
            problems.append(
                f"{app_id}: candidate references itself as supporting history"
            )

        for support in explanation.supporting_games:
            reference_game = games_by_id.get(support.app_id)

            if reference_game is None:
                problems.append(
                    f"{app_id}: supporting App ID {support.app_id} is not in the library"
                )
                continue

            if (getattr(reference_game, "playtime_minutes", 0) or 0) <= 0:
                problems.append(
                    f"{app_id}: unplayed game {support.app_id} used as supporting history"
                )

            for value_name, value in (
                ("raw similarity", support.raw_similarity),
                ("adjusted similarity", support.adjusted_similarity),
                ("feedback weight", support.feedback_weight),
            ):
                if not isfinite(value):
                    problems.append(
                        f"{app_id}: non-finite {value_name} for {support.app_id}"
                    )

            for feature in support.shared_features:
                if feature.contribution <= 0.0 or not isfinite(feature.contribution):
                    problems.append(
                        f"{app_id}: invalid shared-feature contribution from {support.name}"
                    )

                if feature.name.casefold() in SUPPRESSED_FEATURES:
                    problems.append(
                        f"{app_id}: suppressed shared feature leaked: {feature.name}"
                    )

    return problems


def main():
    (
        games,
        content_vectors,
        scores,
        explanations,
        method,
        cluster_count,
    ) = build_audit_data()

    games_by_id = {game.app_id: game for game in games}
    problems = audit_explanations(games, content_vectors, scores, explanations)

    print("Production recommendation explanation audit")
    print("=" * 100)
    print(f"Method: {method}")
    print(f"Cluster count: {cluster_count if cluster_count is not None else 'n/a'}")
    print(f"Candidates: {len(scores)}")
    print(f"Supporting-history model: up to 3 feedback-weighted positive neighbors")
    print(f"Taste feature limit: {DEFAULT_FEATURE_LIMIT}")
    print()

    for rank, score in enumerate(scores[:AUDIT_LIMIT], start=1):
        game = games_by_id.get(score.app_id)
        name = getattr(game, "name", str(score.app_id))
        explanation = explanations.get(score.app_id)

        print(f"{rank:2}. {score.recommendation_score:.4f}  {name} ({score.app_id})")

        if explanation is None:
            print("    EXPLANATION MISSING")
            print("-" * 100)
            continue

        print(f"    Why it fits: {format_features(explanation.taste_features)}")

        if explanation.taste_features:
            print("    Taste contributions:")
            for feature in explanation.taste_features:
                print(
                    f"        {feature.contribution:.4f}  "
                    f"{format_feature_label(feature)}"
                )

        print("    Supporting played games:")

        if not explanation.supporting_games:
            print("        No positive played-game references available")

        for support_rank, support in enumerate(explanation.supporting_games, start=1):
            print(f"        {support_rank}. {support.name} ({support.app_id})")
            print(
                f"           raw={support.raw_similarity:.4f} | "
                f"adjusted={support.adjusted_similarity:.4f} | "
                f"shared={support.shared_feature_count}"
            )
            print(
                f"           evidence={support.evidence} | "
                f"weight={support.feedback_weight:.3f} | "
                f"playtime={support.playtime_minutes / 60.0:.1f}h"
            )

            if support.shared_features:
                print(
                    "           shared traits: "
                    f"{format_features(support.shared_features)}"
                )

        print("-" * 100)

    print()
    print(f"Potential explanation problems: {len(problems)}")

    for problem in problems[:50]:
        print(f"  - {problem}")

    if len(problems) > 50:
        print(f"  ... and {len(problems) - 50} additional problems")

    print("Audit complete.")


if __name__ == "__main__":
    main()
