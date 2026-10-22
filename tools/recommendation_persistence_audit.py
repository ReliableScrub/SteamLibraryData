import json

from recommendations.engine import generate_and_save_recommendations
from recommendations.persistence import (
    FEATURE_VERSION,
    MODEL_VERSION,
    load_recommendation_state,
    load_saved_recommendations,
)

EXPECTED_MODEL_VERSION = 2
EXPECTED_FEATURE_VERSION = 2
MAX_SUPPORTING_GAMES = 3
SCORE_TOLERANCE = 1e-9


def main():
    print("Recommendation persistence audit")
    print("=" * 100)

    print("Generating and saving production recommendation build...")

    build = generate_and_save_recommendations()

    state = load_recommendation_state()
    rows = load_saved_recommendations()

    problems = []

    if state is None:
        problems.append("recommendation_state row was not saved.")

        print()
        print("Persistence problems detected: 1")
        print(" - recommendation_state row was not saved.")
        return

    (
        saved_method,
        saved_model_version,
        saved_feature_version,
        generated_at,
        training_game_count,
        rated_game_count,
        implicit_game_count,
        candidate_game_count,
    ) = state

    print()
    print("Saved state")
    print("-" * 100)
    print(f"Method: {saved_method}")
    print(f"Model version: {saved_model_version}")
    print(f"Feature version: {saved_feature_version}")
    print(f"Generated at: {generated_at}")
    print(f"Training games: {training_game_count}")
    print(f"Rated games: {rated_game_count}")
    print(f"Implicit games: {implicit_game_count}")
    print(f"Candidate games: {candidate_game_count}")

    if saved_method != build.method:
        problems.append("Saved method does not match generated build.")

    if MODEL_VERSION != EXPECTED_MODEL_VERSION:
        problems.append(
            f"Persistence MODEL_VERSION is "
            f"{MODEL_VERSION}, expected "
            f"{EXPECTED_MODEL_VERSION}."
        )

    if FEATURE_VERSION != EXPECTED_FEATURE_VERSION:
        problems.append(
            f"Persistence FEATURE_VERSION is "
            f"{FEATURE_VERSION}, expected "
            f"{EXPECTED_FEATURE_VERSION}."
        )

    if saved_model_version != EXPECTED_MODEL_VERSION:
        problems.append(
            f"Saved model_version is "
            f"{saved_model_version}, expected "
            f"{EXPECTED_MODEL_VERSION}."
        )

    if saved_feature_version != EXPECTED_FEATURE_VERSION:
        problems.append(
            f"Saved feature_version is "
            f"{saved_feature_version}, expected "
            f"{EXPECTED_FEATURE_VERSION}."
        )

    if candidate_game_count != len(build.scores):
        problems.append("Saved candidate_game_count does not match generated build.")

    if len(rows) != len(build.scores):
        problems.append(
            "Saved recommendation row count does not match generated build."
        )

    build_scores = {score.app_id: score for score in build.scores}
    expected_top_pick_ids = {score.app_id for score in build.top_picks}

    saved_top_pick_ids = set()
    explanation_count = 0
    missing_explanation_count = 0
    invalid_json_count = 0
    invalid_structure_count = 0

    print()
    print("Saved recommendation sample")
    print("-" * 100)

    for index, row in enumerate(
        rows,
        start=1,
    ):
        (
            app_id,
            saved_score,
            match_tier,
            explanation_json,
            row_generated_at,
        ) = row

        if match_tier == "top_pick":
            saved_top_pick_ids.add(app_id)
        elif match_tier is not None:
            problems.append(f"Unknown match tier {match_tier!r} for App ID {app_id}.")

        generated_score = build_scores.get(app_id)

        if generated_score is None:
            problems.append(f"Saved App ID {app_id} does not exist in generated build.")
            continue

        score_delta = abs(saved_score - generated_score.recommendation_score)

        if score_delta > SCORE_TOLERANCE:
            problems.append(f"Score mismatch for App ID {app_id}: delta={score_delta}")

        if row_generated_at != generated_at:
            problems.append(f"Generated timestamp mismatch for App ID {app_id}.")

        if explanation_json is None:
            missing_explanation_count += 1
            continue

        explanation_count += 1

        try:
            explanation = json.loads(explanation_json)

        except json.JSONDecodeError:
            invalid_json_count += 1

            problems.append(f"Invalid explanation JSON for App ID {app_id}.")

            continue

        if not isinstance(
            explanation,
            dict,
        ):
            invalid_structure_count += 1
            continue

        required_keys = {
            "taste_source",
            "taste_features",
            "supporting_games",
        }

        if not required_keys.issubset(explanation):
            invalid_structure_count += 1

            problems.append(
                f"Explanation for App ID {app_id} is missing required keys."
            )

            continue

        taste_features = explanation["taste_features"]

        supporting_games = explanation["supporting_games"]

        if not isinstance(
            taste_features,
            list,
        ):
            invalid_structure_count += 1

            problems.append(f"taste_features is not a list for App ID {app_id}.")

        if not isinstance(
            supporting_games,
            list,
        ):
            invalid_structure_count += 1

            problems.append(f"supporting_games is not a list for App ID {app_id}.")

            continue

        if len(supporting_games) > MAX_SUPPORTING_GAMES:
            problems.append(
                f"App ID {app_id} has {len(supporting_games)} supporting games."
            )

        for supporting_game in supporting_games:
            required_support_keys = {
                "app_id",
                "name",
                "raw_similarity",
                "adjusted_similarity",
                "shared_feature_count",
                "evidence",
                "feedback_weight",
                "playtime_minutes",
                "shared_features",
            }

            if not required_support_keys.issubset(supporting_game):
                invalid_structure_count += 1

                problems.append(
                    f"Supporting-game explanation "
                    f"for App ID {app_id} is "
                    "missing required fields."
                )

        if index <= 10:
            feature_names = [
                feature.get(
                    "name",
                    "<unknown>",
                )
                for feature in taste_features
            ]

            support_names = [
                supporting_game.get(
                    "name",
                    "<unknown>",
                )
                for supporting_game in supporting_games
            ]

            print(f"{index:>2}. {saved_score:.4f} | App ID {app_id}")

            print("    Taste: " + " • ".join(feature_names))

            print("    Supporting games: " + " | ".join(support_names))

            print(f"    JSON bytes: {len(explanation_json.encode('utf-8'))}")

    if saved_top_pick_ids != expected_top_pick_ids:
        missing_top_picks = expected_top_pick_ids - saved_top_pick_ids

        unexpected_top_picks = saved_top_pick_ids - expected_top_pick_ids

        if missing_top_picks:
            problems.append(
                "Missing persisted top picks: "
                + ", ".join(str(app_id) for app_id in sorted(missing_top_picks))
            )

        if unexpected_top_picks:
            problems.append(
                "Unexpected persisted top picks: "
                + ", ".join(str(app_id) for app_id in sorted(unexpected_top_picks))
            )

    if missing_explanation_count:
        problems.append(
            f"{missing_explanation_count} saved recommendations have no explanation."
        )

    if invalid_json_count:
        problems.append(f"{invalid_json_count} explanation rows contain invalid JSON.")

    if invalid_structure_count:
        problems.append(
            f"{invalid_structure_count} explanation rows have invalid structure."
        )

    print()
    print("Persistence summary")
    print("-" * 100)
    print(f"Generated candidates: {len(build.scores)}")
    print(f"Saved candidates: {len(rows)}")
    print(f"Saved explanations: {explanation_count}")
    print(f"Missing explanations: {missing_explanation_count}")
    print(f"Invalid JSON: {invalid_json_count}")
    print(f"Invalid structures: {invalid_structure_count}")
    print(f"Top picks: {len(saved_top_pick_ids)}")
    print()

    if problems:
        print(f"Persistence problems detected: {len(problems)}")

        for problem in problems:
            print(f" - {problem}")

        raise SystemExit(1)

    print("Persistence problems detected: 0")
    print(
        "Recommendation build, explanation JSON, "
        "and version metadata persisted correctly."
    )


if __name__ == "__main__":
    main()
