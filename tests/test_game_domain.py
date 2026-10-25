import pytest

from game import Game
from game_classification import GameClassifier, canonical_genre_name


def make_game(
    app_id,
    name,
    *,
    steam_type="unknown",
    metadata_checked=True,
    genres=None,
    tags=None,
):
    return Game(
        app_id=app_id,
        name=name,
        playtime_minutes=0,
        steam_type=steam_type,
        classification_updated_at=1,
        metadata_checked=metadata_checked,
        genres=list(genres or []),
        tags=dict(tags or {}),
    )


@pytest.mark.parametrize(
    ("name", "steam_type", "expected"),
    [
        ("Some Game Public Beta", "game", True),
        ("Some Game Test Server", "game", True),
        ("Magicka 2 Spell Balance Beta", "unknown", True),
        ("Skullgirls Endless Beta", "unknown", True),
        ("Some Game Playtest", "game", True),
        ("Released Game Beta", "game", False),
        ("Alpha Protocol", "unknown", False),
        ("Beta Protocol", "unknown", False),
        ("Beta", "unknown", False),
    ],
)
def test_test_build_detection_avoids_generic_alpha_beta_false_positives(
    name,
    steam_type,
    expected,
):
    game = Game(
        app_id=1,
        name=name,
        playtime_minutes=0,
        steam_type=steam_type,
    )

    assert game.is_test_build() is expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (
            {
                "manual_status": "Completed",
                "playtime_2weeks_minutes": 60,
            },
            "Completed",
        ),
        (
            {
                "manual_status": "Dropped",
                "achievement_total": 10,
                "achievements_unlocked": 10,
            },
            "Dropped",
        ),
        (
            {
                "manual_status": "On Hold",
                "playtime_2weeks_minutes": 60,
            },
            "On Hold",
        ),
        (
            {
                "achievement_total": 10,
                "achievements_unlocked": 10,
                "playtime_2weeks_minutes": 60,
            },
            "Completed",
        ),
        (
            {
                "playtime_minutes": 120,
                "playtime_2weeks_minutes": 30,
            },
            "Playing",
        ),
        (
            {
                "playtime_minutes": 0,
            },
            "Backlog",
        ),
        (
            {
                "playtime_minutes": 120,
            },
            "Inactive",
        ),
    ],
)
def test_effective_status_precedence(values, expected):
    values = dict(values)
    playtime_minutes = values.pop("playtime_minutes", 0)

    game = Game(
        app_id=1,
        name="Status Test",
        playtime_minutes=playtime_minutes,
        **values,
    )

    assert game.effective_status() == expected


def test_preferred_hltb_time_uses_most_complete_available_metric():
    game = Game(
        app_id=1,
        name="HLTB Test",
        playtime_minutes=0,
        hltb_main=10,
        hltb_main_extra=15,
        hltb_all_styles=18,
        hltb_completionist=25,
    )

    assert game.preferred_hltb_time() == 25

    game.hltb_completionist = None
    assert game.preferred_hltb_time() == 18

    game.hltb_all_styles = None
    assert game.preferred_hltb_time() == 15

    game.hltb_main_extra = None
    assert game.preferred_hltb_time() == 10


def test_hltb_review_requires_a_complete_confident_match():
    game = Game(
        app_id=1,
        name="HLTB Review",
        playtime_minutes=0,
    )

    assert not game.hltb_needs_review()

    game.hltb_checked = True
    assert game.hltb_needs_review()

    game.hltb_match_name = "Matched Game"
    assert game.hltb_needs_review()

    game.hltb_similarity = 0.79
    assert game.hltb_needs_review()

    game.hltb_similarity = 0.80
    assert not game.hltb_needs_review()


def test_game_keeps_store_description_field():
    game = Game(
        app_id=1,
        name="Description Test",
        playtime_minutes=0,
        steam_short_description="A short Steam description.",
    )

    assert game.steam_short_description == "A short Steam description."


def test_unknown_with_software_exclusive_genre_is_inferred_as_software():
    games = [
        make_game(
            1,
            "Known Game",
            steam_type="game",
            genres=["Action"],
        ),
        make_game(
            2,
            "Known Tool",
            steam_type="software",
            genres=["Utilities"],
        ),
        make_game(
            3,
            "Mystery Tool",
            genres=["Utilities"],
        ),
    ]

    classifier = GameClassifier(games)
    mystery = games[2]

    assert classifier.inferred_steam_type(mystery) == "software"
    assert classifier.display_steam_type(mystery) == "Unknown (Software)"
    assert not classifier.is_backlog_eligible(mystery)


