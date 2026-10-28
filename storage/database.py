import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from game import Game
from storage.paths import DB_FILE


@contextmanager
def get_connection():
    connection = sqlite3.connect(DB_FILE)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with get_connection() as connection:
        connection.executescript("""
            --sql
            CREATE TABLE IF NOT EXISTS database_info (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                steam_id TEXT NOT NULL
            );

            --sql
            CREATE TABLE IF NOT EXISTS games (
                app_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                playtime_minutes INTEGER NOT NULL DEFAULT 0,
                playtime_2weeks_minutes INTEGER NOT NULL DEFAULT 0,
                last_played_timestamp INTEGER NOT NULL DEFAULT 0,

                steam_type TEXT NOT NULL DEFAULT 'unknown',
                classification_updated_at INTEGER,

                metadata_checked INTEGER NOT NULL DEFAULT 0,
                metadata_updated_at INTEGER,
                steamspy_positive INTEGER,
                steamspy_negative INTEGER,
                steam_short_description TEXT,

                hltb_main REAL,
                hltb_main_extra REAL,
                hltb_completionist REAL,
                hltb_all_styles REAL,
                hltb_match_name TEXT,
                hltb_similarity REAL,
                hltb_game_id INTEGER,
                hltb_web_link TEXT,
                hltb_match_status TEXT,
                hltb_checked INTEGER NOT NULL DEFAULT 0,
                hltb_updated_at INTEGER,

                achievement_total INTEGER,
                achievements_unlocked INTEGER,
                achievements_checked INTEGER NOT NULL DEFAULT 0,
                achievements_updated_at INTEGER,
                achievements_playtime_minutes INTEGER,

                manual_status TEXT DEFAULT NULL
            );

            --sql
            CREATE TABLE IF NOT EXISTS genres (
                genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            --sql
            CREATE TABLE IF NOT EXISTS game_genres (
                app_id INTEGER NOT NULL,
                genre_id INTEGER NOT NULL,

                PRIMARY KEY (app_id, genre_id),

                FOREIGN KEY (app_id)
                    REFERENCES games(app_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (genre_id)
                    REFERENCES genres(genre_id)
                    ON DELETE CASCADE
            );

            --sql
            CREATE TABLE IF NOT EXISTS tags (
                tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            
            --sql
            CREATE TABLE IF NOT EXISTS game_tags (
                app_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                weight INTEGER NOT NULL DEFAULT 0,

                PRIMARY KEY (app_id, tag_id),

                FOREIGN KEY (app_id)
                    REFERENCES games(app_id)
                    ON DELETE CASCADE,

                FOREIGN KEY (tag_id)
                    REFERENCES tags(tag_id)
                    ON DELETE CASCADE
            );

            --sql
            CREATE TABLE IF NOT EXISTS hltb_candidates (
                app_id INTEGER NOT NULL,
                hltb_game_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                game_web_link TEXT,
                main_story REAL,
                main_extra REAL,
                completionist REAL,
                all_styles REAL,
                similarity REAL,
                search_query TEXT,

                PRIMARY KEY (app_id, hltb_game_id),

                FOREIGN KEY (app_id)
                    REFERENCES games(app_id)
                    ON DELETE CASCADE
            );
        """)

        ensure_game_columns(connection)
        ensure_recommendation_tables(connection)
        reset_empty_hltb_checks()


