import sqlite3
from pathlib import Path
from game import Game

# SteamLibraryData/data/steam_backlog.db
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_FILE = PROJECT_ROOT / "data" / "steam_backlog.db"

def get_connection():
    DB_FILE.parent.mkdir(exist_ok=True)

    connection = sqlite3.connect(DB_FILE)
    connection.execute("PRAGMA foreign_keys = ON")

    return connection

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

                metadata_checked INTEGER NOT NULL DEFAULT 0,

                hltb_main REAL,
                hltb_main_extra REAL,
                hltb_completionist REAL,
                hltb_all_styles REAL,
                hltb_match_name TEXT,
                hltb_similarity REAL,
                hltb_checked INTEGER NOT NULL DEFAULT 0,

                achievement_total INTEGER,
                achievements_unlocked INTEGER,
                achievements_checked INTEGER NOT NULL DEFAULT 0,

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
        """)

        ensure_game_columns(connection)

def save_game(game):
    with get_connection() as connection:
        connection.execute("""
            --sql
            INSERT INTO games (
                app_id,
                name,
                playtime_minutes,
                playtime_2weeks_minutes,
                last_played_timestamp,
                metadata_checked,
                hltb_main,
                hltb_main_extra,
                hltb_completionist,
                hltb_all_styles,
                hltb_match_name,
                hltb_similarity,
                hltb_checked,
                achievement_total,
                achievements_unlocked,
                achievements_checked,
                manual_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_id) DO UPDATE SET
                name = excluded.name,
                playtime_minutes = excluded.playtime_minutes,
                playtime_2weeks_minutes = excluded.playtime_2weeks_minutes,
                last_played_timestamp = excluded.last_played_timestamp,
                metadata_checked = excluded.metadata_checked,
                hltb_main = excluded.hltb_main,
                hltb_main_extra = excluded.hltb_main_extra,
                hltb_completionist = excluded.hltb_completionist,
                hltb_all_styles = excluded.hltb_all_styles,
                hltb_match_name = excluded.hltb_match_name,
                hltb_similarity = excluded.hltb_similarity,
                hltb_checked = excluded.hltb_checked,
                achievement_total = excluded.achievement_total,
                achievements_unlocked = excluded.achievements_unlocked,
                achievements_checked = excluded.achievements_checked,
                manual_status = excluded.manual_status
        """, (
            game.app_id,
            game.name,
            game.playtime_minutes,
            game.playtime_2weeks_minutes,
            game.last_played_timestamp,
            int(game.metadata_checked),
            game.hltb_main,
            game.hltb_main_extra,
            game.hltb_completionist,
            game.hltb_all_styles,
            game.hltb_match_name,
            game.hltb_similarity,
            int(game.hltb_checked),
            game.achievement_total,
            game.achievements_unlocked,
            int(game.achievements_checked),
            game.manual_status
        ))

        connection.execute("DELETE FROM game_genres WHERE app_id = ?", (game.app_id,))

        for genre in game.genres:
            connection.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (genre,))

            genre_id = connection.execute(
                "SELECT genre_id FROM genres WHERE name = ?",
                (genre,)
            ).fetchone()[0]

            connection.execute(
                "INSERT OR IGNORE INTO game_genres (app_id, genre_id) VALUES (?, ?)",
                (game.app_id, genre_id)
            )

        connection.execute("DELETE FROM game_tags WHERE app_id = ?", (game.app_id,))

        for tag, weight in game.tags.items():
            connection.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))

            tag_id = connection.execute(
                "SELECT tag_id FROM tags WHERE name = ?",
                (tag,)
            ).fetchone()[0]

            connection.execute(
                "INSERT OR REPLACE INTO game_tags (app_id, tag_id, weight) VALUES (?, ?, ?)",
                (game.app_id, tag_id, weight)
            )

def load_games():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT
                app_id,
                name,
                playtime_minutes,
                playtime_2weeks_minutes,
                last_played_timestamp,
                metadata_checked,
                hltb_main,
                hltb_main_extra,
                hltb_completionist,
                hltb_all_styles,
                hltb_match_name,
                hltb_similarity,
                hltb_checked,
                achievement_total,
                achievements_unlocked,
                achievements_checked,
                manual_status
            FROM games
        """).fetchall()

        games = []

        for row in rows:
            app_id = row[0]

            genre_rows = connection.execute("""
                SELECT genres.name
                FROM genres
                JOIN game_genres ON genres.genre_id = game_genres.genre_id
                WHERE game_genres.app_id = ?
            """, (app_id,)).fetchall()

            tag_rows = connection.execute("""
                SELECT tags.name, game_tags.weight
                FROM tags
                JOIN game_tags ON tags.tag_id = game_tags.tag_id
                WHERE game_tags.app_id = ?
            """, (app_id,)).fetchall()

            genres = [genre[0] for genre in genre_rows]
            tags = {tag[0]: tag[1] for tag in tag_rows}

            game = Game(
                app_id = row[0],
                name = row[1],
                playtime_minutes = row[2],
                playtime_2weeks_minutes = row[3],
                last_played_timestamp = row[4],
                metadata_checked = bool(row[5]),
                hltb_main = row[6],
                hltb_main_extra = row[7],
                hltb_completionist = row[8],
                hltb_all_styles = row[9],
                hltb_match_name = row[10],
                hltb_similarity = row[11],
                hltb_checked = bool(row[12]),
                achievement_total = row[13],
                achievements_unlocked = row[14],
                achievements_checked = bool(row[15]),
                genres = genres,
                tags = tags,
                manual_status = row[16],
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
            raise ValueError("This database already belongs to a different Steam account.")

        connection.execute(
            "INSERT OR IGNORE INTO database_info (id, steam_id) VALUES (1, ?)",
            (steam_id,)
        )

def delete_database():
    files = [
        DB_FILE,
        Path(f"{DB_FILE}-journal"),
        Path(f"{DB_FILE}-wal"),
        Path(f"{DB_FILE}-shm")
    ]

    for file in files:
        if file.exists():
            file.unlink()

def delete_games_not_in(app_ids):
    app_ids = set(app_ids)

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT app_id FROM games"
        ).fetchall()

        for row in rows:
            app_id = row[0]

            if app_id not in app_ids:
                connection.execute(
                    "DELETE FROM games WHERE app_id = ?",
                    (app_id,)
                )
                
def ensure_game_columns(conn):
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(games)").fetchall()
    }

    if "playtime_2weeks_minutes" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN playtime_2weeks_minutes INTEGER NOT NULL DEFAULT 0"
        )

    if "last_played_timestamp" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN last_played_timestamp INTEGER NOT NULL DEFAULT 0"
        )

    if "manual_status" not in columns:
        conn.execute(
            "ALTER TABLE games ADD COLUMN manual_status TEXT DEFAULT NULL"
        )