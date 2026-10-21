import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from storage.paths import DB_FILE


def table_exists(connection, table_name):
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()

    return row is not None


def column_exists(connection, table_name, column_name):
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column[1] == column_name for column in columns)


def scalar(connection, query, parameters=()):
    row = connection.execute(query, parameters).fetchone()
    return row[0] if row else 0


def print_section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_distribution(connection, column_name):
    rows = connection.execute(
        f"""
        SELECT COALESCE({column_name}, '<NULL>'), COUNT(*)
        FROM games
        GROUP BY {column_name}
        ORDER BY COUNT(*) DESC
        """
    ).fetchall()

    for value, count in rows:
        print(f"{str(value):25} {count:6}")


def main():
    if not DB_FILE.exists():
        raise FileNotFoundError(f"Database not found: {DB_FILE}")

    database_uri = f"{DB_FILE.resolve().as_uri()}?mode=ro"

    with sqlite3.connect(database_uri, uri=True) as connection:
        print(f"Database: {DB_FILE}")

        total_games = scalar(connection, "SELECT COUNT(*) FROM games")

        print_section("LIBRARY")
        print(f"Total database rows:       {total_games}")

        if column_exists(connection, "games", "steam_type"):
            print()
            print("Steam classification:")
            print_distribution(connection, "steam_type")

        print_section("PLAYTIME")

        print(
            f"Never played:              "
            f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE playtime_minutes = 0')}"
        )
        print(
            f"Played at least once:      "
            f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE playtime_minutes > 0')}"
        )
        print(
            f"Under 30 minutes:          "
            f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE playtime_minutes > 0 AND playtime_minutes < 30')}"
        )
        print(
            f"30 minutes - 2 hours:      "
            f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE playtime_minutes >= 30 AND playtime_minutes < 120')}"
        )
        print(
            f"2 - 10 hours:              "
            f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE playtime_minutes >= 120 AND playtime_minutes < 600')}"
        )
        print(
            f"10 - 50 hours:             "
            f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE playtime_minutes >= 600 AND playtime_minutes < 3000')}"
        )
        print(
            f"50+ hours:                 "
            f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE playtime_minutes >= 3000')}"
        )

        if column_exists(connection, "games", "last_played_timestamp"):
            print(
                f"Has last-played timestamp: "
                f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE last_played_timestamp > 0')}"
            )

        if column_exists(connection, "games", "manual_status"):
            print_section("MANUAL STATUS")
            print_distribution(connection, "manual_status")

            print()
            print("Status x playtime:")
            rows = connection.execute(
                """
                SELECT
                    COALESCE(manual_status, '<NULL>'),
                    COUNT(*),
                    SUM(CASE WHEN playtime_minutes = 0 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN playtime_minutes > 0 THEN 1 ELSE 0 END)
                FROM games
                GROUP BY manual_status
                ORDER BY COUNT(*) DESC
                """
            ).fetchall()

            print(f"{'Status':20} {'Total':>8} {'Unplayed':>10} {'Played':>10}")
            for status, total, unplayed, played in rows:
                print(f"{status:20} {total:8} {unplayed:10} {played:10}")

        print_section("GAME METADATA")

        if table_exists(connection, "game_genres"):
            genre_games = scalar(
                connection,
                "SELECT COUNT(DISTINCT app_id) FROM game_genres",
            )
            genre_links = scalar(connection, "SELECT COUNT(*) FROM game_genres")

            print(f"Games with genres:         {genre_games}")
            print(f"Total genre assignments:  {genre_links}")

            if genre_games:
                print(f"Average genres/game:       {genre_links / genre_games:.2f}")

        if table_exists(connection, "game_tags"):
            tag_games = scalar(
                connection,
                "SELECT COUNT(DISTINCT app_id) FROM game_tags",
            )
            tag_links = scalar(connection, "SELECT COUNT(*) FROM game_tags")

            print(f"Games with tags:           {tag_games}")
            print(f"Total tag assignments:    {tag_links}")

            if tag_games:
                print(f"Average tags/game:         {tag_links / tag_games:.2f}")

        hltb_columns = [
            column
            for column in (
                "hltb_main",
                "hltb_main_extra",
                "hltb_completionist",
                "hltb_all_styles",
            )
            if column_exists(connection, "games", column)
        ]

        if hltb_columns:
            condition = " OR ".join(f"{column} IS NOT NULL" for column in hltb_columns)
            print(
                f"Games with HLTB data:      "
                f"{scalar(connection, f'SELECT COUNT(*) FROM games WHERE {condition}')}"
            )

        print_section("ACHIEVEMENTS")

        if column_exists(connection, "games", "achievement_total"):
            print(
                f"Games with achievement data: "
                f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE achievement_total IS NOT NULL')}"
            )
            print(
                f"Games with achievements:     "
                f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE achievement_total > 0')}"
            )

            if column_exists(connection, "games", "achievements_unlocked"):
                print(
                    f"Any achievements unlocked:   "
                    f"{scalar(connection, 'SELECT COUNT(*) FROM games WHERE achievements_unlocked > 0')}"
                )
                print(
                    f"100% achievements:            "
                    f"{
                        scalar(
                            connection,
                            '''
                        SELECT COUNT(*)
                        FROM games
                        WHERE achievement_total > 0
                          AND achievements_unlocked = achievement_total
                    ''',
                        )
                    }"
                )

        print_section("ROUGH RECOMMENDATION POOLS")

        if column_exists(connection, "games", "steam_type"):
            game_filter = "steam_type = 'game'"
        else:
            game_filter = "1 = 1"

        actual_games = scalar(
            connection,
            f"SELECT COUNT(*) FROM games WHERE {game_filter}",
        )
        played_games = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM games
            WHERE {game_filter}
              AND playtime_minutes > 0
            """,
        )
        unplayed_games = scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM games
            WHERE {game_filter}
              AND playtime_minutes = 0
            """,
        )

        print(f"Confirmed games:           {actual_games}")
        print(f"Played confirmed games:    {played_games}")
        print(f"Unplayed confirmed games:  {unplayed_games}")

        if table_exists(connection, "game_tags") and table_exists(
            connection, "game_genres"
        ):
            candidate_metadata = scalar(
                connection,
                f"""
                SELECT COUNT(*)
                FROM games g
                WHERE {game_filter}
                  AND g.playtime_minutes = 0
                  AND (
                      EXISTS (
                          SELECT 1
                          FROM game_tags gt
                          WHERE gt.app_id = g.app_id
                      )
                      OR EXISTS (
                          SELECT 1
                          FROM game_genres gg
                          WHERE gg.app_id = g.app_id
                      )
                  )
                """,
            )

            print(f"Unplayed with tags/genres: {candidate_metadata}")


if __name__ == "__main__":
    main()
