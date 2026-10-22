import argparse

from storage.database import get_connection


def load_tag_games(tag_name):
    with get_connection() as connection:
        return connection.execute(
            """
            WITH game_tag_totals AS (
                SELECT
                    app_id,
                    SUM(weight) AS total_weight,
                    COUNT(*) AS tag_count
                FROM game_tags
                GROUP BY app_id
            ),
            target_games AS (
                SELECT
                    games.app_id,
                    games.name,
                    game_tags.weight AS target_weight
                FROM games
                JOIN game_tags
                    ON games.app_id = game_tags.app_id
                JOIN tags
                    ON game_tags.tag_id = tags.tag_id
                WHERE games.steam_type = 'game'
                  AND tags.name = ?
            )
            SELECT
                target_games.app_id,
                target_games.name,
                target_games.target_weight,
                game_tag_totals.total_weight,
                game_tag_totals.tag_count,
                (
                    CAST(target_games.target_weight AS REAL)
                    / game_tag_totals.total_weight
                ) AS weight_share,
                (
                    SELECT
                        1 + COUNT(*)
                    FROM game_tags AS other_tags
                    WHERE other_tags.app_id = target_games.app_id
                      AND other_tags.weight > target_games.target_weight
                ) AS tag_rank
            FROM target_games
            JOIN game_tag_totals
                ON target_games.app_id = game_tag_totals.app_id
            ORDER BY
                weight_share DESC,
                target_games.target_weight DESC,
                target_games.name COLLATE NOCASE
            """,
            (tag_name,),
        ).fetchall()


def load_top_tags(app_id, limit=5):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                tags.name,
                game_tags.weight
            FROM game_tags
            JOIN tags
                ON game_tags.tag_id = tags.tag_id
            WHERE game_tags.app_id = ?
            ORDER BY
                game_tags.weight DESC,
                tags.name COLLATE NOCASE
            LIMIT ?
            """,
            (app_id, limit),
        ).fetchall()


def main():
    parser = argparse.ArgumentParser(
        description="Inspect how strongly a SteamSpy tag applies to games."
    )

    parser.add_argument(
        "tag",
        help='Tag name, for example "Mystery Dungeon"',
    )

    args = parser.parse_args()

    rows = load_tag_games(args.tag)

    print(f"Tag: {args.tag}")
    print(f"Matching games: {len(rows)}")
    print()

    for index, row in enumerate(rows, start=1):
        (
            app_id,
            name,
            target_weight,
            total_weight,
            tag_count,
            weight_share,
            tag_rank,
        ) = row

        print(f"{index:>2}. {name} ({app_id})")

        print(f"    {args.tag}: {target_weight}")

        print(f"    total tag weight: {total_weight}")

        print(f"    share: {weight_share * 100:.2f}%")

        print(f"    tag rank: #{tag_rank} of {tag_count}")

        top_tags = load_top_tags(app_id)

        print(
            "    top tags: "
            + ", ".join(f"{tag} ({weight})" for tag, weight in top_tags)
        )

        print()


if __name__ == "__main__":
    main()
