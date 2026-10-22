from collections.abc import Mapping
from dataclasses import dataclass
from math import sqrt

DEFAULT_FEATURE_LIMIT = 3
SUPPORTING_GAME_LIMIT = 3

SUPPRESSED_FEATURES = frozenset(
    {
        "casual",
        "free to play",
        "indie",
        "kickstarter",
    }
)


@dataclass(frozen=True)
class ExplanationFeature:
    name: str
    contribution: float
    sources: tuple[str, ...]


@dataclass(frozen=True)
class SupportingPlayedGame:
    app_id: int
    name: str
    raw_similarity: float
    adjusted_similarity: float
    shared_feature_count: int
    evidence: str
    feedback_weight: float
    playtime_minutes: int
    shared_features: tuple[ExplanationFeature, ...]


@dataclass(frozen=True)
class RecommendationExplanation:
    taste_source: str
    taste_features: tuple[ExplanationFeature, ...]
    supporting_games: tuple[SupportingPlayedGame, ...]


def _get_value(item, names, default=None):
    for name in names:
        if isinstance(item, Mapping) and name in item:
            value = item[name]
            if value is not None:
                return value

        value = getattr(item, name, None)
        if value is not None:
            return value

    return default


def _vector_items(vector):
    if not isinstance(vector, Mapping):
        return []

    items = []

    for key, value in vector.items():
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue

        if numeric_value != 0.0:
            items.append((key, numeric_value))

    return items


def _feature_parts(key):
    if isinstance(key, (tuple, list)) and len(key) >= 2:
        source = str(key[0]).strip().casefold()
        name = str(key[1]).strip()
        if name:
            return name, source

    text = str(key).strip()

    if ":" in text:
        possible_source, possible_name = text.split(":", 1)
        source = possible_source.strip().casefold()
        name = possible_name.strip()

        if name and source in {
            "genre",
            "tag",
            "steam genre",
            "steam tag",
            "steamspy genre",
            "steamspy tag",
        }:
            if source.startswith("steamspy "):
                source = source.removeprefix("steamspy ")
            elif source.startswith("steam "):
                source = source.removeprefix("steam ")
            return name, source

    return text, "feature"


def _cosine(left, right):
    left_items = dict(_vector_items(left))
    right_items = dict(_vector_items(right))

    if not left_items or not right_items:
        return 0.0

    left_norm = sqrt(sum(value * value for value in left_items.values()))
    right_norm = sqrt(sum(value * value for value in right_items.values()))

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    dot_product = sum(
        value * right_items.get(key, 0.0) for key, value in left_items.items()
    )

    return dot_product / (left_norm * right_norm)


def _feature_contributions(
    candidate_vector,
    reference_vector,
    feature_limit=DEFAULT_FEATURE_LIMIT,
    scale=1.0,
):
    candidate_items = dict(_vector_items(candidate_vector))
    reference_items = dict(_vector_items(reference_vector))

    if not candidate_items or not reference_items:
        return ()

    candidate_norm = sqrt(sum(value * value for value in candidate_items.values()))
    reference_norm = sqrt(sum(value * value for value in reference_items.values()))

    if candidate_norm == 0.0 or reference_norm == 0.0:
        return ()

    denominator = candidate_norm * reference_norm
    merged = {}

    for key, candidate_value in candidate_items.items():
        reference_value = reference_items.get(key, 0.0)
        contribution = candidate_value * reference_value / denominator
        contribution *= scale

        # Negative overlap is not a useful positive explanation.
        if contribution <= 0.0:
            continue

        name, source = _feature_parts(key)
        if not name or name.casefold() in SUPPRESSED_FEATURES:
            continue

        normalized_name = name.casefold()
        entry = merged.get(normalized_name)

        if entry is None:
            entry = {
                "name": name,
                "contribution": 0.0,
                "sources": set(),
            }
            merged[normalized_name] = entry

        entry["contribution"] += contribution

        if source:
            entry["sources"].add(source)

    ordered = sorted(
        merged.values(),
        key=lambda entry: (
            -entry["contribution"],
            entry["name"].casefold(),
        ),
    )

    if feature_limit is not None:
        ordered = ordered[: max(0, int(feature_limit))]

    source_order = {"genre": 0, "tag": 1}
    features = []

    for entry in ordered:
        sources = tuple(
            sorted(
                entry["sources"],
                key=lambda source: (source_order.get(source, 99), source),
            )
        )

        features.append(
            ExplanationFeature(
                name=entry["name"],
                contribution=entry["contribution"],
                sources=sources,
            )
        )

    return tuple(features)


