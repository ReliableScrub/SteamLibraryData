import argparse
import math
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from recommendations.clustering import (
    positive_feedback_weight,
    train_taste_clusters,
)
from recommendations.data import load_recommendation_games
from recommendations.features import build_content_features, cosine_similarity
from recommendations.feedback import final_feedback
from recommendations.profile import build_preference_profile
from storage.database import get_connection


def find_game(games, search_text):
    search = search_text.casefold()

    exact = [game for game in games if game.name.casefold() == search]

    if exact:
        return exact[0]

    partial = [game for game in games if search in game.name.casefold()]

    if len(partial) == 1:
        return partial[0]

    if len(partial) > 1:
        print("Multiple games matched:")
        for game in partial[:20]:
            print(f"  {game.name} ({game.app_id})")
        return None

    print(f'No game matched "{search_text}".')
    return None


def summary(games, vectors):
    profile = build_preference_profile(games, vectors)

    feedback_counts = Counter()
    played = 0

    for game in games:
        if game.playtime_minutes > 0:
            played += 1

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
            feedback_counts["none"] += 1
        elif feedback.score > 0:
            feedback_counts["positive"] += 1
        elif feedback.score < 0:
            feedback_counts["negative"] += 1
        else:
            feedback_counts["neutral"] += 1

    magnitude = math.sqrt(sum(value * value for value in profile.values()))

    print(f"Confirmed games: {len(games)}")
    print(f"Played games: {played}")
    print(f"Unplayed games: {len(games) - played}")
    print(f"Content vectors: {len(vectors)}")
    print(f"Profile features: {len(profile)}")
    print(f"Profile magnitude: {magnitude:.6f}")

    print()
    print("Feedback coverage:")
    for label in ("positive", "negative", "neutral", "none"):
        print(f"  {label:<10} {feedback_counts[label]}")

    positive_features = sorted(
        ((feature, weight) for feature, weight in profile.items() if weight > 0),
        key=lambda item: item[1],
        reverse=True,
    )

    negative_features = sorted(
        ((feature, weight) for feature, weight in profile.items() if weight < 0),
        key=lambda item: item[1],
    )

    print()
    print("Strongest positive profile features:")
    for feature, weight in positive_features[:25]:
        print(f"  {weight:+.4f}  {feature}")

    print()
    print("Strongest negative profile features:")
    for feature, weight in negative_features[:15]:
        print(f"  {weight:+.4f}  {feature}")


def inspect_game(games, vectors, search_text):
    game = find_game(games, search_text)

    if game is None:
        return

    vector = vectors.get(game.app_id, {})

    print(f"{game.name} ({game.app_id})")
    print(f"Playtime: {game.playtime_minutes / 60:.1f}h")
    print(f"Rating: {game.rating}")
    print(f"Genres: {', '.join(game.genres) if game.genres else '<none>'}")

    print()
    print("Raw tags:")
    for tag, weight in sorted(
        game.tags.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:20]:
        print(f"  {weight:>6}  {tag}")

    print()
    print("Weighted features:")
    for feature, weight in sorted(
        vector.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:20]:
        print(f"  {weight:.4f}  {feature}")

    similarities = []

    for candidate in games:
        if candidate.app_id == game.app_id:
            continue

        candidate_vector = vectors.get(candidate.app_id)

        if not candidate_vector:
            continue

        similarities.append(
            (
                cosine_similarity(vector, candidate_vector),
                candidate,
            )
        )

    similarities.sort(
        key=lambda item: (
            -item[0],
            item[1].name.casefold(),
        )
    )

    print()
    print("Most similar games:")
    for similarity, candidate in similarities[:10]:
        print(f"  {similarity:.3f}  {candidate.name} ({candidate.app_id})")


