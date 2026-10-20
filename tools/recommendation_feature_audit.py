import sys
from collections import Counter

from recommendations.features import build_content_features, cosine_similarity
from storage.database import load_games


def print_similar_games(target_game, games, vectors, limit=10):
    target_vector = vectors[target_game.app_id]

    similarities = []

    for game in games:
        if game.app_id == target_game.app_id:
            continue

        similarity = cosine_similarity(
            target_vector,
            vectors[game.app_id],
        )

        similarities.append((similarity, game))

    similarities.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    print()
    print(f"Most similar games to: {target_game.name}")

    for similarity, game in similarities[:limit]:
        print(f"  {similarity:.3f}  {game.name}")


def find_game(games, search_text):
    search_text = search_text.lower()

    exact_matches = [game for game in games if game.name.lower() == search_text]

    if exact_matches:
        return exact_matches[0]

    partial_matches = [game for game in games if search_text in game.name.lower()]

    if len(partial_matches) == 1:
        return partial_matches[0]

    if len(partial_matches) > 1:
        print("Multiple games matched:")

        for game in partial_matches[:20]:
            print(f"  {game.name}")

        return None

    print(f'No game matched "{search_text}".')
    return None


def main():
    all_games = load_games()

    games = [game for game in all_games if game.steam_type == "game"]

    vectors = build_content_features(games)

    feature_frequency = Counter()

    for vector in vectors.values():
        feature_frequency.update(vector.keys())

    empty_vectors = [game for game in games if not vectors.get(game.app_id)]

    tag_weights = [weight for game in games for weight in game.tags.values()]

    genre_features = [
        feature for feature in feature_frequency if feature.startswith("genre:")
    ]

    tag_features = [
        feature for feature in feature_frequency if feature.startswith("tag:")
    ]

    print(f"Confirmed games: {len(games)}")
    print(f"Vectors: {len(vectors)}")
    print(f"Empty vectors: {len(empty_vectors)}")
    print()

    print(f"Unique features: {len(feature_frequency)}")
    print(f"Unique genres: {len(genre_features)}")
    print(f"Unique tags: {len(tag_features)}")
    print()

    print("Most common features:")
    for feature, count in feature_frequency.most_common(20):
        print(f"  {count:4}  {feature}")

    print()

    rare_features = sorted(
        feature_frequency.items(),
        key=lambda item: (item[1], item[0]),
    )

    print("Rare features:")
    for feature, count in rare_features[:20]:
        print(f"  {count:4}  {feature}")

    print()

    if tag_weights:
        print(f"SteamSpy tag weight min: {min(tag_weights)}")
        print(f"SteamSpy tag weight max: {max(tag_weights)}")
        print(f"Zero tag weights: {sum(weight == 0 for weight in tag_weights)}")
        print(f"Negative tag weights: {sum(weight < 0 for weight in tag_weights)}")

    if empty_vectors:
        print()
        print("Games with empty vectors:")

        for game in empty_vectors[:20]:
            print(f"  {game.app_id}: {game.name}")

    if len(sys.argv) > 1:
        search_text = " ".join(sys.argv[1:])
        target_game = find_game(games, search_text)

        if target_game is not None:
            print_game_features(
                target_game,
                vectors[target_game.app_id],
            )

            print_similar_games(
                target_game,
                games,
                vectors,
            )

            similarities = [
                (
                    cosine_similarity(
                        vectors[target_game.app_id],
                        vectors[game.app_id],
                    ),
                    game,
                )
                for game in games
                if game.app_id != target_game.app_id
            ]

            similarities.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            for _similarity, game in similarities[:3]:
                print_similarity_breakdown(
                    target_game,
                    game,
                    vectors,
                )


def print_game_features(game, vector, limit=20):
    print()
    print(f"Features for: {game.name}")

    print("Genres:")
    for genre in game.genres:
        print(f"  {genre}")

    print("Raw SteamSpy tags:")
    for tag, weight in sorted(
        game.tags.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]:
        print(f"  {weight:6}  {tag}")

    print("Final weighted features:")
    for feature, weight in sorted(
        vector.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]:
        print(f"  {weight:.4f}  {feature}")


def print_similarity_breakdown(game_a, game_b, vectors, limit=15):
    vector_a = vectors[game_a.app_id]
    vector_b = vectors[game_b.app_id]

    contributions = []

    for feature, value_a in vector_a.items():
        value_b = vector_b.get(feature)

        if value_b is None:
            continue

        contributions.append(
            (
                value_a * value_b,
                feature,
                value_a,
                value_b,
            )
        )

    contributions.sort(reverse=True)

    similarity = cosine_similarity(vector_a, vector_b)

    print()
    print(f"Similarity breakdown: {game_a.name} <-> {game_b.name}")
    print(f"Total similarity: {similarity:.3f}")

    for contribution, feature, value_a, value_b in contributions[:limit]:
        print(f"  {contribution:.4f}  {feature} ({value_a:.3f} x {value_b:.3f})")


if __name__ == "__main__":
    main()
