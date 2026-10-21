from recommendations.data import load_recommendation_games
from recommendations.engine import build_recommendations
from recommendations.persistence import (
    load_recommendation_state,
    load_saved_recommendations,
    save_recommendation_build,
)

TOP_RESULTS = 20


def main():
    games = load_recommendation_games()

    build = build_recommendations(games)

    print(f"Generated method: {build.method}")

    print(f"Generated clusters: {build.cluster_count}")

    print(f"Generated candidates: {len(build.scores)}")

    save_recommendation_build(
        build,
        games,
    )

    state = load_recommendation_state()

    saved = load_saved_recommendations()

    print()
    print("Saved recommendation state:")

    print(f"  method: {state[0]}")

    print(f"  model version: {state[1]}")

    print(f"  feature version: {state[2]}")

    print(f"  generated at: {state[3]}")

    print(f"  training games: {state[4]}")

    print(f"  rated games: {state[5]}")

    print(f"  implicit games: {state[6]}")

    print(f"  candidates: {state[7]}")

    print()
    print(f"Saved rows: {len(saved)}")

    print()
    print(f"Top {min(TOP_RESULTS, len(saved))} saved recommendations")

    print("-" * 80)

    games_by_id = {game.app_id: game for game in games}

    for rank, row in enumerate(
        saved[:TOP_RESULTS],
        start=1,
    ):
        app_id = row[0]
        score = row[1]

        game = games_by_id.get(app_id)

        name = game.name if game is not None else "<unknown>"

        print(f"{rank:>2}. {score:.4f}  {name} ({app_id})")

    print()
    print("Persistence audit complete.")


if __name__ == "__main__":
    main()
