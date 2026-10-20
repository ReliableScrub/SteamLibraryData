import math
from dataclasses import dataclass


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

    if rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5.")

    score = (rating - 3) / 2

    return FeedbackSignal(
        score=score,
        confidence=1.0,
    )


def manual_status_feedback(status):
    if status is None:
        return None

    if status == "Completed":
        return FeedbackSignal(
            score=0.35,
            confidence=0.30,
        )

    if status == "Dropped":
        return FeedbackSignal(
            score=-0.45,
            confidence=0.35,
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

    if playtime_hours < 0.5:
        return None

    strength = math.log1p(playtime_hours) / math.log1p(40)
    strength = min(strength, 1.0)

    return FeedbackSignal(
        score=0.60 * strength,
        confidence=0.45 * strength,
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

    capped_ratios = [min(ratio, 1.5) for ratio in positive_ratios]

    average_ratio = sum(capped_ratios) / len(capped_ratios)
    strength = min(average_ratio, 1.0)

    if strength < 0.05:
        return None

    return FeedbackSignal(
        score=0.55 * strength,
        confidence=0.40 * strength,
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
        score=0.45 * strength,
        confidence=0.35 * strength,
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

    confidence += 0.05 * (len(signals) - 1)
    confidence = min(confidence, 0.60)

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
