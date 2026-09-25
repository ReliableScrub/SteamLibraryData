from dataclasses import dataclass, field


@dataclass
class Game:
    app_id: int
    name: str
    playtime_minutes: int

    playtime_2weeks_minutes: int = 0
    last_played_timestamp: int = 0

    genres: list[str] = field(default_factory=list)
    tags: dict[str, int] = field(default_factory=dict)

    metadata_checked: bool = False

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

    achievement_total: int | None = None
    achievements_unlocked: int | None = None
    achievements_checked: bool = False

    manual_status: str | None = None

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
