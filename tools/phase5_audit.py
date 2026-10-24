import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from storage.paths import DB_FILE

VALID_STEAM_TYPES = {
    "game",
    "software",
    "dlc",
    "video",
    "hardware",
    "unknown",
}


def open_read_only(database_path):
    database_path = database_path.expanduser().resolve()

    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    connection = sqlite3.connect(
        f"{database_path.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def tables(connection):
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {row["name"] for row in rows}


def columns(connection, table):
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def scalar(connection, query, parameters=()):
    row = connection.execute(query, parameters).fetchone()
    return row[0] if row else 0


def heading(title):
    print()
    print(title)
    print("-" * len(title))


def count(label, value):
    print(f"{label:<36} {int(value):,}")


def value(label, result):
    print(f"{label:<36} {result}")


def format_timestamp(timestamp):
    if timestamp is None:
        return "n/a"

    try:
        return (
            datetime.fromtimestamp(int(timestamp))
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S %Z")
        )
    except (OSError, OverflowError, TypeError, ValueError):
        return f"invalid ({timestamp!r})"


def timestamp_columns(connection, source):
    found = []

    for table in sorted(tables(connection)):
        for column in sorted(columns(connection, table)):
            lower = column.casefold()

            if source not in lower:
                continue

            if not any(word in lower for word in ("updated", "checked", "refresh")):
                continue

            if not (lower.endswith("_at") or "timestamp" in lower):
                continue

            found.append((table, column))

    return found


def print_timestamp_summary(connection, source, label):
    found = timestamp_columns(connection, source)

    if not found:
        value(label, "No timestamp column found")
        return

    for table, column in found:
        row = connection.execute(
            f"""
            SELECT
                COUNT({column}) AS populated,
                MIN({column}) AS oldest,
                MAX({column}) AS newest
            FROM {table}
            WHERE {column} IS NOT NULL
            """
        ).fetchone()

        value(
            f"{label} ({table}.{column})",
            f"{row['populated']:,} timestamps",
        )
        value("  Oldest", format_timestamp(row["oldest"]))
        value("  Newest", format_timestamp(row["newest"]))


def audit_database(database_path):
    errors = []
    warnings = []

    with open_read_only(database_path) as connection:
        available_tables = tables(connection)

        print("Steam Backlog DB - Phase 5 Audit")
        print("=" * 38)
        print(f"Database: {database_path.expanduser().resolve()}")

        heading("SQLite integrity")

        integrity = [
            row[0] for row in connection.execute("PRAGMA integrity_check").fetchall()
        ]

        if integrity == ["ok"]:
            value("Integrity check", "PASS")
        else:
            value("Integrity check", "FAIL")
            errors.extend(f"SQLite integrity: {item}" for item in integrity)

        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        count("Foreign-key violations", len(foreign_keys))

        if foreign_keys:
            errors.append(f"{len(foreign_keys)} foreign-key violation(s)")

        required_tables = {
            "games",
            "genres",
            "game_genres",
            "tags",
            "game_tags",
            "hltb_candidates",
            "game_ratings",
            "recommendation_state",
            "game_recommendations",
        }

        missing_tables = sorted(required_tables - available_tables)

        if missing_tables:
            errors.append("Missing expected table(s): " + ", ".join(missing_tables))

        if "games" not in available_tables:
            return errors, warnings

        game_columns = columns(connection, "games")
        total_rows = scalar(connection, "SELECT COUNT(*) FROM games")

        heading("Library")

        count("Database rows", total_rows)

        if "steam_type" in game_columns:
            type_rows = connection.execute(
                """
                SELECT COALESCE(steam_type, '<NULL>') AS steam_type, COUNT(*) AS count
                FROM games
                GROUP BY steam_type
                ORDER BY count DESC, steam_type
                """
            ).fetchall()

            seen_types = set()

            for row in type_rows:
                count(f"Steam type: {row['steam_type']}", row["count"])
                seen_types.add(row["steam_type"])

            invalid = sorted(
                steam_type
                for steam_type in seen_types
                if steam_type not in VALID_STEAM_TYPES
            )

            if invalid:
                errors.append(
                    "Invalid steam_type value(s): "
                    + ", ".join(repr(item) for item in invalid)
                )

        if "playtime_minutes" in game_columns:
            count(
                "Never played",
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM games WHERE playtime_minutes = 0",
                ),
            )
            count(
                "Played at least once",
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM games WHERE playtime_minutes > 0",
                ),
            )
            count(
                "Played 50+ hours",
                scalar(
                    connection,
                    """
                    SELECT COUNT(*)
                    FROM games
                    WHERE playtime_minutes >= 3000
                    """,
                ),
            )

        if "manual_status" in game_columns:
            status_rows = connection.execute(
                """
                SELECT COALESCE(manual_status, '<NULL>') AS status, COUNT(*) AS count
                FROM games
                GROUP BY manual_status
                ORDER BY count DESC
                """
            ).fetchall()

            heading("Manual status")

            for row in status_rows:
                count(row["status"], row["count"])

        heading("Maintenance coverage")

        for column, label in (
            ("classification_updated_at", "Classification checked"),
            ("metadata_checked", "Metadata checked"),
            ("hltb_checked", "HLTB checked"),
            ("achievements_checked", "Achievements checked"),
        ):
            if column not in game_columns:
                value(label, "Column not present")
                continue

            if column.endswith("_at"):
                checked = scalar(
                    connection,
                    f"SELECT COUNT(*) FROM games WHERE {column} IS NOT NULL",
                )
            else:
                checked = scalar(
                    connection,
                    f"SELECT COUNT(*) FROM games WHERE {column} = 1",
                )

            value(label, f"{checked:,} / {total_rows:,}")

        heading("Refresh timestamps")
        print_timestamp_summary(connection, "classification", "Classification")
        print_timestamp_summary(connection, "metadata", "Metadata")
        print_timestamp_summary(connection, "hltb", "HLTB")
        print_timestamp_summary(connection, "achievement", "Achievements")

        heading("Metadata")

        if {"game_genres", "genres"}.issubset(available_tables):
            genre_games = scalar(
                connection,
                "SELECT COUNT(DISTINCT app_id) FROM game_genres",
            )
            genre_links = scalar(connection, "SELECT COUNT(*) FROM game_genres")
            count("Games with genres", genre_games)
            count("Genre assignments", genre_links)

        if {"game_tags", "tags"}.issubset(available_tables):
            tag_games = scalar(
                connection,
                "SELECT COUNT(DISTINCT app_id) FROM game_tags",
            )
            tag_links = scalar(connection, "SELECT COUNT(*) FROM game_tags")
            count("Games with tags", tag_games)
            count("Tag assignments", tag_links)

        if {"game_genres", "genres"}.issubset(available_tables):
            orphan_genres = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM game_genres AS mapping
                LEFT JOIN games AS game ON game.app_id = mapping.app_id
                LEFT JOIN genres AS genre ON genre.genre_id = mapping.genre_id
                WHERE game.app_id IS NULL OR genre.genre_id IS NULL
                """,
            )
            count("Orphan genre mappings", orphan_genres)

            if orphan_genres:
                errors.append(f"{orphan_genres} orphan genre mapping(s)")

        if {"game_tags", "tags"}.issubset(available_tables):
            orphan_tags = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM game_tags AS mapping
                LEFT JOIN games AS game ON game.app_id = mapping.app_id
                LEFT JOIN tags AS tag ON tag.tag_id = mapping.tag_id
                WHERE game.app_id IS NULL OR tag.tag_id IS NULL
                """,
            )
            count("Orphan tag mappings", orphan_tags)

            if orphan_tags:
                errors.append(f"{orphan_tags} orphan tag mapping(s)")

        heading("HLTB")

        if {"hltb_checked", "hltb_match_status"}.issubset(game_columns):
            rows = connection.execute(
                """
                SELECT COALESCE(hltb_match_status, '<none>') AS status, COUNT(*) AS count
                FROM games
                WHERE hltb_checked = 1
                GROUP BY hltb_match_status
                ORDER BY count DESC
                """
            ).fetchall()

            for row in rows:
                count(f"Checked: {row['status']}", row["count"])

            review_count = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM games
                WHERE hltb_match_status = 'review'
                """,
            )

            if review_count:
                warnings.append(f"{review_count} HLTB match(es) still need review")

        if "hltb_candidates" in available_tables:
            orphan_candidates = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM hltb_candidates AS candidate
                LEFT JOIN games AS game ON game.app_id = candidate.app_id
                WHERE game.app_id IS NULL
                """,
            )
            count("Orphan HLTB candidates", orphan_candidates)

            if orphan_candidates:
                errors.append(f"{orphan_candidates} orphan HLTB candidate row(s)")

        heading("Achievements")

        if {"achievement_total", "achievements_unlocked"}.issubset(game_columns):
            invalid_achievements = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM games
                WHERE achievement_total < 0
                   OR achievements_unlocked < 0
                   OR (
                        achievement_total IS NOT NULL
                        AND achievements_unlocked IS NOT NULL
                        AND achievements_unlocked > achievement_total
                   )
                """,
            )
            count("Invalid achievement totals", invalid_achievements)

            if invalid_achievements:
                errors.append(
                    f"{invalid_achievements} game(s) have invalid achievement totals"
                )

        if {
            "achievements_checked",
            "playtime_minutes",
            "achievements_playtime_minutes",
        }.issubset(game_columns):
            changed = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM games
                WHERE achievements_checked = 1
                  AND achievements_playtime_minutes IS NOT NULL
                  AND playtime_minutes > achievements_playtime_minutes
                """,
            )
            count("Eligible for Refresh Changed", changed)

            if changed:
                warnings.append(
                    f"{changed} game(s) have more playtime than their achievement check"
                )

        heading("Ratings and recommendations")

        if "game_ratings" in available_tables:
            ratings = scalar(connection, "SELECT COUNT(*) FROM game_ratings")
            count("Personal ratings", ratings)

        if "recommendation_state" in available_tables:
            state_rows = scalar(
                connection,
                "SELECT COUNT(*) FROM recommendation_state",
            )
            count("Recommendation state rows", state_rows)

            if state_rows > 1:
                errors.append("recommendation_state contains more than one row")

        if "game_recommendations" in available_tables:
            recommendations = scalar(
                connection,
                "SELECT COUNT(*) FROM game_recommendations",
            )
            count("Saved recommendations", recommendations)

            orphan_recommendations = scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM game_recommendations AS recommendation
                LEFT JOIN games AS game ON game.app_id = recommendation.app_id
                WHERE game.app_id IS NULL
                """,
            )
            count("Orphan recommendations", orphan_recommendations)

            if orphan_recommendations:
                errors.append(
                    f"{orphan_recommendations} recommendation row(s) reference missing games"
                )

        heading("Result")

        if errors:
            print("FAIL")
        elif warnings:
            print("PASS WITH WARNINGS")
        else:
            print("PASS")

        if errors:
            print()
            print("Errors:")
            for message in errors:
                print(f"  - {message}")

        if warnings:
            print()
            print("Warnings:")
            for message in warnings:
                print(f"  - {message}")

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Phase 5 database and maintenance audit."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_FILE,
        help="Database path. Defaults to the application's configured database.",
    )
    args = parser.parse_args()

    try:
        errors, _warnings = audit_database(args.db)
    except (FileNotFoundError, sqlite3.Error) as error:
        print(f"Audit could not run: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