def save_game(game):
    with get_connection() as connection:
        connection.execute(
            """
            --sql
            INSERT INTO games (
                app_id,
                name,
                playtime_minutes,
                playtime_2weeks_minutes,
                last_played_timestamp,
                steam_type,
                classification_updated_at,
                metadata_checked,
                steamspy_positive,
                steamspy_negative,
                hltb_main,
                hltb_main_extra,
                hltb_completionist,
                hltb_all_styles,
                hltb_match_name,
                hltb_similarity,
                hltb_game_id,
                hltb_web_link,
                hltb_match_status,
                hltb_checked,
                achievement_total,
                achievements_unlocked,
                achievements_checked,
                achievements_updated_at,
                achievements_playtime_minutes,
                manual_status,
                metadata_updated_at,
                hltb_updated_at,
                steam_short_description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_id) DO UPDATE SET
                name = excluded.name,
                playtime_minutes = excluded.playtime_minutes,
                playtime_2weeks_minutes = excluded.playtime_2weeks_minutes,
                last_played_timestamp = excluded.last_played_timestamp,
                steam_type = excluded.steam_type,
                classification_updated_at = excluded.classification_updated_at,
                metadata_checked = excluded.metadata_checked,
                steamspy_positive = excluded.steamspy_positive,
                steamspy_negative = excluded.steamspy_negative,
                hltb_main = excluded.hltb_main,
                hltb_main_extra = excluded.hltb_main_extra,
                hltb_completionist = excluded.hltb_completionist,
                hltb_all_styles = excluded.hltb_all_styles,
                hltb_match_name = excluded.hltb_match_name,
                hltb_similarity = excluded.hltb_similarity,
                hltb_game_id = excluded.hltb_game_id,
                hltb_web_link = excluded.hltb_web_link,
                hltb_match_status = excluded.hltb_match_status,
                hltb_checked = excluded.hltb_checked,
                achievement_total = excluded.achievement_total,
                achievements_unlocked = excluded.achievements_unlocked,
                achievements_checked = excluded.achievements_checked,
                achievements_updated_at = excluded.achievements_updated_at,
                achievements_playtime_minutes = excluded.achievements_playtime_minutes,
                manual_status = excluded.manual_status,
                metadata_updated_at = excluded.metadata_updated_at,
                hltb_updated_at = excluded.hltb_updated_at,
                steam_short_description = excluded.steam_short_description
        """,
            (
                game.app_id,
                game.name,
                game.playtime_minutes,
                game.playtime_2weeks_minutes,
                game.last_played_timestamp,
                game.steam_type,
                game.classification_updated_at,
                int(game.metadata_checked),
                game.steamspy_positive,
                game.steamspy_negative,
                game.hltb_main,
                game.hltb_main_extra,
                game.hltb_completionist,
                game.hltb_all_styles,
                game.hltb_match_name,
                game.hltb_similarity,
                game.hltb_game_id,
                game.hltb_web_link,
                game.hltb_match_status,
                int(game.hltb_checked),
                game.achievement_total,
                game.achievements_unlocked,
                int(game.achievements_checked),
                game.achievements_updated_at,
                game.achievements_playtime_minutes,
                game.manual_status,
                game.metadata_updated_at,
                game.hltb_updated_at,
                game.steam_short_description,
            ),
        )

        connection.execute("DELETE FROM game_genres WHERE app_id = ?", (game.app_id,))

        for genre in game.genres:
            connection.execute(
                "INSERT OR IGNORE INTO genres (name) VALUES (?)", (genre,)
            )

            genre_id = connection.execute(
                "SELECT genre_id FROM genres WHERE name = ?", (genre,)
            ).fetchone()[0]

            connection.execute(
                "INSERT OR IGNORE INTO game_genres (app_id, genre_id) VALUES (?, ?)",
                (game.app_id, genre_id),
            )

        connection.execute("DELETE FROM game_tags WHERE app_id = ?", (game.app_id,))

        for tag, weight in game.tags.items():
            connection.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))

            tag_id = connection.execute(
                "SELECT tag_id FROM tags WHERE name = ?", (tag,)
            ).fetchone()[0]

            connection.execute(
                "INSERT OR REPLACE INTO game_tags (app_id, tag_id, weight) VALUES (?, ?, ?)",
                (game.app_id, tag_id, weight),
            )


def _require_game_row(cursor, game):
    if cursor.rowcount != 1:
        raise RuntimeError(f"Could not save AppID {game.app_id}: game not found.")


