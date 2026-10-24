import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from recommendations.data import RecommendationGameData
from storage import database


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()

    if app is None:
        app = QApplication([])

    return app


@pytest.fixture
def temporary_database(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_FILE", test_db)
    database.initialize_database()
    return test_db


@pytest.fixture
def make_game():
    def factory(
        app_id,
        name,
        *,
        playtime_minutes=0,
        playtime_2weeks_minutes=0,
        last_played_timestamp=0,
        manual_status=None,
        rating=None,
        metadata_checked=True,
        genres=None,
        tags=None,
        hltb_main=None,
        hltb_main_extra=None,
        hltb_completionist=None,
        hltb_all_styles=None,
        hltb_checked=False,
        hltb_match_status=None,
        achievement_total=None,
        achievements_unlocked=None,
        achievements_checked=False,
    ):
        return RecommendationGameData(
            app_id=app_id,
            name=name,
            playtime_minutes=playtime_minutes,
            playtime_2weeks_minutes=playtime_2weeks_minutes,
            last_played_timestamp=last_played_timestamp,
            manual_status=manual_status,
            rating=rating,
            metadata_checked=metadata_checked,
            genres=list(genres or []),
            tags=dict(tags or {}),
            hltb_main=hltb_main,
            hltb_main_extra=hltb_main_extra,
            hltb_completionist=hltb_completionist,
            hltb_all_styles=hltb_all_styles,
            hltb_checked=hltb_checked,
            hltb_match_status=hltb_match_status,
            achievement_total=achievement_total,
            achievements_unlocked=achievements_unlocked,
            achievements_checked=achievements_checked,
        )

    return factory
