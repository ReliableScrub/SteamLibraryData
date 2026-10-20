from recommendations.data import RecommendationGameData
from recommendations.features import build_content_features, cosine_similarity
from recommendations.profile import build_preference_profile


def make_game(
    app_id,
    name,
    rating=None,
    playtime_minutes=0,
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
    )


def test_recommendation_pipeline_prefers_game_similar_to_liked_game():
    games = [
        make_game(
            app_id=1,
            name="Liked RPG",
            rating=5,
            playtime_minutes=600,
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
                "Party-Based RPG": 80,
                "Choices Matter": 60,
            },
        ),
        make_game(
            app_id=2,
            name="Disliked Racing Game",
            rating=1,
            playtime_minutes=600,
            genres=["Racing"],
            tags={
                "Racing": 100,
                "Driving": 80,
                "Sports": 60,
            },
        ),
        make_game(
            app_id=3,
            name="Unplayed RPG Candidate",
            genres=["RPG"],
            tags={
                "Turn-Based": 100,
                "Party-Based RPG": 80,
                "Choices Matter": 60,
            },
        ),
        make_game(
            app_id=4,
            name="Unplayed Racing Candidate",
            genres=["Racing"],
            tags={
                "Racing": 100,
                "Driving": 80,
                "Sports": 60,
            },
        ),
    ]

    content_vectors = build_content_features(games)

    profile = build_preference_profile(
        games,
        content_vectors,
    )

    rpg_score = cosine_similarity(
        profile,
        content_vectors[3],
    )

    racing_score = cosine_similarity(
        profile,
        content_vectors[4],
    )

    assert rpg_score > 0
    assert racing_score < 0
    assert rpg_score > racing_score