def save_library_fields(game):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE games
            SET
                name = ?,
                playtime_minutes = ?,
                playtime_2weeks_minutes = ?,
                last_played_timestamp = ?
            WHERE app_id = ?
            """,
            (
                game.name,
                game.playtime_minutes,
                game.playtime_2weeks_minutes,
                game.last_played_timestamp,
                game.app_id,
            ),
        )

        _require_game_row(cursor, game)


def save_hltb_data(game, candidates=None):
    if candidates is None:
        candidates = []

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE games
            SET
                hltb_main = ?,
                hltb_main_extra = ?,
                hltb_completionist = ?,
                hltb_all_styles = ?,
                hltb_match_name = ?,
                hltb_similarity = ?,
                hltb_game_id = ?,
                hltb_web_link = ?,
                hltb_match_status = ?,
                hltb_checked = ?,
                hltb_updated_at = ?
            WHERE app_id = ?
            """,
            (
                game.hltb_main,
                game.hltb_main_extra,
                game.hltb_completionist,
                game.hltb_all_styles,
                game.hltb_match_name,
                game.hltb_similarity,
                game.hltb_game_id,
                game.hltb_web_link,
                game.hltb_match_status,
                int(game.hltb_checked),
                game.hltb_updated_at,
                game.app_id,
            ),
        )

        _require_game_row(cursor, game)

        connection.execute(
            "DELETE FROM hltb_candidates WHERE app_id = ?",
            (game.app_id,),
        )

        if game.hltb_match_status != "review":
            return

        for candidate in candidates:
            game_id = candidate.get("game_id")

            if game_id is None:
                continue

            connection.execute(
                """
                INSERT INTO hltb_candidates (
                    app_id,
                    hltb_game_id,
                    game_name,
                    game_web_link,
                    main_story,
                    main_extra,
                    completionist,
                    all_styles,
                    similarity,
                    search_query
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game.app_id,
                    game_id,
                    candidate["game_name"],
                    candidate.get("game_web_link"),
                    candidate.get("main_story"),
                    candidate.get("main_extra"),
                    candidate.get("completionist"),
                    candidate.get("all_styles"),
                    candidate.get("similarity"),
                    candidate.get("search_query"),
                ),
            )


def save_steam_short_description(app_id, description):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            --sql
            UPDATE games
            SET steam_short_description = ?
            WHERE app_id = ?
            """,
            (description, app_id),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Could not save Steam description for AppID {app_id}: game not found."
            )


def save_metadata_data(game):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE games
            SET
                metadata_checked = ?,
                metadata_updated_at = ?,
                steamspy_positive = ?,
                steamspy_negative = ?
            WHERE app_id = ?
            """,
            (
                int(game.metadata_checked),
                game.metadata_updated_at,
                game.steamspy_positive,
                game.steamspy_negative,
                game.app_id,
            ),
        )

        _require_game_row(cursor, game)

        connection.execute(
            "DELETE FROM game_genres WHERE app_id = ?",
            (game.app_id,),
        )

        for genre in game.genres:
            connection.execute(
                "INSERT OR IGNORE INTO genres (name) VALUES (?)",
                (genre,),
            )

            genre_id = connection.execute(
                "SELECT genre_id FROM genres WHERE name = ?",
                (genre,),
            ).fetchone()[0]

            connection.execute(
                "INSERT OR IGNORE INTO game_genres (app_id, genre_id) VALUES (?, ?)",
                (
                    game.app_id,
                    genre_id,
                ),
            )

        connection.execute(
            "DELETE FROM game_tags WHERE app_id = ?",
            (game.app_id,),
        )

        for tag, weight in game.tags.items():
            connection.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)",
                (tag,),
            )

            tag_id = connection.execute(
                "SELECT tag_id FROM tags WHERE name = ?",
                (tag,),
            ).fetchone()[0]

            connection.execute(
                "INSERT OR REPLACE INTO game_tags (app_id, tag_id, weight) VALUES (?, ?, ?)",
                (
                    game.app_id,
                    tag_id,
                    weight,
                ),
            )


def save_achievement_data(game):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE games
            SET
                achievement_total = ?,
                achievements_unlocked = ?,
                achievements_checked = ?,
                achievements_updated_at = ?,
                achievements_playtime_minutes = ?
            WHERE app_id = ?
            """,
            (
                game.achievement_total,
                game.achievements_unlocked,
                int(game.achievements_checked),
                game.achievements_updated_at,
                game.achievements_playtime_minutes,
                game.app_id,
            ),
        )

        _require_game_row(cursor, game)


