import time

from api.achievements_api import (
    get_achievement_progress,
    get_achievement_totals,
)
from api.hltb_api import get_hltb_data
from api.steam_api import SteamApiError
from api.steamspy_api import get_game_metadata
from local_steam import (
    find_steam_directory,
    get_local_achievement_progress,
    get_private_app_ids,
)
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
    game.hltb_updated_at = int(time.time())


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
        game.hltb_updated_at = int(time.time())
        return

    if status == "no_match":
        game.hltb_match_status = "no_match"
        game.hltb_checked = True
        game.hltb_updated_at = int(time.time())
        return

    raise ValueError(f"Unknown HLTB result status: {status}")


def mark_hltb_no_match(game):
    clear_hltb_match(game)

    game.hltb_match_status = "no_match"
    game.hltb_checked = True
    game.hltb_updated_at = int(time.time())


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
        game.hltb_updated_at,
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
        game.hltb_updated_at,
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
    genres, tags, positive_reviews, negative_reviews = result

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
    game.steamspy_positive = positive_reviews
    game.steamspy_negative = negative_reviews
    game.metadata_checked = True
    game.metadata_updated_at = int(time.time())


def update_metadata(game):
    result = fetch_metadata(game)
    previous_genres = list(game.genres)
    previous_tags = dict(game.tags)
    previous_positive = game.steamspy_positive
    previous_negative = game.steamspy_negative
    previous_checked = game.metadata_checked

    previous_updated_at = game.metadata_updated_at

    try:
        apply_metadata(game, result)
        save_metadata_data(game)

    except Exception:
        game.genres = previous_genres
        game.tags = previous_tags
        game.steamspy_positive = previous_positive
        game.steamspy_negative = previous_negative
        game.metadata_checked = previous_checked
        game.metadata_updated_at = previous_updated_at
        raise


def fetch_achievements(
    game,
    steam_id,
    steam_api_key,
    known_total=None,
):
    return get_achievement_progress(
        steam_id,
        steam_api_key,
        game.app_id,
        known_total=known_total,
    )


def apply_achievements(game, result):
    total, unlocked = result

    game.achievement_total = total
    game.achievements_unlocked = unlocked
    game.achievements_checked = True
    game.achievements_updated_at = int(time.time())
    game.achievements_playtime_minutes = game.playtime_minutes


def _achievement_state(game):
    return (
        game.achievement_total,
        game.achievements_unlocked,
        game.achievements_checked,
        game.achievements_updated_at,
        game.achievements_playtime_minutes,
    )


def _restore_achievement_state(game, state):
    (
        game.achievement_total,
        game.achievements_unlocked,
        game.achievements_checked,
        game.achievements_updated_at,
        game.achievements_playtime_minutes,
    ) = state


def save_achievement_result(game, result):
    previous = _achievement_state(game)

    try:
        apply_achievements(game, result)
        save_achievement_data(game)

    except Exception:
        _restore_achievement_state(
            game,
            previous,
        )
        raise


def _save_web_result_preserving_known_positive(
    game,
    result,
):
    existing_total = game.achievement_total
    new_total, _ = result

    if (
        isinstance(existing_total, int)
        and not isinstance(existing_total, bool)
        and existing_total > 0
        and new_total == 0
    ):
        raise SteamApiError(
            "Steam returned zero achievements for a game that already has a "
            "known positive achievement total. Its stored achievement data was "
            "left unchanged instead of being cleared."
        )

    save_achievement_result(
        game,
        result,
    )


