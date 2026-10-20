import storage.database as database
from recommendations.data import load_recommendation_games


def setup_test_database(tmp_path, monkeypatch):
    # Redirect all database operations to a disposable test database.
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_FILE", test_db)
    database.initialize_database()


def test_recommendation_data_loads_game_metadata_and_rating(
    tmp_path,
    monkeypatch,
):
    # ARRANGE:
    # Create a clean test database.
    setup_test_database(tmp_path, monkeypatch)

    with database.get_connection() as connection:
        # Add one confirmed Steam game.
        connection.execute(
            """
            INSERT INTO games (
                app_id,
                name,
                steam_type,
                playtime_minutes
            )
            VALUES (?, ?, ?, ?)
            """,
            (123, "Test RPG", "game", 600),
        )

        # Add a genre.
        connection.execute(
            "INSERT INTO genres (name) VALUES (?)",
            ("RPG",),
        )

        genre_id = connection.execute(
            "SELECT genre_id FROM genres WHERE name = ?",
            ("RPG",),
        ).fetchone()[0]

        connection.execute(
            """
            INSERT INTO game_genres (app_id, genre_id)
            VALUES (?, ?)
            """,
            (123, genre_id),
        )

        # Add a SteamSpy-style weighted tag.
        connection.execute(
            "INSERT INTO tags (name) VALUES (?)",
            ("Story Rich",),
        )

        tag_id = connection.execute(
            "SELECT tag_id FROM tags WHERE name = ?",
            ("Story Rich",),
        ).fetchone()[0]

        connection.execute(
            """
            INSERT INTO game_tags (
                app_id,
                tag_id,
                weight
            )
            VALUES (?, ?, ?)
            """,
            (123, tag_id, 250),
        )

    # Add the user's personal rating through the real production function.
    database.set_game_rating(123, 5)

    # ACT:
    # Build the recommendation dataset.
    games = load_recommendation_games()

    # ASSERT:
    # We should get exactly the game we inserted.
    assert len(games) == 1

    game = games[0]

    assert game.app_id == 123
    assert game.name == "Test RPG"
    assert game.playtime_minutes == 600

    # Personal preference data should be present.
    assert game.rating == 5

    # Content features should also be present.
    assert game.genres == ["RPG"]
    assert game.tags == {"Story Rich": 250}
