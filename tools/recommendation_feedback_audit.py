from collections import Counter

from recommendations.feedback import (
    achievement_progress,
    implicit_feedback,
    playtime_ratios,
)
from storage.database import get_connection, load_games


def percentile(values, fraction):
    if not values:
        return None

    values = sorted(values)
    index = round((len(values) - 1) * fraction)

    return values[index]


def print_distribution(label, values):
    print()
    print(label)
    print(f"  Count: {len(values)}")

    if not values:
        return

    print(f"  Min:    {min(values):.3f}")
    print(f"  10%:    {percentile(values, 0.10):.3f}")
    print(f"  25%:    {percentile(values, 0.25):.3f}")
    print(f"  Median: {percentile(values, 0.50):.3f}")
    print(f"  75%:    {percentile(values, 0.75):.3f}")
    print(f"  90%:    {percentile(values, 0.90):.3f}")
    print(f"  95%:    {percentile(values, 0.95):.3f}")
    print(f"  Max:    {max(values):.3f}")


def load_ratings():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT game_ratings.rating
            FROM game_ratings
            JOIN games
                ON games.app_id = game_ratings.app_id
            WHERE games.steam_type = 'game'
            """
        ).fetchall()

    return [row[0] for row in rows]


def main():
    games = [game for game in load_games() if game.steam_type == "game"]

    played_games = [game for game in games if game.playtime_minutes > 0]

    playtime_hours = [game.playtime_minutes / 60 for game in played_games]

    achievement_values = []

    main_ratios = []
    main_extra_ratios = []
    completionist_ratios = []
    all_styles_ratios = []

    recent_minutes = []

    manual_statuses = Counter(
        game.manual_status for game in games if game.manual_status is not None
    )
    implicit_rows = []

    for game in games:
        if game.playtime_minutes <= 0:
            continue
        feedback = implicit_feedback(
            playtime_minutes=game.playtime_minutes,
            hltb_main=game.hltb_main,
            hltb_main_extra=game.hltb_main_extra,
            hltb_completionist=game.hltb_completionist,
            hltb_all_styles=game.hltb_all_styles,
            achievement_total=game.achievement_total,
            achievements_unlocked=game.achievements_unlocked,
        )

        if feedback is not None:
            evidence_weight = feedback.score * feedback.confidence

            implicit_rows.append(
                (
                    evidence_weight,
                    feedback,
                    game,
                )
            )
        progress = achievement_progress(
            game.achievement_total,
            game.achievements_unlocked,
        )

        if progress is not None:
            achievement_values.append(progress)

        ratios = playtime_ratios(
            game.playtime_minutes,
            game.hltb_main,
            game.hltb_main_extra,
            game.hltb_completionist,
            game.hltb_all_styles,
        )

        if ratios.main_story is not None:
            main_ratios.append(ratios.main_story)

        if ratios.main_extra is not None:
            main_extra_ratios.append(ratios.main_extra)

        if ratios.completionist is not None:
            completionist_ratios.append(ratios.completionist)

        if ratios.all_styles is not None:
            all_styles_ratios.append(ratios.all_styles)

        if game.playtime_2weeks_minutes > 0:
            recent_minutes.append(game.playtime_2weeks_minutes)

    ratings = load_ratings()
    rating_counts = Counter(ratings)

    print(f"Confirmed games: {len(games)}")
    print(f"Played games: {len(played_games)}")
    print(f"Unplayed games: {len(games) - len(played_games)}")

    print()
    print("Manual statuses:")

    if manual_statuses:
        for status, count in manual_statuses.items():
            print(f"  {status}: {count}")
    else:
        print("  None")

    print()
    print("Explicit ratings:")

    if rating_counts:
        for rating in range(1, 6):
            print(f"  {rating} star: {rating_counts.get(rating, 0)}")
    else:
        print("  None")

    print_distribution(
        "Playtime hours",
        playtime_hours,
    )

    print_distribution(
        "Achievement progress",
        achievement_values,
    )

    print_distribution(
        "Playtime / HLTB Main Story",
        main_ratios,
    )

    print_distribution(
        "Playtime / HLTB Main + Extra",
        main_extra_ratios,
    )

    print_distribution(
        "Playtime / HLTB Completionist",
        completionist_ratios,
    )

    print_distribution(
        "Playtime / HLTB All Styles",
        all_styles_ratios,
    )

    print_distribution(
        "Recent activity minutes",
        recent_minutes,
    )

    implicit_rows.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    print()
    print("Strongest implicit positive evidence:")

    for evidence_weight, feedback, game in implicit_rows[:30]:
        hours = game.playtime_minutes / 60

        print(
            f"  {evidence_weight:.3f}  "
            f"score={feedback.score:.3f}  "
            f"confidence={feedback.confidence:.3f}  "
            f"hours={hours:.1f}  "
            f"{game.name}"
        )


if __name__ == "__main__":
    main()
