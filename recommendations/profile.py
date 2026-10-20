from recommendations.features import normalize_vector
from recommendations.feedback import final_feedback


def build_preference_profile(games, content_vectors):
    profile = {}

    for game in games:
        vector = content_vectors.get(game.app_id)

        if not vector:
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

        weight = feedback.score * feedback.confidence

        if weight == 0:
            continue

        for feature, value in vector.items():
            profile[feature] = profile.get(feature, 0.0) + value * weight

    return normalize_vector(profile)
