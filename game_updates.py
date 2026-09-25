from api.achievements_api import get_achievement_progress
from api.hltb_api import get_hltb_data
from api.steamspy_api import get_game_metadata
from storage.database import (
    clear_hltb_candidates,
    replace_hltb_candidates,
)


def fetch_hltb(game):
    return get_hltb_data(game.name)


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

    clear_hltb_candidates(game.app_id)


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

        replace_hltb_candidates(
            game.app_id,
            result["candidates"],
        )

        return

    if status == "no_match":
        game.hltb_match_status = "no_match"
        game.hltb_checked = True

        clear_hltb_candidates(game.app_id)

        return

    raise ValueError(f"Unknown HLTB result status: {status}")


def mark_hltb_no_match(game):
    clear_hltb_match(game)

    game.hltb_match_status = "no_match"
    game.hltb_checked = True

    clear_hltb_candidates(game.app_id)


def update_hltb(game):
    result = fetch_hltb(game)
    apply_hltb(game, result)


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
    apply_metadata(game, result)


def fetch_achievements(game, steam_id, steam_api_key):
    return get_achievement_progress(steam_id, steam_api_key, game.app_id)


def apply_achievements(game, result):
    total, unlocked = result

    game.achievement_total = total
    game.achievements_unlocked = unlocked
    game.achievements_checked = True


def update_achievements(game, steam_id, steam_api_key):
    result = fetch_achievements(game, steam_id, steam_api_key)

    apply_achievements(game, result)