def save_manual_status(game):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE games
            SET manual_status = ?
            WHERE app_id = ?
            """,
            (
                game.manual_status,
                game.app_id,
            ),
        )

        _require_game_row(cursor, game)


def save_steam_classifications(classifications):
    if not classifications:
        return None

    valid_types = {
        "game",
        "software",
        "dlc",
        "video",
        "hardware",
        "test",
        "unknown",
    }

    for app_id, steam_type in classifications.items():
        if not isinstance(app_id, int) or app_id <= 0:
            raise ValueError(
                f"Invalid Steam App ID in classification results: {app_id!r}"
            )

        if steam_type not in valid_types:
            raise ValueError(
                f"Invalid Steam classification for AppID {app_id}: {steam_type!r}"
            )

    updated_at = int(time.time())

    with get_connection() as connection:
        for app_id, steam_type in classifications.items():
            cursor = connection.execute(
                """
                UPDATE games
                SET
                    steam_type = ?,
                    classification_updated_at = ?
                WHERE app_id = ?
                """,
                (
                    steam_type,
                    updated_at,
                    app_id,
                ),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Could not save Steam classification "
                    f"for AppID {app_id}: game not found."
                )

    return updated_at


def load_games():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT
                app_id,
                name,
                playtime_minutes,
                playtime_2weeks_minutes,
                last_played_timestamp,
                steam_type,
                classification_updated_at,
                metadata_checked,
                steamspy_positive,
                steamspy_negative,
                hltb_main,
                hltb_main_extra,
                hltb_completionist,
                hltb_all_styles,
                hltb_match_name,
                hltb_similarity,
                hltb_game_id,
                hltb_web_link,
                hltb_match_status,
                hltb_checked,
                achievement_total,
                achievements_unlocked,
                achievements_checked,
                achievements_updated_at,
                achievements_playtime_minutes,
                manual_status,
                metadata_updated_at,
                hltb_updated_at,
                steam_short_description
            FROM games
        """).fetchall()

        games = []

        for row in rows:
            app_id = row[0]

            genre_rows = connection.execute(
                """
                SELECT genres.name
                FROM genres
                JOIN game_genres ON genres.genre_id = game_genres.genre_id
                WHERE game_genres.app_id = ?
            """,
                (app_id,),
            ).fetchall()

            tag_rows = connection.execute(
                """
                SELECT tags.name, game_tags.weight
                FROM tags
                JOIN game_tags ON tags.tag_id = game_tags.tag_id
                WHERE game_tags.app_id = ?
            """,
                (app_id,),
            ).fetchall()

            genres = [genre[0] for genre in genre_rows]
            tags = {tag[0]: tag[1] for tag in tag_rows}

            game = Game(
                app_id=row[0],
                name=row[1],
                playtime_minutes=row[2],
                playtime_2weeks_minutes=row[3],
                last_played_timestamp=row[4],
                steam_type=row[5],
                classification_updated_at=row[6],
                metadata_checked=bool(row[7]),
                steamspy_positive=row[8],
                steamspy_negative=row[9],
                hltb_main=row[10],
                hltb_main_extra=row[11],
                hltb_completionist=row[12],
                hltb_all_styles=row[13],
                hltb_match_name=row[14],
                hltb_similarity=row[15],
                hltb_game_id=row[16],
                hltb_web_link=row[17],
                hltb_match_status=row[18],
                hltb_checked=bool(row[19]),
                achievement_total=row[20],
                achievements_unlocked=row[21],
                achievements_checked=bool(row[22]),
                achievements_updated_at=row[23],
                achievements_playtime_minutes=row[24],
                genres=genres,
                tags=tags,
                manual_status=row[25],
                metadata_updated_at=row[26],
                hltb_updated_at=row[27],
                steam_short_description=row[28],
            )

            games.append(game)

        return games


def get_database_steam_id():
    with get_connection() as connection:
        row = connection.execute(
            "SELECT steam_id FROM database_info WHERE id = 1"
        ).fetchone()

    if row is None:
        return None

    return row[0]


def set_database_steam_id(steam_id):
    with get_connection() as connection:
        existing_steam_id = connection.execute(
            "SELECT steam_id FROM database_info WHERE id = 1"
        ).fetchone()

        if existing_steam_id is not None and existing_steam_id[0] != steam_id:
            raise ValueError(
                "This database already belongs to a different Steam account."
            )

        connection.execute(
            "INSERT OR IGNORE INTO database_info (id, steam_id) VALUES (1, ?)",
            (steam_id,),
        )


def delete_database():
    files = [
        DB_FILE,
        Path(f"{DB_FILE}-journal"),
        Path(f"{DB_FILE}-wal"),
        Path(f"{DB_FILE}-shm"),
    ]

    for file in files:
        if file.exists():
            file.unlink()


def delete_games_not_in(app_ids):
    app_ids = set(app_ids)

    with get_connection() as connection:
        rows = connection.execute("SELECT app_id FROM games").fetchall()

        for row in rows:
            app_id = row[0]

            if app_id not in app_ids:
                connection.execute("DELETE FROM games WHERE app_id = ?", (app_id,))


