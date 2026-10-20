import pytest

from recommendations.feedback import (
    FeedbackSignal,
    PlaytimeRatios,
    achievement_engagement,
    achievement_progress,
    combine_implicit_feedback,
    explicit_rating_feedback,
    hltb_engagement,
    implicit_feedback,
    manual_status_feedback,
    playtime_engagement,
    playtime_ratios,
)


def test_unrated_game_has_no_explicit_feedback():
    assert explicit_rating_feedback(None) is None


@pytest.mark.parametrize(
    ("rating", "expected_score"),
    [
        (1, -1.0),
        (2, -0.5),
        (3, 0.0),
        (4, 0.5),
        (5, 1.0),
    ],
)
def test_rating_maps_to_expected_feedback(rating, expected_score):
    feedback = explicit_rating_feedback(rating)

    assert feedback == FeedbackSignal(
        score=expected_score,
        confidence=1.0,
    )


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_invalid_rating_is_rejected(rating):
    with pytest.raises(ValueError):
        explicit_rating_feedback(rating)


@pytest.mark.parametrize(
    ("status", "expected_feedback"),
    [
        (
            "Completed",
            FeedbackSignal(
                score=0.35,
                confidence=0.30,
            ),
        ),
        (
            "Dropped",
            FeedbackSignal(
                score=-0.45,
                confidence=0.35,
            ),
        ),
        (
            "On Hold",
            None,
        ),
        (
            None,
            None,
        ),
    ],
)
def test_manual_status_maps_to_expected_feedback(
    status,
    expected_feedback,
):
    assert manual_status_feedback(status) == expected_feedback


def test_unknown_manual_status_is_rejected():
    with pytest.raises(ValueError):
        manual_status_feedback("Banana")


def test_achievement_progress():
    assert achievement_progress(100, 25) == pytest.approx(0.25)
    assert achievement_progress(40, 40) == pytest.approx(1.0)
    assert achievement_progress(10, 0) == pytest.approx(0.0)


def test_missing_or_unavailable_achievements_have_no_progress():
    assert achievement_progress(None, None) is None
    assert achievement_progress(100, None) is None
    assert achievement_progress(0, 0) is None


@pytest.mark.parametrize(
    ("total", "unlocked"),
    [
        (-1, 0),
        (10, -1),
        (10, 11),
    ],
)
def test_invalid_achievement_counts_are_rejected(total, unlocked):
    with pytest.raises(ValueError):
        achievement_progress(total, unlocked)


def test_playtime_ratios_preserve_each_hltb_metric():
    ratios = playtime_ratios(
        playtime_minutes=600,
        hltb_main=5,
        hltb_main_extra=10,
        hltb_completionist=20,
        hltb_all_styles=8,
    )

    assert ratios == PlaytimeRatios(
        main_story=pytest.approx(2.0),
        main_extra=pytest.approx(1.0),
        completionist=pytest.approx(0.5),
        all_styles=pytest.approx(1.25),
    )


def test_missing_hltb_metrics_produce_missing_ratios():
    ratios = playtime_ratios(
        playtime_minutes=600,
        hltb_main=None,
        hltb_main_extra=0,
        hltb_completionist=20,
        hltb_all_styles=None,
    )

    assert ratios.main_story is None
    assert ratios.main_extra is None
    assert ratios.completionist == pytest.approx(0.5)
    assert ratios.all_styles is None


def test_negative_playtime_is_rejected():
    with pytest.raises(ValueError):
        playtime_ratios(
            playtime_minutes=-1,
            hltb_main=10,
            hltb_main_extra=20,
            hltb_completionist=30,
            hltb_all_styles=15,
        )


def test_very_short_playtime_has_no_engagement_signal():
    assert playtime_engagement(20) is None


def test_playtime_engagement_increases_with_playtime():
    short = playtime_engagement(60)
    medium = playtime_engagement(600)
    long = playtime_engagement(2400)

    assert short.score < medium.score < long.score
    assert short.confidence < medium.confidence < long.confidence


def test_playtime_engagement_saturates():
    forty_hours = playtime_engagement(40 * 60)
    huge_playtime = playtime_engagement(1000 * 60)

    assert forty_hours == huge_playtime


def test_hltb_engagement_uses_available_ratios():
    ratios = PlaytimeRatios(
        main_story=1.0,
        main_extra=0.5,
        completionist=None,
        all_styles=0.75,
    )

    feedback = hltb_engagement(ratios)

    assert feedback is not None
    assert feedback.score > 0
    assert feedback.confidence > 0


def test_hltb_engagement_caps_extreme_ratios():
    normal = hltb_engagement(
        PlaytimeRatios(
            main_story=1.5,
            main_extra=None,
            completionist=None,
            all_styles=None,
        )
    )

    extreme = hltb_engagement(
        PlaytimeRatios(
            main_story=50.0,
            main_extra=None,
            completionist=None,
            all_styles=None,
        )
    )

    assert normal == extreme


def test_zero_achievement_progress_has_no_engagement_signal():
    assert achievement_engagement(0.0) is None


def test_achievement_engagement_increases_with_progress():
    low = achievement_engagement(0.10)
    medium = achievement_engagement(0.50)
    high = achievement_engagement(1.0)

    assert low.score < medium.score < high.score
    assert low.confidence < medium.confidence < high.confidence


def test_implicit_feedback_requires_play():
    feedback = implicit_feedback(
        playtime_minutes=0,
        hltb_main=10,
        hltb_main_extra=20,
        hltb_completionist=30,
        hltb_all_styles=15,
        achievement_total=100,
        achievements_unlocked=0,
    )

    assert feedback is None


def test_combined_implicit_feedback_does_not_sum_scores():
    playtime = FeedbackSignal(
        score=0.60,
        confidence=0.45,
    )

    hltb = FeedbackSignal(
        score=0.55,
        confidence=0.40,
    )

    achievements = FeedbackSignal(
        score=0.45,
        confidence=0.35,
    )

    feedback = combine_implicit_feedback(
        playtime,
        hltb,
        achievements,
    )

    assert feedback.score <= 0.60
    assert feedback.confidence <= 0.60


def test_multiple_signals_increase_confidence():
    one_signal = combine_implicit_feedback(
        FeedbackSignal(
            score=0.50,
            confidence=0.40,
        ),
        None,
        None,
    )

    two_signals = combine_implicit_feedback(
        FeedbackSignal(
            score=0.50,
            confidence=0.40,
        ),
        FeedbackSignal(
            score=0.50,
            confidence=0.40,
        ),
        None,
    )

    assert two_signals.score == pytest.approx(one_signal.score)

    assert two_signals.confidence > one_signal.confidence


def test_implicit_confidence_is_capped():
    feedback = combine_implicit_feedback(
        FeedbackSignal(
            score=0.60,
            confidence=0.55,
        ),
        FeedbackSignal(
            score=0.55,
            confidence=0.55,
        ),
        FeedbackSignal(
            score=0.50,
            confidence=0.55,
        ),
    )

    assert feedback.confidence == pytest.approx(0.60)


def test_no_implicit_signals_produce_no_feedback():
    assert (
        combine_implicit_feedback(
            None,
            None,
            None,
        )
        is None
    )


def test_meaningful_play_produces_implicit_feedback():
    feedback = implicit_feedback(
        playtime_minutes=600,
        hltb_main=8,
        hltb_main_extra=12,
        hltb_completionist=20,
        hltb_all_styles=10,
        achievement_total=40,
        achievements_unlocked=20,
    )

    assert feedback is not None
    assert feedback.score > 0
    assert feedback.confidence > 0
    assert feedback.confidence <= 0.60