def tag_summary():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                tags.name,
                COUNT(DISTINCT game_tags.app_id) AS game_count,
                AVG(game_tags.weight) AS average_weight,
                MAX(game_tags.weight) AS maximum_weight
            FROM tags
            JOIN game_tags
                ON tags.tag_id = game_tags.tag_id
            JOIN games
                ON game_tags.app_id = games.app_id
            WHERE games.steam_type = 'game'
            GROUP BY tags.tag_id, tags.name
            ORDER BY game_count DESC, tags.name COLLATE NOCASE
            """
        ).fetchall()

    print(f"Distinct tags: {len(rows)}")
    print()
    print(f"{'Tag':<40} {'Games':>7} {'Avg':>10} {'Max':>10}")
    print("-" * 72)

    for name, game_count, average_weight, maximum_weight in rows:
        print(
            f"{name:<40} {game_count:>7} {average_weight:>10.1f} {maximum_weight:>10}"
        )


def inspect_tag(tag_name):
    with get_connection() as connection:
        rows = connection.execute(
            """
            WITH totals AS (
                SELECT
                    app_id,
                    SUM(weight) AS total_weight,
                    COUNT(*) AS tag_count
                FROM game_tags
                GROUP BY app_id
            )
            SELECT
                games.app_id,
                games.name,
                game_tags.weight,
                totals.total_weight,
                totals.tag_count,
                CAST(game_tags.weight AS REAL) / totals.total_weight AS share
            FROM games
            JOIN game_tags
                ON games.app_id = game_tags.app_id
            JOIN tags
                ON game_tags.tag_id = tags.tag_id
            JOIN totals
                ON totals.app_id = games.app_id
            WHERE games.steam_type = 'game'
              AND tags.name = ?
            ORDER BY share DESC, game_tags.weight DESC, games.name COLLATE NOCASE
            """,
            (tag_name,),
        ).fetchall()

    print(f"Tag: {tag_name}")
    print(f"Matching games: {len(rows)}")
    print()

    for index, row in enumerate(rows[:50], start=1):
        app_id, name, weight, total_weight, tag_count, share = row

        print(f"{index:>2}. {name} ({app_id})")
        print(
            f"    weight={weight} | "
            f"share={share * 100:.2f}% | "
            f"{tag_count} total tags | "
            f"total weight={total_weight}"
        )


def inspect_clusters(games, vectors):
    model = train_taste_clusters(
        games,
        vectors,
    )

    if model is None:
        print("Not enough positive history for taste clusters.")
        return

    qualified = [
        game
        for game in games
        if game.playtime_minutes > 0
        and vectors.get(game.app_id)
        and positive_feedback_weight(game) > 0
    ]

    print(f"Taste clusters: {len(model.cluster_centers)}")
    print(f"Positive played games: {len(qualified)}")

    for index, center in enumerate(model.cluster_centers):
        print()
        print(f"Cluster {index} ({model.cluster_sizes[index]} training games)")
        print("-" * 72)

        for feature, weight in sorted(
            center.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )[:15]:
            print(f"  {weight:7.4f}  {feature}")

        closest = sorted(
            (
                (
                    cosine_similarity(vectors[game.app_id], center),
                    game,
                )
                for game in qualified
            ),
            key=lambda item: (
                -item[0],
                item[1].name.casefold(),
            ),
        )

        print("  Closest played games:")
        for similarity, game in closest[:8]:
            print(f"    {similarity:.4f}  {game.name}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Ad-hoc recommendation data inspector replacing separate "
            "feedback/profile/tag/feature/cluster audit scripts."
        )
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser("summary")
    subparsers.add_parser("tags")
    subparsers.add_parser("clusters")

    game_parser = subparsers.add_parser("game")
    game_parser.add_argument("name")

    tag_parser = subparsers.add_parser("tag")
    tag_parser.add_argument("name")

    args = parser.parse_args()

    if args.command == "tags":
        tag_summary()
        return

    if args.command == "tag":
        inspect_tag(args.name)
        return

    games = load_recommendation_games()
    vectors = build_content_features(games)

    if args.command == "summary":
        summary(games, vectors)
    elif args.command == "game":
        inspect_game(games, vectors, args.name)
    else:
        inspect_clusters(games, vectors)


if __name__ == "__main__":
    main()
