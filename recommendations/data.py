from dataclasses import dataclass, field

from storage.database import get_connection


@dataclass
class RecommendationGameData:
    app_id: int
    name: str

    playtime_minutes: int
    playtime_2weeks_minutes: int
    last_played_timestamp: int

    manual_status: str | None
    rating: int | None

    metadata_checked: bool
    steamspy_positive: int | None = None
    steamspy_negative: int | None = None
    genres: list[str] = field(default_factory=list)
    tags: dict[str, int] = field(default_factory=dict)

    hltb_main: float | None = None
    hltb_main_extra: float | None = None
    hltb_completionist: float | None = None
    hltb_all_styles: float | None = None
    hltb_checked: bool = False
    hltb_match_status: str | None = None

    achievement_total: int | None = None
    achievements_unlocked: int | None = None
    achievements_checked: bool = False


def load_recommendation_games():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                g.app_id,
                g.name,
                g.playtime_minutes,
                g.playtime_2weeks_minutes,
                g.last_played_timestamp,
                g.manual_status,
                r.rating,
                g.metadata_checked,
                g.steamspy_positive,
                g.steamspy_negative,
                g.hltb_main,
                g.hltb_main_extra,
                g.hltb_completionist,
                g.hltb_all_styles,
                g.hltb_checked,
                g.hltb_match_status,
                g.achievement_total,
                g.achievements_unlocked,
                g.achievements_checked
            FROM games g
            LEFT JOIN game_ratings r
                ON r.app_id = g.app_id
            WHERE g.steam_type = 'game'
            ORDER BY g.app_id
            """
        ).fetchall()

        games = {}

        for row in rows:
            game = RecommendationGameData(
                app_id=row[0],
                name=row[1],
                playtime_minutes=row[2],
                playtime_2weeks_minutes=row[3],
                last_played_timestamp=row[4],
                manual_status=row[5],
                rating=row[6],
                metadata_checked=bool(row[7]),
                steamspy_positive=row[8],
                steamspy_negative=row[9],
                hltb_main=row[10],
                hltb_main_extra=row[11],
                hltb_completionist=row[12],
                hltb_all_styles=row[13],
                hltb_checked=bool(row[14]),
                hltb_match_status=row[15],
                achievement_total=row[16],
                achievements_unlocked=row[17],
                achievements_checked=bool(row[18]),
            )

            games[game.app_id] = game

        genre_rows = connection.execute(
            """
            SELECT
                game_genres.app_id,
                genres.name
            FROM game_genres
            JOIN genres
                ON genres.genre_id = game_genres.genre_id
            JOIN games
                ON games.app_id = game_genres.app_id
            WHERE games.steam_type = 'game'
            ORDER BY game_genres.app_id, genres.name
            """
        ).fetchall()

        for app_id, genre in genre_rows:
            game = games.get(app_id)

            if game is not None:
                game.genres.append(genre)

        tag_rows = connection.execute(
            """
            SELECT
                game_tags.app_id,
                tags.name,
                game_tags.weight
            FROM game_tags
            JOIN tags
                ON tags.tag_id = game_tags.tag_id
            JOIN games
                ON games.app_id = game_tags.app_id
            WHERE games.steam_type = 'game'
            ORDER BY game_tags.app_id, tags.name
            """
        ).fetchall()

        for app_id, tag, weight in tag_rows:
            game = games.get(app_id)

            if game is not None:
                game.tags[tag] = weight

    return list(games.values())
