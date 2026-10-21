from dataclasses import dataclass

import pytest

from recommendations.diversity import rerank_mmr


@dataclass(frozen=True)
class DummyScore:
    app_id: int
    recommendation_score: float


def test_mmr_with_full_relevance_weight_preserves_ranking():
    scores = [
        DummyScore(1, 0.90),
        DummyScore(2, 0.80),
        DummyScore(3, 0.70),
    ]

    vectors = {
        1: {"tag:A": 1.0},
        2: {"tag:A": 1.0},
        3: {"tag:B": 1.0},
    }

    reranked = rerank_mmr(
        scores,
        vectors,
        limit=3,
        relevance_weight=1.0,
    )

    assert [score.app_id for score in reranked] == [1, 2, 3]


def test_mmr_can_prefer_diverse_candidate_over_near_duplicate():
    scores = [
        DummyScore(1, 0.90),
        DummyScore(2, 0.89),
        DummyScore(3, 0.85),
    ]

    vectors = {
        1: {"tag:RPG": 1.0},
        2: {"tag:RPG": 1.0},
        3: {"tag:Action": 1.0},
    }

    reranked = rerank_mmr(
        scores,
        vectors,
        limit=3,
        relevance_weight=0.80,
    )

    assert [score.app_id for score in reranked] == [1, 3, 2]


def test_mmr_keeps_first_raw_recommendation():
    scores = [
        DummyScore(1, 0.90),
        DummyScore(2, 0.80),
        DummyScore(3, 0.70),
    ]

    vectors = {
        1: {"tag:A": 1.0},
        2: {"tag:B": 1.0},
        3: {"tag:C": 1.0},
    }

    reranked = rerank_mmr(
        scores,
        vectors,
        limit=3,
        relevance_weight=0.50,
    )

    assert reranked[0].app_id == 1


def test_mmr_respects_limit():
    scores = [
        DummyScore(1, 0.90),
        DummyScore(2, 0.80),
        DummyScore(3, 0.70),
    ]

    vectors = {
        1: {"tag:A": 1.0},
        2: {"tag:B": 1.0},
        3: {"tag:C": 1.0},
    }

    reranked = rerank_mmr(
        scores,
        vectors,
        limit=2,
    )

    assert len(reranked) == 2


def test_mmr_rejects_invalid_relevance_weight():
    with pytest.raises(ValueError):
        rerank_mmr(
            [],
            {},
            limit=10,
            relevance_weight=1.1,
        )