def _shared_feature_count(candidate_vector, reference_vector):
    candidate_features = {
        key for key, value in _vector_items(candidate_vector) if value != 0.0
    }
    reference_features = {
        key for key, value in _vector_items(reference_vector) if value != 0.0
    }

    return len(candidate_features & reference_features)


def _feedback_weight_for_game(game):
    try:
        from recommendations.feedback import final_feedback

        feedback = final_feedback(
            rating=getattr(game, "rating", None),
            manual_status=getattr(game, "manual_status", None),
            playtime_minutes=getattr(game, "playtime_minutes", 0) or 0,
            hltb_main=getattr(game, "hltb_main", None),
            hltb_main_extra=getattr(game, "hltb_main_extra", None),
            hltb_completionist=getattr(game, "hltb_completionist", None),
            hltb_all_styles=getattr(game, "hltb_all_styles", None),
            achievement_total=getattr(game, "achievement_total", None),
            achievements_unlocked=getattr(game, "achievements_unlocked", None),
        )
    except (AttributeError, TypeError, ValueError):
        return 0.0

    if feedback is None:
        return 0.0

    return float(feedback.score) * float(feedback.confidence)


def _fallback_neighbor(score):
    app_id = _get_value(
        score,
        ("nearest_positive_app_id", "nearest_game_app_id"),
    )

    if app_id is None:
        return None

    raw_similarity = _get_value(
        score,
        ("nearest_positive_similarity", "nearest_similarity"),
        0.0,
    )
    adjusted_similarity = _get_value(
        score,
        ("nearest_positive_adjusted_similarity", "nearest_adjusted_similarity"),
        raw_similarity,
    )

    return {
        "app_id": app_id,
        "raw_similarity": raw_similarity,
        "adjusted_similarity": adjusted_similarity,
        "shared_feature_count": _get_value(
            score,
            ("nearest_positive_shared_features", "nearest_shared_features"),
            0,
        ),
        "feedback_weight": _get_value(
            score,
            ("nearest_positive_feedback_weight", "nearest_feedback_weight"),
            0.0,
        ),
    }


def _neighbors_for_score(score):
    neighbors = _get_value(score, ("neighbors", "supporting_games"), ())

    if isinstance(neighbors, Mapping):
        neighbors = list(neighbors.values())
    elif neighbors is None:
        neighbors = []
    else:
        neighbors = list(neighbors)

    if not neighbors:
        fallback = _fallback_neighbor(score)
        if fallback is not None:
            neighbors = [fallback]

    return neighbors[:SUPPORTING_GAME_LIMIT]


