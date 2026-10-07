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

from storage.credentials import get_steam_api_key
from storage.database import initialize_database, load_games
from ui.gui import run_gui


def main():
    steam_api_key = get_steam_api_key()

    initialize_database()

    games = load_games()

    run_gui(games, steam_api_key)


if __name__ == "__main__":
    main()
