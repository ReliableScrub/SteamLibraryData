from api.achievements_api import get_achievement_progress
from api.hltb_api import get_hltb_data
from api.steamspy_api import get_game_metadata

def update_hltb(game):
    result = get_hltb_data(game.name)

    if result is not None:
        game.hltb_main = result.main_story
        game.hltb_main_extra = result.main_extra
        game.hltb_completionist = result.completionist
        game.hltb_all_styles = result.all_styles

        game.hltb_match_name = result.game_name
        game.hltb_similarity = result.similarity

    game.hltb_checked = True

def update_metadata(game):
    genres, tags = get_game_metadata(game.app_id)

    game.genres = genres
    game.tags = tags
    game.metadata_checked = True

def update_achievements(game,steam_id,steam_api_key):
    total, unlocked = get_achievement_progress(steam_id, steam_api_key, game.app_id)

    game.achievement_total = total
    game.achievements_unlocked = unlocked
    game.achievements_checked = True