from recommendations.features import cosine_similarity

DEFAULT_MMR_RELEVANCE_WEIGHT = 0.90


def rerank_mmr(
    scores,
    content_vectors,
    *,
    limit,
    relevance_weight=DEFAULT_MMR_RELEVANCE_WEIGHT,
):
    if not 0.0 <= relevance_weight <= 1.0:
        raise ValueError("relevance_weight must be between 0 and 1.")

    if limit < 0:
        raise ValueError("limit must be non-negative.")

    if limit == 0 or not scores:
        return []

    candidates = list(scores)

    original_rank = {score.app_id: index for index, score in enumerate(candidates)}

    max_selected_similarity = {score.app_id: 0.0 for score in candidates}

    selected = []
    remaining = list(candidates)

    while remaining and len(selected) < limit:
        best_score = None
        best_key = None

        for score in remaining:
            redundancy = max_selected_similarity[score.app_id]

            mmr_score = (
                relevance_weight * score.recommendation_score
                - (1.0 - relevance_weight) * redundancy
            )

            key = (
                mmr_score,
                score.recommendation_score,
                -original_rank[score.app_id],
            )

            if best_key is None or key > best_key:
                best_key = key
                best_score = score

        selected.append(best_score)

        remaining.remove(best_score)

        selected_vector = content_vectors.get(best_score.app_id)

        if not selected_vector:
            continue

        for score in remaining:
            candidate_vector = content_vectors.get(score.app_id)

            if not candidate_vector:
                continue

            similarity = cosine_similarity(
                candidate_vector,
                selected_vector,
            )

            if similarity > max_selected_similarity[score.app_id]:
                max_selected_similarity[score.app_id] = similarity

    return selected
