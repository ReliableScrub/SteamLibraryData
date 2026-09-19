import os
import time

from dotenv import load_dotenv
from steam_api import get_owned_games
from cache import save_games, load_games
from steamspy_api import get_game_metadata
from hltb_api import get_hltb_data

load_dotenv()

steam_api_key = os.getenv("STEAM_API_KEY")

if not steam_api_key:
    print("Steam API key not found.")
    exit()

games = load_games()

if games is not None:
    print("Cached library found.")

    refresh = input("Refresh library from Steam? (y/n): ").strip().lower()
else:
    refresh = "y"

if refresh == "y":
    steam_id = input("Enter your SteamID64: ").strip()

    fresh_games = get_owned_games(steam_api_key, steam_id)

    if games is not None:
        cached_games_by_id = {}

        for cached_game in games:
            cached_games_by_id[cached_game.app_id] = cached_game

        for fresh_game in fresh_games:
            cached_game = cached_games_by_id.get(fresh_game.app_id)

            if cached_game is not None:
                fresh_game.genres = cached_game.genres
                fresh_game.tags = cached_game.tags

    games = fresh_games

    save_games(games)

    print("Library downloaded and saved.")
else:
    print("Loaded library from cache.")

print("Games found:", len(games))

games_without_hltb = [
    game
    for game in games
    if not game.hltb_checked
]

hltb_batch = games_without_hltb[:5]

print(f"\nGames needing HLTB lookup: {len(games_without_hltb)}")

for game in hltb_batch:
    print(f"Searching HLTB for {game.name}...")

    try:
        hltb_result = get_hltb_data(game.name)

        if hltb_result is not None:
            game.hltb_main = hltb_result.main_story
            game.hltb_main_extra = hltb_result.main_extra
            game.hltb_completionist = hltb_result.completionist
            game.hltb_all_styles = hltb_result.all_styles

            game.hltb_match_name = hltb_result.game_name
            game.hltb_similarity = hltb_result.similarity

            print(
                f"Matched: {game.hltb_match_name} "
                f"({game.hltb_similarity:.2f})"
            )
        else:
            print("No HLTB match found.")

        game.hltb_checked = True

    except Exception as error:
        print(f"HLTB lookup failed for {game.name}: {error}")

if hltb_batch:
    save_games(games)
    print("HLTB progress saved.")

games_needing_review = [
    game
    for game in games
    if game.hltb_needs_review()
]

print(
    f"HLTB matches needing review: "
    f"{len(games_needing_review)}"
)

for game in games_needing_review[:5]:
    print(
        f"Review: {game.name} → "
        f"{game.hltb_match_name} "
        f"({game.hltb_similarity})"
    )