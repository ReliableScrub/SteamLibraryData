from recommendations.data import RecommendationGameData
from recommendations.engine import (
    METHOD_BASELINE,
    METHOD_KMEANS,
    build_recommendations,
)


def make_game(
    app_id,
    name,
    *,
    playtime_minutes=0,
    rating=None,
    genres=None,
    tags=None,
):
    return RecommendationGameData(
        app_id=app_id,
        name=name,
        playtime_minutes=playtime_minutes,
        playtime_2weeks_minutes=0,
        last_played_timestamp=0,
        manual_status=None,
        rating=rating,
        metadata_checked=True,
        genres=genres or [],
        tags=tags or {},
        hltb_main=None,
        hltb_main_extra=None,
        hltb_completionist=None,
        hltb_all_styles=None,
        hltb_checked=False,
        hltb_match_status=None,
        achievement_total=None,
        achievements_unlocked=None,
        achievements_checked=False,
    )


def build_positive_games(count):
    games = []

    for index in range(count):
        games.append(
            make_game(
                index + 1,
                f"Positive Game {index + 1}",
                playtime_minutes=600,
                rating=5,
                genres=["RPG" if index % 2 == 0 else "Action"],
                tags={
                    f"Group {index % 5}": 100,
                    f"Feature {index % 7}": 80,
                },
            )
        )

    return games


def test_engine_uses_baseline_for_small_history():
    games = build_positive_games(14)

    games.append(
        make_game(
            1000,
            "Candidate",
            genres=["RPG"],
            tags={
                "Group 0": 100,
            },
        )
    )

    result = build_recommendations(games)

    assert result.method == METHOD_BASELINE
    assert result.cluster_count is None

    assert {score.app_id for score in result.scores} == {1000}


def test_engine_uses_adaptive_kmeans_when_history_is_large_enough():
    games = build_positive_games(20)

    games.append(
        make_game(
            1000,
            "Candidate",
            genres=["RPG"],
            tags={
                "Group 0": 100,
            },
        )
    )

    result = build_recommendations(games)

    assert result.method == METHOD_KMEANS
    assert result.cluster_count == 3

    assert {score.app_id for score in result.scores} == {1000}


def test_engine_returns_scores_in_recommendation_order():
    games = build_positive_games(20)

    games.extend(
        [
            make_game(
                1000,
                "Strong Candidate",
                genres=["RPG"],
                tags={
                    "Group 0": 100,
                    "Feature 0": 80,
                },
            ),
            make_game(
                1001,
                "Weak Candidate",
                genres=["Simulation"],
                tags={
                    "Unrelated": 100,
                },
            ),
        ]
    )

    result = build_recommendations(games)

    scores = [score.recommendation_score for score in result.scores]

    assert scores == sorted(
        scores,
        reverse=True,
    )


def test_engine_builds_diversified_top_picks():
    games = build_positive_games(20)

    games.extend(
        [
            make_game(
                1000,
                "Candidate A",
                genres=["RPG"],
                tags={"Group 0": 100},
            ),
            make_game(
                1001,
                "Candidate B",
                genres=["Action"],
                tags={"Group 1": 100},
            ),
        ]
    )

    result = build_recommendations(games)
    

    assert result.top_picks
    assert len(result.top_picks) <= 10

    assert {score.app_id for score in result.top_picks}.issubset(
        {score.app_id for score in result.scores}
    )