def update_achievement_from_sources(
    game,
    steam_id,
    steam_api_key,
    bulk_totals,
    steam_dir=None,
    private_app_ids=None,
):
    app_id = game.app_id

    bulk_has_entry = app_id in bulk_totals
    bulk_total = bulk_totals.get(app_id)

    is_private = private_app_ids is not None and app_id in private_app_ids

    privacy_known = private_app_ids is not None

    local_progress = None

    if steam_dir is not None:
        local_progress = get_local_achievement_progress(
            steam_id,
            app_id,
            steam_dir=steam_dir,
        )

    existing_total = game.achievement_total
    existing_unlocked = game.achievements_unlocked

    existing_positive = (
        isinstance(existing_total, int)
        and not isinstance(existing_total, bool)
        and existing_total > 0
    )

    local_positive = local_progress is not None and local_progress[0] > 0

    if not bulk_has_entry:
        if is_private:
            raise SteamApiError(
                "This game is marked Private in Steam, and Steam did not return "
                "a batched achievement total for it. Its stored achievement data "
                "was left unchanged."
            )

        result = fetch_achievements(
            game,
            steam_id,
            steam_api_key,
        )

        _save_web_result_preserving_known_positive(
            game,
            result,
        )

        return "web"

    if (
        isinstance(bulk_total, int)
        and not isinstance(bulk_total, bool)
        and bulk_total > 0
    ):
        if local_progress is not None and local_progress[0] == bulk_total:
            local_unlocked = local_progress[1]

            local_would_regress = (
                game.achievements_checked
                and isinstance(existing_unlocked, int)
                and not isinstance(existing_unlocked, bool)
                and local_unlocked < existing_unlocked
            )

            if not local_would_regress:
                save_achievement_result(
                    game,
                    (
                        bulk_total,
                        local_unlocked,
                    ),
                )

                return "local"

        if is_private:
            raise SteamApiError(
                "This game is marked Private in Steam, and its local achievement "
                "cache is missing, stale, or older than the stored progress. "
                "Its stored achievement data was left unchanged. Temporarily make "
                "the game public if you want to force a fresh achievement check."
            )

        result = fetch_achievements(
            game,
            steam_id,
            steam_api_key,
            known_total=bulk_total,
        )

        save_achievement_result(
            game,
            result,
        )

        return "web"

    if bulk_total == 0:
        if existing_positive or local_positive:
            if is_private:
                raise SteamApiError(
                    "Steam's batched endpoint reported zero achievements for this "
                    "Private game, but existing or local data says achievements "
                    "exist. Its stored achievement data was left unchanged."
                )

            result = fetch_achievements(
                game,
                steam_id,
                steam_api_key,
            )

            _save_web_result_preserving_known_positive(
                game,
                result,
            )

            return "web"

        save_achievement_result(
            game,
            (
                0,
                0,
            ),
        )

        return "bulk_zero"

    if bulk_total is None:
        if existing_positive or local_positive:
            if is_private:
                raise SteamApiError(
                    "Steam omitted the achievement total for this Private game, "
                    "but existing or local data says achievements exist. Its stored "
                    "achievement data was left unchanged."
                )

            result = fetch_achievements(
                game,
                steam_id,
                steam_api_key,
            )

            _save_web_result_preserving_known_positive(
                game,
                result,
            )

            return "web"

        if privacy_known and not is_private:
            save_achievement_result(
                game,
                (
                    0,
                    0,
                ),
            )

            return "bulk_omitted"

        result = fetch_achievements(
            game,
            steam_id,
            steam_api_key,
        )

        _save_web_result_preserving_known_positive(
            game,
            result,
        )

        return "web"

    raise SteamApiError(
        f"Steam returned an unusable batched achievement total for AppID {app_id}."
    )


def update_achievements(
    game,
    steam_id,
    steam_api_key,
):
    try:
        bulk_totals = get_achievement_totals(
            steam_id,
            steam_api_key,
            [
                game.app_id,
            ],
        )

    except SteamApiError:
        result = fetch_achievements(
            game,
            steam_id,
            steam_api_key,
        )

        _save_web_result_preserving_known_positive(
            game,
            result,
        )

        return

    steam_dir = find_steam_directory()
    private_app_ids = None

    if steam_dir is not None:
        private_app_ids = get_private_app_ids(
            steam_id,
            steam_dir=steam_dir,
        )

    update_achievement_from_sources(
        game=game,
        steam_id=steam_id,
        steam_api_key=steam_api_key,
        bulk_totals=bulk_totals,
        steam_dir=steam_dir,
        private_app_ids=private_app_ids,
    )
