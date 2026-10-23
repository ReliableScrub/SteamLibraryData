from dataclasses import dataclass

from recommendations.features import build_content_features, cosine_similarity
from recommendations.neighbors import shared_feature_count, support_adjusted_similarity

DEFAULT_SIMILAR_GAME_LIMIT = 50
DEFAULT_SHARED_TRAIT_LIMIT = 3

SUPPRESSED_SHARED_TRAITS = frozenset(
    {
        "casual",
        "free to play",
        "indie",
        "kickstarter",
    }
)


@dataclass(frozen=True)
class SimilarGameScore:
    app_id: int
    similarity: float
    adjusted_similarity: float
    shared_feature_count: int
    shared_traits: tuple[str, ...]


def _display_feature_name(feature):
    if ":" not in feature:
        return feature

    _, name = feature.split(":", 1)
    return name


def _shared_traits(reference_vector, candidate_vector, limit):
    merged = {}

    for feature in reference_vector.keys() & candidate_vector.keys():
        contribution = reference_vector[feature] * candidate_vector[feature]

        if contribution <= 0:
            continue

        name = _display_feature_name(feature)

        if name.casefold() in SUPPRESSED_SHARED_TRAITS:
            continue

        merged[name] = merged.get(name, 0.0) + contribution

    ranked = sorted(
        merged.items(),
        key=lambda item: (-item[1], item[0].casefold()),
    )

    return tuple(name for name, _ in ranked[:limit])


def _is_backlog_candidate(game):
    if game.playtime_minutes > 0:
        return False

    is_backlog_eligible = getattr(game, "is_backlog_eligible", None)

    return not (callable(is_backlog_eligible) and not is_backlog_eligible())


class SimilarGameIndex:
    def __init__(self, games):
        self.games = list(games)
        self.games_by_id = {game.app_id: game for game in self.games}
        self.content_vectors = build_content_features(self.games)

    def find_similar(
        self,
        reference_app_id,
        *,
        limit=DEFAULT_SIMILAR_GAME_LIMIT,
        unplayed_only=True,
        shared_trait_limit=DEFAULT_SHARED_TRAIT_LIMIT,
    ):
        reference_vector = self.content_vectors.get(reference_app_id)

        if not reference_vector:
            return []

        scores = []

        for game in self.games:
            if game.app_id == reference_app_id:
                continue

            if unplayed_only and not _is_backlog_candidate(game):
                continue

            candidate_vector = self.content_vectors.get(game.app_id)

            if not candidate_vector:
                continue

            similarity = cosine_similarity(
                reference_vector,
                candidate_vector,
            )

            if similarity <= 0:
                continue

            shared_count = shared_feature_count(
                reference_vector,
                candidate_vector,
            )

            adjusted_similarity = support_adjusted_similarity(
                similarity,
                shared_count,
            )

            if adjusted_similarity <= 0:
                continue

            scores.append(
                SimilarGameScore(
                    app_id=game.app_id,
                    similarity=similarity,
                    adjusted_similarity=adjusted_similarity,
                    shared_feature_count=shared_count,
                    shared_traits=_shared_traits(
                        reference_vector,
                        candidate_vector,
                        shared_trait_limit,
                    ),
                )
            )

        scores.sort(
            key=lambda score: (
                -score.adjusted_similarity,
                -score.similarity,
                score.app_id,
            )
        )

        return scores[:limit]