def ensure_recommendation_tables(connection):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS game_ratings (
            app_id INTEGER PRIMARY KEY,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recommendation_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            method TEXT NOT NULL,
            model_version INTEGER NOT NULL,
            feature_version INTEGER NOT NULL,
            generated_at INTEGER NOT NULL,
            training_game_count INTEGER NOT NULL,
            rated_game_count INTEGER NOT NULL,
            implicit_game_count INTEGER NOT NULL,
            candidate_game_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS game_recommendations (
            app_id INTEGER PRIMARY KEY,
            score REAL NOT NULL,
            match_tier TEXT,
            explanation_json TEXT,
            generated_at INTEGER NOT NULL,

            FOREIGN KEY (app_id)
                REFERENCES games(app_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_game_recommendations_score
        ON game_recommendations(score DESC);
        """
    )


def ensure_game_columns(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}

    if "playtime_2weeks_minutes" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN playtime_2weeks_minutes INTEGER NOT NULL DEFAULT 0"
        )

    if "last_played_timestamp" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN last_played_timestamp INTEGER NOT NULL DEFAULT 0"
        )

    if "manual_status" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN manual_status TEXT DEFAULT NULL")

    if "hltb_game_id" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN hltb_game_id INTEGER")

    if "hltb_web_link" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN hltb_web_link TEXT")

    if "hltb_match_status" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN hltb_match_status TEXT")

    if "steam_type" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN steam_type TEXT NOT NULL DEFAULT 'unknown'"
        )

    if "classification_updated_at" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN classification_updated_at INTEGER")

    if "steamspy_positive" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN steamspy_positive INTEGER")

    if "steamspy_negative" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN steamspy_negative INTEGER")

    if "achievements_updated_at" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN achievements_updated_at INTEGER")

    if "achievements_playtime_minutes" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN achievements_playtime_minutes INTEGER"
        )

    if "metadata_updated_at" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN metadata_updated_at INTEGER")

    if "hltb_updated_at" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN hltb_updated_at INTEGER")

    if "steam_short_description" not in columns:
        conn.execute("ALTER TABLE games ADD COLUMN steam_short_description TEXT")


def reset_empty_hltb_checks():
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE games
            SET hltb_checked = 0
            WHERE hltb_checked = 1
              AND hltb_match_status IS NULL
              AND hltb_match_name IS NULL
              AND hltb_main IS NULL
              AND hltb_main_extra IS NULL
              AND hltb_completionist IS NULL
              AND hltb_all_styles IS NULL
            """
        )

        return cursor.rowcount


def load_hltb_candidates(app_id):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                hltb_game_id,
                game_name,
                game_web_link,
                main_story,
                main_extra,
                completionist,
                all_styles,
                similarity,
                search_query
            FROM hltb_candidates
            WHERE app_id = ?
            ORDER BY similarity DESC
            """,
            (app_id,),
        ).fetchall()

    return [
        {
            "game_id": row[0],
            "game_name": row[1],
            "game_web_link": row[2],
            "main_story": row[3],
            "main_extra": row[4],
            "completionist": row[5],
            "all_styles": row[6],
            "similarity": row[7],
            "search_query": row[8],
        }
        for row in rows
    ]


def get_game_rating(app_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT rating
            FROM game_ratings
            WHERE app_id = ?
            """,
            (app_id,),
        ).fetchone()

    if row is None:
        return None

    return row[0]


def set_game_rating(app_id, rating):
    rating = int(rating)

    if rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5.")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO game_ratings (
                app_id,
                rating,
                updated_at
            )
            VALUES (?, ?, CAST(strftime('%s', 'now') AS INTEGER))
            ON CONFLICT(app_id) DO UPDATE SET
                rating = excluded.rating,
                updated_at = excluded.updated_at
            """,
            (app_id, rating),
        )

        invalidate_recommendations(connection)


def clear_game_rating(app_id):
    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM game_ratings
            WHERE app_id = ?
            """,
            (app_id,),
        )

        invalidate_recommendations(connection)


def invalidate_recommendations(connection):
    connection.execute("DELETE FROM game_recommendations")
    connection.execute("DELETE FROM recommendation_state")


def load_game_ratings():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                app_id,
                rating
            FROM game_ratings
            """
        ).fetchall()

    return {app_id: rating for app_id, rating in rows}
