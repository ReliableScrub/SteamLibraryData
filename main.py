import os
from ui.gui import run_gui

from dotenv import load_dotenv

from storage.cache import load_games, save_games
from api.steam_api import get_owned_games

def main():
    load_dotenv()

    steam_api_key = os.getenv("STEAM_API_KEY")

    if not steam_api_key:
        print("Steam API key not found.")
        exit()

    games = load_games()

    if games is not None:
        print(f"Cached library found: {len(games)} games.")

        refresh = input("Refresh library from Steam? (y/n): ").strip().lower()
    else:
        print("No cached library found.")
        refresh = "y"

    if refresh == "y":
        steam_id = input("Enter your SteamID64: ").strip()

        fresh_games = get_owned_games(steam_id, steam_api_key)

        if games is not None:
            cached_games_by_id = {}

            for cached_game in games:
                cached_games_by_id[cached_game.app_id] = cached_game

            for fresh_game in fresh_games:
                cached_game = cached_games_by_id.get(fresh_game.app_id)

                if cached_game is not None:
                    fresh_game.genres = cached_game.genres
                    fresh_game.tags = cached_game.tags

                    fresh_game.hltb_main = cached_game.hltb_main
                    fresh_game.hltb_main_extra = cached_game.hltb_main_extra
                    fresh_game.hltb_completionist = (
                        cached_game.hltb_completionist
                    )
                    fresh_game.hltb_all_styles = (
                        cached_game.hltb_all_styles
                    )
                    fresh_game.hltb_match_name = (
                        cached_game.hltb_match_name
                    )
                    fresh_game.hltb_similarity = (
                        cached_game.hltb_similarity
                    )
                    fresh_game.hltb_checked = (
                        cached_game.hltb_checked
                    )

                    fresh_game.achievement_total = (
                        cached_game.achievement_total
                    )
                    fresh_game.achievements_unlocked = (
                        cached_game.achievements_unlocked
                    )
                    fresh_game.achievements_checked = (
                        cached_game.achievements_checked
                    )

        games = fresh_games

        save_games(games)

        print("Library refreshed and saved.")
    else:
        print("Loaded library from cache.")

    print(f"Games loaded: {len(games)}")

    run_gui(games, steam_api_key)

if __name__ == "__main__":
    main()