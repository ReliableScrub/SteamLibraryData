import pytest

from game import Game
from ui.update_controller import UpdateController


def make_game(
    app_id,
    name,
    *,
    steam_type="game",
    metadata_checked=True,
    genres=None,
    tags=None,
    hltb_checked=False,
    achievements_checked=False,
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
        hltb_checked=hltb_checked,
        achievements_checked=achievements_checked,
    )


@pytest.fixture
def make_controller(qapp):
    controllers = []

    def factory(games):
        controller = UpdateController(
            games,
            "fake_api_key",
        )
        controllers.append(controller)

        return controller

    yield factory

    for controller in controllers:
        controller.deleteLater()

    qapp.processEvents()


def capture_batch(
    monkeypatch,
    controller,
):
    captured = {}

    def fake_start_batch(**kwargs):
        captured.update(kwargs)

        return "started"

    monkeypatch.setattr(
        controller,
        "_start_batch",
        fake_start_batch,
    )

    return captured


def mixed_library():
    return [
        make_game(
            1,
            "Eligible Game",
            steam_type="game",
        ),
        make_game(
            2,
            "Known Software",
            steam_type="software",
            genres=["Utilities"],
        ),
        make_game(
            3,
            "Unknown Tool",
            steam_type="unknown",
            genres=["Utilities"],
        ),
        make_game(
            4,
            "Some Game Test Server",
            steam_type="game",
        ),
        make_game(
            5,
            "Already Checked",
            steam_type="game",
            hltb_checked=True,
            achievements_checked=True,
        ),
    ]


def test_hltb_batch_only_selects_effective_backlog_games(
    make_controller,
    monkeypatch,
):
    controller = make_controller(mixed_library())
    captured = capture_batch(
        monkeypatch,
        controller,
    )

    assert controller.start_hltb_batch() == "started"
    assert captured["source"] == "hltb"
    assert [game.app_id for game in captured["games"]] == [1]


def test_achievement_batch_only_selects_effective_backlog_games(
    make_controller,
    monkeypatch,
):
    controller = make_controller(mixed_library())
    captured = capture_batch(
        monkeypatch,
        controller,
    )

    assert controller.start_achievement_batch("fake_steam_id") == "started"

    assert captured["source"] == "achievements"
    assert [game.app_id for game in captured["games"]] == [1]


def test_achievement_pending_count_uses_effective_backlog_eligibility(
    make_controller,
):
    controller = make_controller(mixed_library())

    assert controller.achievement_pending_count() == 1


def test_metadata_batch_remains_unrestricted_by_backlog_eligibility(
    make_controller,
    monkeypatch,
):
    games = [
        make_game(
            1,
            "Game",
            steam_type="game",
            metadata_checked=False,
        ),
        make_game(
            2,
            "Software",
            steam_type="software",
            metadata_checked=False,
        ),
        make_game(
            3,
            "DLC",
            steam_type="dlc",
            metadata_checked=False,
        ),
        make_game(
            4,
            "Some Game Public Beta",
            steam_type="game",
            metadata_checked=False,
        ),
    ]

    controller = make_controller(games)
    captured = capture_batch(
        monkeypatch,
        controller,
    )

    assert controller.start_metadata_batch() == "started"
    assert captured["source"] == "metadata"

    assert [game.app_id for game in captured["games"]] == [
        1,
        2,
        3,
        4,
    ]


def test_noneligible_missing_hltb_and_achievements_do_not_count_as_missing_data(
    make_controller,
):
    games = [
        make_game(
            1,
            "Known Software",
            steam_type="software",
            genres=["Utilities"],
        ),
        make_game(
            2,
            "Unknown Tool",
            steam_type="unknown",
            genres=["Utilities"],
        ),
        make_game(
            3,
            "Some Game Test Server",
            steam_type="game",
        ),
    ]

    controller = make_controller(games)

    assert not controller.has_missing_data()
    assert not controller.missing_data_needs_steam_id()


def test_eligible_missing_sources_still_count_as_missing_data(
    make_controller,
):
    game = make_game(
        1,
        "Eligible Game",
        steam_type="game",
    )

    controller = make_controller([game])

    assert controller.has_missing_data()
    assert controller.missing_data_needs_steam_id()
