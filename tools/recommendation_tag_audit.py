from storage.database import get_connection


def load_tag_statistics():
    with get_connection() as connection:
        return connection.execute(
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
            ORDER BY tags.name COLLATE NOCASE
            """
        ).fetchall()


def main():
    rows = load_tag_statistics()

    print(f"Distinct tags: {len(rows)}")
    print()

    print(f"{'Tag':<40} {'Games':>7} {'Avg Weight':>12} {'Max Weight':>12}")

    print("-" * 76)

    for name, game_count, average_weight, maximum_weight in rows:
        print(
            f"{name:<40} {game_count:>7} {average_weight:>12.1f} {maximum_weight:>12}"
        )


if __name__ == "__main__":
    main()
