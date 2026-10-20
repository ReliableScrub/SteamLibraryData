import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Feedback model configuration
# ---------------------------------------------------------------------------
#
# FeedbackSignal:
#   score      = preference direction/strength (-1 dislike to +1 like)
#   confidence = how much weight to give that score (not a probability)
#
# FIXED SEMANTICS
# ----------------
# The 1-5 star scale is part of the database/UI contract:
#
#   ★      = -1.00
#   ★★     = -0.50
#   ★★★    =  0.00
#   ★★★★   = +0.50
#   ★★★★★  = +1.00
#
# Explicit ratings override inferred feedback.
# Unplayed games produce no implicit feedback.
# Missing achievements or HLTB data mean "no evidence", not negative evidence.
#
# TUNABLE MODEL PARAMETERS
# ------------------------
# Manual status:
#   COMPLETED_* / DROPPED_* control the influence of those manual statuses.
#
# Playtime:
#   PLAYTIME_MIN_HOURS        = when playtime starts counting as evidence
#   PLAYTIME_SATURATION_HOURS = when extra hours stop adding much information
#   PLAYTIME_MAX_*            = maximum playtime score/confidence
#
# HLTB:
#   HLTB_RATIO_CAP        = limits extreme playtime/HLTB ratios
#   HLTB_MIN_STRENGTH     = ignores negligible HLTB-relative engagement
#   HLTB_MAX_*            = maximum HLTB score/confidence
#
# Achievements:
#   ACHIEVEMENT_MAX_*     = maximum achievement score/confidence
#
# Combined implicit feedback:
#   IMPLICIT_CONFIDENCE_BONUS = bonus for multiple agreeing evidence sources
#   IMPLICIT_MAX_CONFIDENCE   = ceiling for inferred feedback confidence
#
# ---------------------------------------------------------------------------

# Explicit rating parameters, pretty much don't touch cause they'll break things.
RATING_MIN = 1
RATING_MAX = 5
RATING_NEUTRAL = 3
RATING_SCORE_SCALE = 2
RATING_CONFIDENCE = 1.0

# Manual status parameters
COMPLETED_SCORE = 0.35
COMPLETED_CONFIDENCE = 0.30

DROPPED_SCORE = -0.45
DROPPED_CONFIDENCE = 0.35

# Playtime engagement parameters
PLAYTIME_MIN_HOURS = 0.5
PLAYTIME_SATURATION_HOURS = 40
PLAYTIME_MAX_SCORE = 0.60
PLAYTIME_MAX_CONFIDENCE = 0.45

# HLTB engagement parameters
HLTB_RATIO_CAP = 1.5
HLTB_MIN_STRENGTH = 0.05
HLTB_MAX_SCORE = 0.55
HLTB_MAX_CONFIDENCE = 0.40

# Achievement engagement parameters
ACHIEVEMENT_MAX_SCORE = 0.45
ACHIEVEMENT_MAX_CONFIDENCE = 0.35

# Combined implicit feedback parameters
IMPLICIT_CONFIDENCE_BONUS = 0.05
IMPLICIT_MAX_CONFIDENCE = 0.60


@dataclass(frozen=True)
class FeedbackSignal:
    score: float
    confidence: float


@dataclass(frozen=True)
class PlaytimeRatios:
    main_story: float | None
    main_extra: float | None
    completionist: float | None
    all_styles: float | None


def explicit_rating_feedback(rating):
    if rating is None:
        return None

    if rating < RATING_MIN or rating > RATING_MAX:
        raise ValueError(f"Rating must be between {RATING_MIN} and {RATING_MAX}.")

    score = (rating - RATING_NEUTRAL) / RATING_SCORE_SCALE

    return FeedbackSignal(
        score=score,
        confidence=RATING_CONFIDENCE,
    )


def manual_status_feedback(status):
    if status is None:
        return None

    if status == "Completed":
        return FeedbackSignal(
            score=COMPLETED_SCORE,
            confidence=COMPLETED_CONFIDENCE,
        )

    if status == "Dropped":
        return FeedbackSignal(
            score=DROPPED_SCORE,
            confidence=DROPPED_CONFIDENCE,
        )

    if status == "On Hold":
        return None

    raise ValueError(f"Unknown manual status: {status}")


def achievement_progress(total, unlocked):
    if total is None or unlocked is None:
        return None

    if total < 0 or unlocked < 0:
        raise ValueError("Achievement counts cannot be negative.")

    if unlocked > total:
        raise ValueError("Unlocked achievements cannot exceed total achievements.")

    if total == 0:
        return None

    return unlocked / total


def playtime_ratios(
    playtime_minutes,
    hltb_main,
    hltb_main_extra,
    hltb_completionist,
    hltb_all_styles,
):
    if playtime_minutes < 0:
        raise ValueError("Playtime cannot be negative.")

    playtime_hours = playtime_minutes / 60

    def ratio(hltb_hours):
        if hltb_hours is None or hltb_hours <= 0:
            return None

        return playtime_hours / hltb_hours

    return PlaytimeRatios(
        main_story=ratio(hltb_main),
        main_extra=ratio(hltb_main_extra),
        completionist=ratio(hltb_completionist),
        all_styles=ratio(hltb_all_styles),
    )


