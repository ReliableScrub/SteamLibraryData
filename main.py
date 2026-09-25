import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="replace",
    )

from dotenv import load_dotenv

from storage.database import initialize_database, load_games
from ui.gui import run_gui


def main():
    load_dotenv()

    steam_api_key = os.getenv("STEAM_API_KEY")

    if not steam_api_key:
        print("STEAM_API_KEY is missing.")
        return

    initialize_database()

    games = load_games()

    run_gui(games, steam_api_key)


if __name__ == "__main__":
    main()
