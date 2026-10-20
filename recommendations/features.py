import math
from collections import Counter


def build_content_features(games):
    document_frequency = Counter()

    # First pass
    # Count how many games contain each genre or tag
    for game in games:
        features = set()

        for genre in game.genres:
            features.add(f"genre:{genre}")

        for tag in game.tags:
            features.add(f"tag:{tag}")

        document_frequency.update(features)

    game_count = len(games)
    vectors = {}

    # Second pass:
    # Build one weighted feature vector for each game.
    for game in games:
        vector = {}

        for genre in game.genres:
            feature = f"genre:{genre}"
            # Inverse document frequency. Smaller usages, more importance
            idf = math.log((game_count + 1) / (document_frequency[feature] + 1)) + 1

            vector[feature] = idf

        max_tag_weight = max(game.tags.values(), default=0)

        for tag, weight in game.tags.items():
            feature = f"tag:{tag}"

            # SteamSpy gives tags different weights.
            # Convert each weight into a 0-1 strength relative to the
            # strongest tag on that particular game.
            if max_tag_weight > 0:
                tag_strength = weight / max_tag_weight
            else:
                tag_strength = 0

            idf = math.log((game_count + 1) / (document_frequency[feature] + 1)) + 1

            vector[feature] = tag_strength * idf

        vectors[game.app_id] = normalize_vector(vector)

    return vectors


def normalize_vector(vector):
    # Calculate the Euclidean/L2 length of the vector.
    magnitude = math.sqrt(sum(value * value for value in vector.values()))

    if magnitude == 0:
        return {}

    # Scale the whole vector to length 1.
    # This makes later cosine comparisons straightforward.
    return {feature: value / magnitude for feature, value in vector.items()}
