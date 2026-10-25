import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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

    uri = f"{database_path.as_uri()}?mode=ro"

    connection = sqlite3.connect(
        uri,
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


def table_names(connection):
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    return {row["name"] for row in rows}


def table_columns(connection, table):
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()

    return {row["name"] for row in rows}


def scalar(connection, query, parameters=()):
    row = connection.execute(
        query,
        parameters,
    ).fetchone()

    if row is None:
        return None

    return row[0]


def format_timestamp(value):
    if value is None:
        return "n/a"

    try:
        return (
            datetime.fromtimestamp(int(value))
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S %Z")
        )
    except (OSError, OverflowError, TypeError, ValueError):
        return f"invalid ({value!r})"


def print_heading(title):
    print()
    print(title)
    print("-" * len(title))


def print_count(label, value):
    print(f"{label:<34} {value:,}")


def print_value(label, value):
    print(f"{label:<34} {value}")


def timestamp_candidates(connection, source):
    candidates = []

    for table in sorted(table_names(connection)):
        columns = table_columns(connection, table)

        for column in sorted(columns):
            lower = column.lower()

            if source not in lower:
                continue

            if (
                "updated" not in lower
                and "checked" not in lower
                and "refresh" not in lower
            ):
                continue

            if not lower.endswith("_at") and "timestamp" not in lower:
                continue

            candidates.append((table, column))

    return candidates


def print_timestamp_summary(connection, source, label):
    candidates = timestamp_candidates(
        connection,
        source,
    )

    if not candidates:
        print_value(
            label,
            "No timestamp column found",
        )
        return

    for table, column in candidates:
        row = connection.execute(
            f"""
            SELECT
                MIN({column}) AS oldest,
                MAX({column}) AS newest,
                COUNT({column}) AS populated
            FROM {table}
            WHERE {column} IS NOT NULL
            """
        ).fetchone()

        print_value(
            f"{label} ({table}.{column})",
            f"{row['populated']:,} timestamps",
        )
        print_value(
            "  Oldest",
            format_timestamp(row["oldest"]),
        )
        print_value(
            "  Newest",
            format_timestamp(row["newest"]),
        )


def audit_database(database_path):
    errors = []
    warnings = []

    connection = open_read_only(database_path)

    try:
        tables = table_names(connection)

        print("Steam Backlog DB - Database Audit")
        print("=" * 33)
        print(f"Database: {database_path.expanduser().resolve()}")

        print_heading("SQLite integrity")

        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()

        integrity_messages = [row[0] for row in integrity_rows]

        if integrity_messages == ["ok"]:
            print_value("Integrity check", "PASS")
        else:
            print_value("Integrity check", "FAIL")
            errors.extend(
                f"SQLite integrity: {message}" for message in integrity_messages
            )

        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()

        print_count(
            "Foreign-key violations",
            len(foreign_key_rows),
        )

        if foreign_key_rows:
            errors.append(f"{len(foreign_key_rows)} foreign-key violation(s)")

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

        missing_tables = sorted(required_tables - tables)

        if missing_tables:
            errors.append("Missing expected table(s): " + ", ".join(missing_tables))

        if "games" not in tables:
            print()
            print("Cannot continue: games table is missing.")
            return errors, warnings

        game_columns = table_columns(
            connection,
            "games",
        )

        print_heading("Library")

        total_games = (
            scalar(
                connection,
                "SELECT COUNT(*) FROM games",
            )
            or 0
        )

        print_count(
            "Library entries",
            total_games,
        )

        classification_rows = connection.execute(
            """
            SELECT steam_type, COUNT(*) AS count
            FROM games
            GROUP BY steam_type
            ORDER BY count DESC, steam_type
            """
        ).fetchall()

        classification_counts = {
            row["steam_type"]: row["count"] for row in classification_rows
        }

        for steam_type in (
            "game",
            "software",
            "dlc",
            "video",
            "hardware",
            "unknown",
        ):
            print_count(
                f"Steam type: {steam_type}",
                classification_counts.get(steam_type, 0),
            )

        invalid_types = sorted(
            steam_type
            for steam_type in classification_counts
            if steam_type not in VALID_STEAM_TYPES
        )

        if invalid_types:
            errors.append(
                "Invalid steam_type value(s): "
                + ", ".join(repr(value) for value in invalid_types)
            )

        if "classification_updated_at" in game_columns:
            classified = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM games
                WHERE classification_updated_at IS NOT NULL
                """,
                )
                or 0
            )

            print_count(
                "Classification checked",
                classified,
            )
            print_count(
                "Classification pending",
                total_games - classified,
            )

            if total_games and classified < total_games:
                warnings.append(
                    f"{total_games - classified} library entries have no classification timestamp"
                )

        if "playtime_minutes" in game_columns:
            print_count(
                "Never played",
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM games WHERE playtime_minutes = 0",
                )
                or 0,
            )
            print_count(
                "Played at least once",
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM games WHERE playtime_minutes > 0",
                )
                or 0,
            )
            print_count(
                "Played 50+ hours",
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM games WHERE playtime_minutes >= 3000",
                )
                or 0,
            )

        if "manual_status" in game_columns:
            print_heading("Manual status")

            status_rows = connection.execute(
                """
                SELECT
                    COALESCE(manual_status, '<NULL>') AS status,
                    COUNT(*) AS count
                FROM games
                GROUP BY manual_status
                ORDER BY count DESC, status
                """
            ).fetchall()

            for row in status_rows:
                print_count(
                    row["status"],
                    row["count"],
                )

        print_heading("Maintenance coverage")

        coverage_columns = (
            ("metadata_checked", "Metadata checked"),
            ("hltb_checked", "HLTB checked"),
            ("achievements_checked", "Achievements checked"),
        )

        for column, label in coverage_columns:
            if column not in game_columns:
                print_value(
                    label,
                    "Column not present",
                )
                warnings.append(f"games.{column} is not present")
                continue

            checked = (
                scalar(
                    connection,
                    f"""
                SELECT COUNT(*)
                FROM games
                WHERE {column} = 1
                """,
                )
                or 0
            )

            print_value(
                label,
                f"{checked:,} / {total_games:,}",
            )

        print_heading("Refresh timestamps")

        print_timestamp_summary(
            connection,
            "classification",
            "Classification",
        )
        print_timestamp_summary(
            connection,
            "metadata",
            "Metadata",
        )
        print_timestamp_summary(
            connection,
            "hltb",
            "HLTB",
        )
        print_timestamp_summary(
            connection,
            "achievement",
            "Achievements",
        )

        print_heading("HLTB")

        if {
            "hltb_checked",
            "hltb_match_status",
        }.issubset(game_columns):
            hltb_rows = connection.execute(
                """
                SELECT
                    COALESCE(hltb_match_status, '<none>') AS status,
                    COUNT(*) AS count
                FROM games
                WHERE hltb_checked = 1
                GROUP BY COALESCE(hltb_match_status, '<none>')
                ORDER BY count DESC, status
                """
            ).fetchall()

            for row in hltb_rows:
                print_count(
                    f"Checked status: {row['status']}",
                    row["count"],
                )

            pending_hltb = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM games
                WHERE hltb_checked = 0
                """,
                )
                or 0
            )

            print_count(
                "Never checked / pending",
                pending_hltb,
            )

            review_count = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM games
                WHERE hltb_match_status = 'review'
                """,
                )
                or 0
            )

            if review_count:
                warnings.append(f"{review_count} HLTB match(es) still need review")

        if "hltb_candidates" in tables:
            orphan_candidates = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM hltb_candidates AS candidate
                LEFT JOIN games AS game
                    ON game.app_id = candidate.app_id
                WHERE game.app_id IS NULL
                """,
                )
                or 0
            )

            print_count(
                "Orphan HLTB candidates",
                orphan_candidates,
            )

            if orphan_candidates:
                errors.append(f"{orphan_candidates} orphan HLTB candidate row(s)")

            candidate_status_mismatch = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM hltb_candidates AS candidate
                JOIN games AS game
                    ON game.app_id = candidate.app_id
                WHERE COALESCE(game.hltb_match_status, '') != 'review'
                """,
                )
                or 0
            )

            print_count(
                "Candidates outside review state",
                candidate_status_mismatch,
            )

            if candidate_status_mismatch:
                warnings.append(
                    f"{candidate_status_mismatch} HLTB candidate row(s) belong to games not in review state"
                )

        print_heading("Achievements")

        achievement_required = {
            "achievement_total",
            "achievements_unlocked",
        }

        if achievement_required.issubset(game_columns):
            invalid_achievement_rows = (
                scalar(
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
                or 0
            )

            print_count(
                "Invalid achievement totals",
                invalid_achievement_rows,
            )

            if invalid_achievement_rows:
                errors.append(
                    f"{invalid_achievement_rows} game(s) have invalid achievement totals"
                )

        changed_since_check = 0

        if {
            "achievements_checked",
            "playtime_minutes",
            "achievements_playtime_minutes",
        }.issubset(game_columns):
            changed_since_check = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM games
                WHERE achievements_checked = 1
                  AND achievements_playtime_minutes IS NOT NULL
                  AND playtime_minutes > achievements_playtime_minutes
                """,
                )
                or 0
            )

            print_count(
                "Playtime changed since check",
                changed_since_check,
            )

            if changed_since_check:
                warnings.append(
                    f"{changed_since_check} game(s) are eligible for Refresh Changed"
                )

        print_heading("Metadata coverage")

        if {"game_genres", "genres"}.issubset(tables):
            print_count(
                "Games with genres",
                scalar(
                    connection,
                    "SELECT COUNT(DISTINCT app_id) FROM game_genres",
                )
                or 0,
            )
            print_count(
                "Genre assignments",
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM game_genres",
                )
                or 0,
            )

        if {"game_tags", "tags"}.issubset(tables):
            print_count(
                "Games with tags",
                scalar(
                    connection,
                    "SELECT COUNT(DISTINCT app_id) FROM game_tags",
                )
                or 0,
            )
            print_count(
                "Tag assignments",
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM game_tags",
                )
                or 0,
            )

        print_heading("Genre / tag integrity")

        checks = [
            (
                "Orphan game_genres rows",
                """
                SELECT COUNT(*)
                FROM game_genres AS mapping
                LEFT JOIN games AS game
                    ON game.app_id = mapping.app_id
                LEFT JOIN genres AS genre
                    ON genre.genre_id = mapping.genre_id
                WHERE game.app_id IS NULL
                   OR genre.genre_id IS NULL
                """,
            ),
            (
                "Orphan game_tags rows",
                """
                SELECT COUNT(*)
                FROM game_tags AS mapping
                LEFT JOIN games AS game
                    ON game.app_id = mapping.app_id
                LEFT JOIN tags AS tag
                    ON tag.tag_id = mapping.tag_id
                WHERE game.app_id IS NULL
                   OR tag.tag_id IS NULL
                """,
            ),
        ]

        for label, query in checks:
            if ("game_genres" in query and "game_genres" not in tables) or (
                "game_tags" in query and "game_tags" not in tables
            ):
                continue

            count = (
                scalar(
                    connection,
                    query,
                )
                or 0
            )

            print_count(
                label,
                count,
            )

            if count:
                errors.append(f"{count} {label.lower()}")

        if "metadata_checked" in game_columns:
            checked_without_genres_or_tags = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM games AS game
                WHERE game.metadata_checked = 1
                  AND NOT EXISTS (
                      SELECT 1
                      FROM game_genres AS gg
                      WHERE gg.app_id = game.app_id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM game_tags AS gt
                      WHERE gt.app_id = game.app_id
                  )
                """,
                )
                or 0
            )

            print_count(
                "Checked with no genres/tags",
                checked_without_genres_or_tags,
            )

            if checked_without_genres_or_tags:
                warnings.append(
                    f"{checked_without_genres_or_tags} metadata-checked game(s) have no stored genres or tags"
                )

        print_heading("Ratings / recommendations")

        if "game_ratings" in tables:
            rating_count = (
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM game_ratings",
                )
                or 0
            )

            orphan_ratings = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM game_ratings AS rating
                LEFT JOIN games AS game
                    ON game.app_id = rating.app_id
                WHERE game.app_id IS NULL
                """,
                )
                or 0
            )

            print_count(
                "Ratings",
                rating_count,
            )
            print_count(
                "Orphan ratings",
                orphan_ratings,
            )

            if orphan_ratings:
                errors.append(f"{orphan_ratings} rating row(s) reference missing games")

        if "recommendation_state" in tables:
            state_count = (
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM recommendation_state",
                )
                or 0
            )

            print_count(
                "Recommendation state rows",
                state_count,
            )

            if state_count > 1:
                errors.append("recommendation_state contains more than one row")

        if "game_recommendations" in tables:
            recommendation_count = (
                scalar(
                    connection,
                    "SELECT COUNT(*) FROM game_recommendations",
                )
                or 0
            )

            orphan_recommendations = (
                scalar(
                    connection,
                    """
                SELECT COUNT(*)
                FROM game_recommendations AS recommendation
                LEFT JOIN games AS game
                    ON game.app_id = recommendation.app_id
                WHERE game.app_id IS NULL
                """,
                )
                or 0
            )

            print_count(
                "Saved recommendations",
                recommendation_count,
            )
            print_count(
                "Orphan recommendations",
                orphan_recommendations,
            )

            if orphan_recommendations:
                errors.append(
                    f"{orphan_recommendations} recommendation row(s) reference missing games"
                )

            if recommendation_count and "recommendation_state" in tables:
                state_count = (
                    scalar(
                        connection,
                        "SELECT COUNT(*) FROM recommendation_state",
                    )
                    or 0
                )

                if state_count == 0:
                    warnings.append(
                        "Saved recommendations exist without recommendation_state"
                    )

        print_heading("Result")

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

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only structural, maintenance, and persistence audit "
            "for the Steam Backlog DB database."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_FILE,
        help=(
            "Path to steam_backlog.db. Defaults to the application's "
            "configured database path."
        ),
    )

    args = parser.parse_args()

    try:
        errors, _warnings = audit_database(
            args.db,
        )
    except (FileNotFoundError, sqlite3.Error) as error:
        print(f"Audit could not run: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
