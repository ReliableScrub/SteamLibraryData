from recommendations.data import load_recommendation_games
from recommendations.diversity import rerank_mmr
from recommendations.engine import build_recommendations
from recommendations.features import build_content_features

TOP_RESULTS = 20

RELEVANCE_WEIGHTS = (
    0.95,
    0.90,
    0.85,
)


def print_ranking(
    title,
    scores,
    games_by_id,
):
    print()
    print(title)
    print("-" * 90)

    for rank, score in enumerate(
        scores,
        start=1,
    ):
        game = games_by_id.get(score.app_id)

        name = game.name if game is not None else "<unknown>"

        print(f"{rank:>2}. {score.recommendation_score:.4f}  {name}")


def main():
    games = load_recommendation_games()

    games_by_id = {game.app_id: game for game in games}

    content_vectors = build_content_features(games)

    result = build_recommendations(games)

    raw_top = result.scores[:TOP_RESULTS]

    print(f"Recommendation method: {result.method}")

    print(f"Cluster count: {result.cluster_count}")

    print_ranking(
        "Raw relevance ranking",
        raw_top,
        games_by_id,
    )

    for relevance_weight in RELEVANCE_WEIGHTS:
        diversified = rerank_mmr(
            result.scores,
            content_vectors,
            limit=TOP_RESULTS,
            relevance_weight=relevance_weight,
        )

        print_ranking(
            (f"MMR ranking (relevance weight={relevance_weight:.2f})"),
            diversified,
            games_by_id,
        )


if __name__ == "__main__":
    main()
