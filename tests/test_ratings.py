import pytest

import storage.database as database


def setup_test_database(tmp_path, monkeypatch):
    # pytest gives us a temporary folder through tmp_path.
    # This database exists only for this test run, so our real Steam database
    # in AppData can never be modified by these tests.
    test_db = tmp_path / "test.db"

    # storage.database normally points DB_FILE at the real application database.
    # monkeypatch temporarily replaces it with our test database.
    #
    # pytest automatically restores the original DB_FILE after the test ends.
    monkeypatch.setattr(database, "DB_FILE", test_db)

    # Create the normal SteamLibraryData database tables inside the temporary DB.
    # This means the tests use the same schema as the real application.
    database.initialize_database()


def test_rating_can_be_saved_and_loaded(tmp_path, monkeypatch):
    # ARRANGE:
    # Start with a clean temporary database.
    setup_test_database(tmp_path, monkeypatch)

    # ACT:
    # Give the fake Steam AppID 123 a 5-star rating.
    database.set_game_rating(123, 5)

    # ASSERT:
    # Reading the rating back should return exactly what we saved.
    assert database.get_game_rating(123) == 5


def test_rating_can_be_changed(tmp_path, monkeypatch):
    # Start with a clean temporary database.
    setup_test_database(tmp_path, monkeypatch)

    # Rate the game 2 stars first...
    database.set_game_rating(123, 2)

    # ...then change that same game's rating to 4 stars.
    # This tests the SQLite ON CONFLICT / UPDATE behavior.
    database.set_game_rating(123, 4)

    # There should now be a 4-star rating for AppID 123,
    # rather than the old 2-star value.
    assert database.get_game_rating(123) == 4


def test_rating_can_be_cleared(tmp_path, monkeypatch):
    # Start with a clean temporary database.
    setup_test_database(tmp_path, monkeypatch)

    # Give the game a rating so there is something to remove.
    database.set_game_rating(123, 5)

    # Remove the rating.
    database.clear_game_rating(123)

    # No rating row should remain, so get_game_rating() should return None.
    assert database.get_game_rating(123) is None


def test_rating_rejects_invalid_values(tmp_path, monkeypatch):
    # Start with a clean temporary database.
    setup_test_database(tmp_path, monkeypatch)

    # Ratings are only allowed to be between 1 and 5.
    #
    # pytest.raises means:
    # "The code inside this block is EXPECTED to raise ValueError."
    #
    # If it does, the test passes.
    # If it does not, pytest fails the test.
    with pytest.raises(ValueError):
        database.set_game_rating(123, 6)


def test_rating_survives_game_deletion(tmp_path, monkeypatch):
    # Start with a clean temporary database.
    setup_test_database(tmp_path, monkeypatch)

    # Add a fake game to the normal games table.
    with database.get_connection() as connection:
        connection.execute(
            """
            INSERT INTO games (app_id, name)
            VALUES (?, ?)
            """,
            (123, "Test Game"),
        )

    # Give that game a permanent personal rating.
    database.set_game_rating(123, 5)

    # Simulate a Steam library refresh where the game is no longer present.
    # An empty list means every current game gets removed from the games table.
    database.delete_games_not_in([])

    # The game itself should be gone...
    with database.get_connection() as connection:
        game = connection.execute(
            "SELECT app_id FROM games WHERE app_id = ?",
            (123,),
        ).fetchone()

    assert game is None

    # ...but the user's personal rating should still exist.
    assert database.get_game_rating(123) == 5
