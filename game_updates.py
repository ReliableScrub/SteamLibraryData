import time

from api.achievements_api import get_achievement_progress
from api.hltb_api import get_hltb_data
from api.steamspy_api import get_game_metadata
from storage.database import (
    save_achievement_data,
    save_hltb_data,
    save_metadata_data,
)


def fetch_hltb(game, cancel_requested=None):
    return get_hltb_data(
        game.name,
        game.app_id,
        cancel_requested=cancel_requested,
    )


def clear_hltb_match(game):
    game.hltb_main = None
    game.hltb_main_extra = None
    game.hltb_completionist = None
    game.hltb_all_styles = None

    game.hltb_match_name = None
    game.hltb_similarity = None
    game.hltb_game_id = None
    game.hltb_web_link = None


def apply_hltb_candidate(game, candidate):
    clear_hltb_match(game)

    game.hltb_main = candidate.get("main_story")
    game.hltb_main_extra = candidate.get("main_extra")
    game.hltb_completionist = candidate.get("completionist")
    game.hltb_all_styles = candidate.get("all_styles")

    game.hltb_match_name = candidate["game_name"]
    game.hltb_similarity = candidate.get("similarity")
    game.hltb_game_id = candidate.get("game_id")
    game.hltb_web_link = candidate.get("game_web_link")

    game.hltb_match_status = "matched"
    game.hltb_checked = True


def apply_hltb(game, result):
    status = result["status"]

    if status == "matched":
        apply_hltb_candidate(
            game,
            result["match"],
        )
        return

    clear_hltb_match(game)

    if status == "review":
        game.hltb_match_status = "review"
        game.hltb_checked = True
        return

    if status == "no_match":
        game.hltb_match_status = "no_match"
        game.hltb_checked = True
        return

    raise ValueError(f"Unknown HLTB result status: {status}")


def mark_hltb_no_match(game):
    clear_hltb_match(game)

    game.hltb_match_status = "no_match"
    game.hltb_checked = True


def _hltb_state(game):
    return (
        game.hltb_main,
        game.hltb_main_extra,
        game.hltb_completionist,
        game.hltb_all_styles,
        game.hltb_match_name,
        game.hltb_similarity,
        game.hltb_game_id,
        game.hltb_web_link,
        game.hltb_match_status,
        game.hltb_checked,
    )


def _restore_hltb_state(game, state):
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
        game.hltb_checked,
    ) = state


def update_hltb(game, cancel_requested=None):
    result = fetch_hltb(
        game,
        cancel_requested=cancel_requested,
    )
    previous = _hltb_state(game)

    try:
        apply_hltb(game, result)
        candidates = result.get("candidates", [])
        save_hltb_data(game, candidates=candidates)

    except Exception:
        _restore_hltb_state(game, previous)
        raise


def accept_hltb_candidate(game, candidate):
    previous = _hltb_state(game)

    try:
        apply_hltb_candidate(game, candidate)
        save_hltb_data(game)

    except Exception:
        _restore_hltb_state(game, previous)
        raise


def set_hltb_no_match(game):
    previous = _hltb_state(game)

    try:
        mark_hltb_no_match(game)
        save_hltb_data(game)

    except Exception:
        _restore_hltb_state(game, previous)
        raise


def fetch_metadata(game):
    return get_game_metadata(game.app_id)


def apply_metadata(game, result):
    genres, tags = result

    if genres is None:
        genres = []

    if tags is None or tags == []:
        tags = {}

    if not isinstance(tags, dict):
        raise TypeError(
            f"Expected metadata tags to be a dict, got {type(tags).__name__}"
        )

    game.genres = genres
    game.tags = tags
    game.metadata_checked = True


def update_metadata(game):
    result = fetch_metadata(game)
    previous_genres = list(game.genres)
    previous_tags = dict(game.tags)
    previous_checked = game.metadata_checked

    try:
        apply_metadata(game, result)
        save_metadata_data(game)

    except Exception:
        game.genres = previous_genres
        game.tags = previous_tags
        game.metadata_checked = previous_checked
        raise


def fetch_achievements(game, steam_id, steam_api_key):
    return get_achievement_progress(steam_id, steam_api_key, game.app_id)


def apply_achievements(game, result):
    total, unlocked = result

    game.achievement_total = total
    game.achievements_unlocked = unlocked
    game.achievements_checked = True
    game.achievements_updated_at = int(time.time())
    game.achievements_playtime_minutes = game.playtime_minutes


def update_achievements(game, steam_id, steam_api_key):
    result = fetch_achievements(game, steam_id, steam_api_key)

    previous = (
        game.achievement_total,
        game.achievements_unlocked,
        game.achievements_checked,
        game.achievements_updated_at,
        game.achievements_playtime_minutes,
    )

    try:
        apply_achievements(game, result)
        save_achievement_data(game)

    except Exception:
        (
            game.achievement_total,
            game.achievements_unlocked,
            game.achievements_checked,
            game.achievements_updated_at,
            game.achievements_playtime_minutes,
        ) = previous
        raise