def _build_supporting_game(
    candidate_app_id,
    neighbor,
    game_by_id,
    content_vectors,
    feature_limit,
):
    reference_app_id = _get_value(
        neighbor,
        ("app_id", "reference_app_id", "game_app_id", "positive_app_id"),
    )

    if reference_app_id is None or reference_app_id == candidate_app_id:
        return None

    reference_game = game_by_id.get(reference_app_id)
    if reference_game is None:
        return None

    playtime_minutes = int(getattr(reference_game, "playtime_minutes", 0) or 0)
    if playtime_minutes <= 0:
        return None

    candidate_vector = content_vectors.get(candidate_app_id)
    reference_vector = content_vectors.get(reference_app_id)

    raw_similarity = float(
        _get_value(
            neighbor,
            ("raw_similarity", "similarity", "raw"),
            _cosine(candidate_vector, reference_vector),
        )
        or 0.0
    )
    adjusted_similarity = float(
        _get_value(
            neighbor,
            ("adjusted_similarity", "adjusted", "adjusted_score"),
            raw_similarity,
        )
        or 0.0
    )

    shared_count_value = _get_value(
        neighbor,
        ("shared_feature_count", "shared_count", "shared"),
    )

    if shared_count_value is None:
        shared_value = _get_value(neighbor, ("shared_features",))
        if isinstance(shared_value, (list, tuple, set, frozenset)):
            shared_count_value = len(shared_value)
        elif isinstance(shared_value, (int, float)):
            shared_count_value = int(shared_value)
        else:
            shared_count_value = _shared_feature_count(
                candidate_vector,
                reference_vector,
            )

    evidence = _get_value(
        neighbor,
        ("evidence", "feedback_evidence", "feedback_type"),
    )

    if evidence is None:
        rating = getattr(reference_game, "rating", None)
        evidence = f"{rating} stars" if rating is not None else "implicit"

    feedback_weight = _get_value(
        neighbor,
        ("feedback_weight", "positive_feedback_weight", "weight"),
    )

    if feedback_weight is None:
        feedback_weight = _feedback_weight_for_game(reference_game)

    scale = adjusted_similarity / raw_similarity if raw_similarity > 0.0 else 0.0
    shared_features = _feature_contributions(
        candidate_vector,
        reference_vector,
        feature_limit=feature_limit,
        scale=scale,
    )

    return SupportingPlayedGame(
        app_id=int(reference_app_id),
        name=str(getattr(reference_game, "name", reference_app_id)),
        raw_similarity=raw_similarity,
        adjusted_similarity=adjusted_similarity,
        shared_feature_count=int(shared_count_value or 0),
        evidence=str(evidence),
        feedback_weight=float(feedback_weight or 0.0),
        playtime_minutes=playtime_minutes,
        shared_features=shared_features,
    )


def build_recommendation_explanations(
    games,
    content_vectors,
    profile,
    baseline_scores,
    recommendation_scores,
    method,
    cluster_model=None,
    feature_limit=DEFAULT_FEATURE_LIMIT,
):
    """Build taste and multi-game history explanations keyed by candidate App ID.

    ``baseline_scores`` supplies the feedback-weighted positive neighborhood.
    ``recommendation_scores`` supplies the final ranked recommendation scores.
    The return value is a dict mapping candidate App IDs to
    :class:`RecommendationExplanation` objects.
    """
    game_by_id = {game.app_id: game for game in games}
    baseline_by_id = {score.app_id: score for score in baseline_scores}
    explanations = {}
    use_clusters = str(method).casefold() in {"kmeans", "k-means"}

    for score in recommendation_scores:
        candidate_app_id = score.app_id
        candidate_vector = content_vectors.get(candidate_app_id)
        if not candidate_vector:
            continue

        taste_reference = profile
        taste_source = "profile"

        if use_clusters and cluster_model is not None:
            cluster_index = _get_value(score, ("cluster_index",))
            centers = _get_value(cluster_model, ("cluster_centers",), ())

            if cluster_index is not None and 0 <= int(cluster_index) < len(centers):
                taste_reference = centers[int(cluster_index)]
                taste_source = "cluster"

        taste_features = _feature_contributions(
            candidate_vector,
            taste_reference,
            feature_limit=feature_limit,
        )

        reference_score = baseline_by_id.get(candidate_app_id, score)
        supporting_games = []

        for neighbor in _neighbors_for_score(reference_score):
            supporting_game = _build_supporting_game(
                candidate_app_id=candidate_app_id,
                neighbor=neighbor,
                game_by_id=game_by_id,
                content_vectors=content_vectors,
                feature_limit=feature_limit,
            )

            if supporting_game is not None:
                supporting_games.append(supporting_game)

        explanations[candidate_app_id] = RecommendationExplanation(
            taste_source=taste_source,
            taste_features=taste_features,
            supporting_games=tuple(supporting_games),
        )

    return explanations
