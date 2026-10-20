from recommendations.baseline import score_unplayed_games
from recommendations.data import load_recommendation_games
from recommendations.features import build_content_features
from recommendations.feedback import final_feedback
from recommendations.profile import build_preference_profile

TOP_RESULTS = 25


def nearest_name(
    score,
    games_by_id,
):
    if score.nearest_positive_app_id is None:
        return "None"

    return games_by_id[score.nearest_positive_app_id].name


def feature_count(vector):
    return sum(value != 0 for value in vector.values())


def print_reference_weight_distribution(games):
    reference_weights = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue

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
            continue

        if feedback.score <= 0:
            continue

        reference_weights.append(feedback.score * feedback.confidence)

    print("Positive reference weight distribution:")

    for threshold in (
        0.010,
        0.025,
        0.050,
        0.100,
        0.150,
        0.200,
        0.250,
        0.300,
    ):
        count = sum(weight >= threshold for weight in reference_weights)

        print(f"  >= {threshold:5.3f}: {count:4d} games")


def print_score(
    score,
    games_by_id,
    content_vectors,
):
    game = games_by_id[score.app_id]

    candidate_vector = content_vectors.get(
        score.app_id,
        {},
    )

    reference_vector = content_vectors.get(
        score.nearest_positive_app_id,
        {},
    )

    candidate_count = feature_count(candidate_vector)

    reference_count = feature_count(reference_vector)

    print(
        f"{score.nearest_positive_adjusted_similarity:6.3f} adjusted | "
        f"{score.nearest_positive_similarity:6.3f} raw | "
        f"{score.profile_similarity:6.3f} profile | "
        f"{score.nearest_positive_feedback_weight:6.3f} ref weight | "
        f"{score.nearest_positive_shared_features:2d} shared "
        f"({candidate_count}/{reference_count}) | "
        f"{game.name} | "
        f"nearest: {nearest_name(score, games_by_id)}"
    )


def main():
    games = load_recommendation_games()

    games_by_id = {game.app_id: game for game in games}

    print_reference_weight_distribution(games)

    content_vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        content_vectors,
    )

    scores = score_unplayed_games(
        games,
        content_vectors,
        profile,
    )

    print()
    print(f"Confirmed games: {len(games)}")

    print(f"Candidate unplayed games: {len(scores)}")

    print()
    print("Top games by global profile similarity:")

    by_profile = sorted(
        scores,
        key=lambda score: score.profile_similarity,
        reverse=True,
    )

    for score in by_profile[:TOP_RESULTS]:
        print_score(
            score,
            games_by_id,
            content_vectors,
        )

    print()
    print("Top games by support-adjusted nearest positive-game similarity:")

    by_nearest = sorted(
        scores,
        key=lambda score: score.nearest_positive_adjusted_similarity,
        reverse=True,
    )

    for score in by_nearest[:TOP_RESULTS]:
        print_score(
            score,
            games_by_id,
            content_vectors,
        )

    profile_top_ids = {score.app_id for score in by_profile[:TOP_RESULTS]}

    nearest_top_ids = {score.app_id for score in by_nearest[:TOP_RESULTS]}

    overlap = len(profile_top_ids & nearest_top_ids)

    print()
    print(f"Top-{TOP_RESULTS} overlap: {overlap} games")

    print()
    print("Highest raw similarities with sparse support:")

    sparse_matches = sorted(
        (
            score
            for score in scores
            if (
                score.nearest_positive_similarity >= 0.90
                and score.nearest_positive_shared_features < 10
            )
        ),
        key=lambda score: score.nearest_positive_similarity,
        reverse=True,
    )

    if not sparse_matches:
        print("  None")
    else:
        for score in sparse_matches[:20]:
            print_score(
                score,
                games_by_id,
                content_vectors,
            )


if __name__ == "__main__":
    main()
