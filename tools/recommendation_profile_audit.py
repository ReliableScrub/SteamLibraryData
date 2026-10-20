import math

from recommendations.data import load_recommendation_games
from recommendations.features import build_content_features
from recommendations.feedback import final_feedback
from recommendations.profile import build_preference_profile


def main():
    games = load_recommendation_games()
    content_vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        content_vectors,
    )

    positive_games = 0
    negative_games = 0
    neutral_games = 0
    no_feedback_games = 0

    for game in games:
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
            no_feedback_games += 1
        elif feedback.score > 0:
            positive_games += 1
        elif feedback.score < 0:
            negative_games += 1
        else:
            neutral_games += 1

    magnitude = math.sqrt(sum(value * value for value in profile.values()))

    positive_features = sorted(
        ((feature, value) for feature, value in profile.items() if value > 0),
        key=lambda item: item[1],
        reverse=True,
    )

    negative_features = sorted(
        ((feature, value) for feature, value in profile.items() if value < 0),
        key=lambda item: item[1],
    )

    print(f"Confirmed games: {len(games)}")
    print(f"Content vectors: {len(content_vectors)}")
    print(f"Profile features: {len(profile)}")
    print(f"Profile magnitude: {magnitude:.6f}")

    print()
    print("Final feedback coverage:")
    print(f"  Positive:    {positive_games}")
    print(f"  Negative:    {negative_games}")
    print(f"  Neutral:     {neutral_games}")
    print(f"  No feedback: {no_feedback_games}")

    print()
    print("Strongest positive profile features:")

    for feature, value in positive_features[:40]:
        print(f"  {value:+.4f}  {feature}")

    print()
    print("Strongest negative profile features:")

    if negative_features:
        for feature, value in negative_features[:20]:
            print(f"  {value:+.4f}  {feature}")
    else:
        print("  None")


if __name__ == "__main__":
    main()
