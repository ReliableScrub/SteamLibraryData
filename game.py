from dataclasses import dataclass, field


@dataclass
class Game:
    app_id: int
    name: str
    playtime_minutes: int

    genres: list[str] = field(default_factory=list)
    tags: dict[str, int] = field(default_factory=dict)

    hltb_main: float | None = None
    hltb_main_extra: float | None = None
    hltb_completionist: float | None = None
    hltb_all_styles: float | None = None

    hltb_match_name: str | None = None
    hltb_similarity: float | None = None
    hltb_checked: bool = False

    def preferred_hltb_time(self):
        if self.hltb_completionist:
            return self.hltb_completionist

        if self.hltb_all_styles:
            return self.hltb_all_styles

        if self.hltb_main_extra:
            return self.hltb_main_extra

        if self.hltb_main:
            return self.hltb_main

        return None

    def hltb_needs_review(self, threshold=0.80):
        if not self.hltb_checked:
            return False

        if self.hltb_match_name is None:
            return True

        if self.hltb_similarity is None:
            return True

        return self.hltb_similarity < threshold