def playtime_engagement(playtime_minutes):
    if playtime_minutes < 0:
        raise ValueError("Playtime cannot be negative.")

    playtime_hours = playtime_minutes / 60

    if playtime_hours < PLAYTIME_MIN_HOURS:
        return None

    strength = math.log1p(playtime_hours) / math.log1p(PLAYTIME_SATURATION_HOURS)

    strength = min(strength, 1.0)

    return FeedbackSignal(
        score=PLAYTIME_MAX_SCORE * strength,
        confidence=PLAYTIME_MAX_CONFIDENCE * strength,
    )


def hltb_engagement(ratios):
    available_ratios = [
        ratio
        for ratio in (
            ratios.main_story,
            ratios.main_extra,
            ratios.completionist,
            ratios.all_styles,
        )
        if ratio is not None
    ]

    if not available_ratios:
        return None

    positive_ratios = [ratio for ratio in available_ratios if ratio > 0]

    if not positive_ratios:
        return None

    capped_ratios = [min(ratio, HLTB_RATIO_CAP) for ratio in positive_ratios]

    average_ratio = sum(capped_ratios) / len(capped_ratios)

    strength = min(average_ratio, 1.0)

    if strength < HLTB_MIN_STRENGTH:
        return None

    return FeedbackSignal(
        score=HLTB_MAX_SCORE * strength,
        confidence=HLTB_MAX_CONFIDENCE * strength,
    )


def achievement_engagement(progress):
    if progress is None:
        return None

    if progress < 0 or progress > 1:
        raise ValueError("Achievement progress must be between 0 and 1.")

    if progress == 0:
        return None

    strength = math.sqrt(progress)

    return FeedbackSignal(
        score=ACHIEVEMENT_MAX_SCORE * strength,
        confidence=ACHIEVEMENT_MAX_CONFIDENCE * strength,
    )


def combine_implicit_feedback(
    playtime_feedback,
    hltb_feedback,
    achievement_feedback,
):
    signals = [
        signal
        for signal in (
            playtime_feedback,
            hltb_feedback,
            achievement_feedback,
        )
        if signal is not None
    ]

    if not signals:
        return None

    total_confidence = sum(signal.confidence for signal in signals)

    if total_confidence <= 0:
        return None

    score = (
        sum(signal.score * signal.confidence for signal in signals) / total_confidence
    )

    confidence = max(signal.confidence for signal in signals)

    confidence += IMPLICIT_CONFIDENCE_BONUS * (len(signals) - 1)

    confidence = min(
        confidence,
        IMPLICIT_MAX_CONFIDENCE,
    )

    return FeedbackSignal(
        score=score,
        confidence=confidence,
    )


def implicit_feedback(
    playtime_minutes,
    hltb_main,
    hltb_main_extra,
    hltb_completionist,
    hltb_all_styles,
    achievement_total,
    achievements_unlocked,
):
    if playtime_minutes < 0:
        raise ValueError("Playtime cannot be negative.")

    if playtime_minutes == 0:
        return None

    playtime_feedback = playtime_engagement(playtime_minutes)

    ratios = playtime_ratios(
        playtime_minutes,
        hltb_main,
        hltb_main_extra,
        hltb_completionist,
        hltb_all_styles,
    )

    hltb_feedback = hltb_engagement(ratios)

    progress = achievement_progress(
        achievement_total,
        achievements_unlocked,
    )

    achievement_feedback = achievement_engagement(progress)

    return combine_implicit_feedback(
        playtime_feedback,
        hltb_feedback,
        achievement_feedback,
    )


def combine_manual_and_implicit_feedback(
    manual_feedback,
    implicit_feedback_signal,
):
    signals = [
        signal
        for signal in (
            manual_feedback,
            implicit_feedback_signal,
        )
        if signal is not None
    ]

    if not signals:
        return None

    if len(signals) == 1:
        return signals[0]

    total_confidence = sum(signal.confidence for signal in signals)

    score = (
        sum(signal.score * signal.confidence for signal in signals) / total_confidence
    )

    confidence = max(signal.confidence for signal in signals)

    return FeedbackSignal(
        score=score,
        confidence=confidence,
    )


def final_feedback(
    rating,
    manual_status,
    playtime_minutes,
    hltb_main,
    hltb_main_extra,
    hltb_completionist,
    hltb_all_styles,
    achievement_total,
    achievements_unlocked,
):
    explicit = explicit_rating_feedback(rating)

    if explicit is not None:
        return explicit

    manual = manual_status_feedback(manual_status)

    implicit = implicit_feedback(
        playtime_minutes=playtime_minutes,
        hltb_main=hltb_main,
        hltb_main_extra=hltb_main_extra,
        hltb_completionist=hltb_completionist,
        hltb_all_styles=hltb_all_styles,
        achievement_total=achievement_total,
        achievements_unlocked=achievements_unlocked,
    )

    return combine_manual_and_implicit_feedback(
        manual,
        implicit,
    )