def test_unknown_with_software_exclusive_tag_is_inferred_as_software():
    games = [
        make_game(
            1,
            "Known Game",
            steam_type="game",
            tags={"Singleplayer": 100},
        ),
        make_game(
            2,
            "Known Tool",
            steam_type="software",
            tags={"Utilities": 100},
        ),
        make_game(
            3,
            "Mystery Tool",
            tags={"Utilities": 50},
        ),
    ]

    classifier = GameClassifier(games)

    assert classifier.inferred_steam_type(games[2]) == "software"
    assert not classifier.is_backlog_eligible(games[2])


def test_feature_shared_by_game_and_software_is_not_software_exclusive():
    games = [
        make_game(
            1,
            "Known Game",
            steam_type="game",
            genres=["Utilities"],
        ),
        make_game(
            2,
            "Known Tool",
            steam_type="software",
            genres=["Utilities"],
        ),
        make_game(
            3,
            "Mystery Entry",
            genres=["Utilities"],
        ),
    ]

    classifier = GameClassifier(games)

    assert "utilities" not in classifier.software_exclusive_genre_keys
    assert classifier.inferred_steam_type(games[2]) == "game"
    assert classifier.display_steam_type(games[2]) == "Unknown (Game)"
    assert classifier.is_backlog_eligible(games[2])


def test_metadata_checked_unknown_without_software_evidence_becomes_game():
    game = make_game(
        1,
        "Mystery RPG",
        genres=["RPG"],
        tags={"Story Rich": 100},
    )

    classifier = GameClassifier([game])

    assert classifier.inferred_steam_type(game) == "game"
    assert classifier.display_steam_type(game) == "Unknown (Game)"
    assert classifier.is_backlog_eligible(game)


def test_unchecked_unknown_stays_unknown_and_remains_eligible():
    game = make_game(
        1,
        "Unchecked Entry",
        metadata_checked=False,
    )

    classifier = GameClassifier([game])

    assert classifier.inferred_steam_type(game) == "unknown"
    assert classifier.display_steam_type(game) == "Unknown"
    assert classifier.is_backlog_eligible(game)


@pytest.mark.parametrize(
    ("steam_type", "expected_label"),
    [
        ("software", "Software"),
        ("dlc", "DLC"),
        ("video", "Video"),
        ("hardware", "Hardware"),
    ],
)
def test_known_non_backlog_types_are_not_eligible(
    steam_type,
    expected_label,
):
    game = make_game(
        1,
        "Non-game Entry",
        steam_type=steam_type,
    )

    classifier = GameClassifier([game])

    assert classifier.inferred_steam_type(game) == steam_type
    assert classifier.display_steam_type(game) == expected_label
    assert not classifier.is_backlog_eligible(game)


def test_known_game_is_backlog_eligible():
    game = make_game(
        1,
        "Released Game",
        steam_type="game",
    )

    classifier = GameClassifier([game])

    assert classifier.inferred_steam_type(game) == "game"
    assert classifier.display_steam_type(game) == "Game"
    assert classifier.is_backlog_eligible(game)


@pytest.mark.parametrize(
    ("name", "steam_type", "expected_label"),
    [
        (
            "Some Game Public Beta",
            "game",
            "Test / Beta",
        ),
        (
            "Some Game Test Server",
            "game",
            "Test / Beta",
        ),
        (
            "Skullgirls Endless Beta",
            "unknown",
            "Unknown (Test / Beta)",
        ),
    ],
)
def test_test_builds_are_never_backlog_eligible(
    name,
    steam_type,
    expected_label,
):
    game = make_game(
        1,
        name,
        steam_type=steam_type,
    )

    classifier = GameClassifier([game])

    assert classifier.inferred_steam_type(game) == "test"
    assert classifier.display_steam_type(game) == expected_label
    assert not classifier.is_backlog_eligible(game)


def test_free_to_play_genre_is_canonicalized_consistently():
    assert canonical_genre_name("free to play") == "Free To Play"
    assert canonical_genre_name("  Free   To   Play  ") == "Free To Play"
