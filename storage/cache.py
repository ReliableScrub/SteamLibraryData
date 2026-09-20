import json
from dataclasses import asdict
from pathlib import Path

from game import Game

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = PROJECT_ROOT / "data" / "games.json"

def save_games(games):
    CACHE_FILE.parent.mkdir(exist_ok=True)

    game_data = []
    # Convert each Game object to a dictionary and append it to the list
    for game in games:
        game_data.append(asdict(game))

    with open(CACHE_FILE, "w", encoding="utf-8") as file:
        json.dump(game_data, file, indent=4)

def load_games():
    if not CACHE_FILE.exists():
        return None

    with open(CACHE_FILE, "r", encoding="utf-8") as file:
        game_data = json.load(file)

    games = []

    for item in game_data:
        game = Game(
            app_id=item["app_id"],
            name=item["name"],
            playtime_minutes=item["playtime_minutes"],
            genres=item.get("genres", []),
            tags=item.get("tags", {}),
            metadata_checked=item.get("metadata_checked", False),

            hltb_main=item.get("hltb_main"),
            hltb_main_extra=item.get("hltb_main_extra"),
            hltb_completionist=item.get("hltb_completionist"),
            hltb_all_styles=item.get("hltb_all_styles"),
            hltb_match_name=item.get("hltb_match_name"),
            hltb_similarity=item.get("hltb_similarity"),
            hltb_checked=item.get("hltb_checked", False),

            achievement_total=item.get("achievement_total"),
            achievements_unlocked=item.get("achievements_unlocked"),
            achievements_checked=item.get("achievements_checked", False)
        )
        games.append(game)

    return games