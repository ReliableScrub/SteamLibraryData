import re
from dataclasses import dataclass, field

TEST_BUILD_PHRASES = (
    "public test",
    "public testing",
    "test server",
    "test client",
    "test realm",
    "test environment",
    "test build",
    "testing beta",
    "beta testing",
    "testing alpha",
    "alpha testing",
    "public beta",
    "public alpha",
    "open beta",
    "closed beta",
    "open alpha",
    "closed alpha",
    "beta test",
    "beta server",
    "beta client",
    "beta build",
    "alpha test",
    "alpha server",
    "alpha client",
    "alpha build",
    "technical test",
    "technical beta",
    "technical alpha",
    "playtest",
    "play test",
)


def normalize_test_build_title(title):
    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        (title or "").casefold(),
    )

    return " ".join(normalized.split())


@dataclass
class Game:
    app_id: int
    name: str
    playtime_minutes: int

    playtime_2weeks_minutes: int = 0
    last_played_timestamp: int = 0

    steam_type: str = "unknown"
    classification_updated_at: int | None = None

    genres: list[str] = field(default_factory=list)
    tags: dict[str, int] = field(default_factory=dict)

    metadata_checked: bool = False
    metadata_updated_at: int | None = None
    steamspy_positive: int | None = None
    steamspy_negative: int | None = None
    steam_short_description: str | None = None

    hltb_main: float | None = None
    hltb_main_extra: float | None = None
    hltb_completionist: float | None = None
    hltb_all_styles: float | None = None

    hltb_match_name: str | None = None
    hltb_similarity: float | None = None

    hltb_game_id: int | None = None
    hltb_web_link: str | None = None
    hltb_match_status: str | None = None

    hltb_checked: bool = False
    hltb_updated_at: int | None = None

    achievement_total: int | None = None
    achievements_unlocked: int | None = None
    achievements_checked: bool = False
    achievements_updated_at: int | None = None
    achievements_playtime_minutes: int | None = None

    manual_status: str | None = None

    def is_test_build(self):
        normalized_name = normalize_test_build_title(self.name)

        if any(phrase in normalized_name for phrase in TEST_BUILD_PHRASES):
            return True

        # Some legacy/test Steam entries are only identifiable by a trailing
        # "Beta" in the title. Restrict this heuristic to unknown Steam types
        # so normal released games are not reclassified by name alone.
        return bool(self.steam_type == "unknown" and normalized_name.endswith(" beta"))

    def hltb_time(self, metric):
        if metric == "Main Story":
            return self.hltb_main

        if metric == "Main + Extra":
            return self.hltb_main_extra

        if metric == "Completionist":
            return self.hltb_completionist

        if metric == "All Styles":
            return self.hltb_all_styles

        return None

    def preferred_hltb_time(self):
        for value in (
            self.hltb_completionist,
            self.hltb_all_styles,
            self.hltb_main_extra,
            self.hltb_main,
        ):
            if value is not None:
                return value

        return None

    def hltb_needs_review(self, threshold=0.80):
        if not self.hltb_checked:
            return False

        if self.hltb_match_name is None:
            return True

        if self.hltb_similarity is None:
            return True

        return self.hltb_similarity < threshold

    def achievement_percent(self):
        if not self.achievement_total:
            return None

        return (self.achievements_unlocked / self.achievement_total) * 100

    def effective_status(self):
        achievement_total = self.achievement_total or 0
        achievements_unlocked = self.achievements_unlocked or 0
        recent_minutes = self.playtime_2weeks_minutes or 0
        playtime_minutes = self.playtime_minutes or 0

        if self.manual_status == "Completed":
            return "Completed"

        if self.manual_status == "Dropped":
            return "Dropped"

        if self.manual_status == "On Hold":
            return "On Hold"

        if achievement_total > 0 and achievements_unlocked >= achievement_total:
            return "Completed"

        if recent_minutes > 0:
            return "Playing"

        if playtime_minutes == 0:
            return "Backlog"

        return "Inactive"

    def is_backlog_eligible(self):
        if self.is_test_build():
            return False

        return self.steam_type not in {
            "software",
            "dlc",
            "video",
            "hardware",
        }
