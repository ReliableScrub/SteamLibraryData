import re

GENRE_CANONICAL_NAMES = {
    "free to play": "Free To Play",
}


def canonical_genre_name(name):
    if not isinstance(name, str):
        return ""

    cleaned = " ".join(name.split())

    if not cleaned:
        return ""

    return GENRE_CANONICAL_NAMES.get(
        cleaned.casefold(),
        cleaned,
    )


def canonical_feature_key(name):
    if not isinstance(name, str):
        return ""

    return " ".join(name.split()).casefold()


def is_bonus_content_title(name):
    if not isinstance(name, str):
        return False

    normalized = " ".join(name.split()).casefold()

    return bool(
        re.search(
            r"\bbonus\s+content\b",
            normalized,
        )
    )


class GameClassifier:
    def __init__(self, games=()):
        self.games = list(games)
        self.software_exclusive_genre_keys = set()
        self.software_exclusive_tag_keys = set()
        self._build_reference_sets()

    def _build_reference_sets(self):
        game_genre_keys = set()
        software_genre_keys = set()
        game_tag_keys = set()
        software_tag_keys = set()

        for game in self.games:
            if is_bonus_content_title(getattr(game, "name", "")):
                continue

            raw_type = getattr(game, "steam_type", "unknown") or "unknown"

            if raw_type not in {"game", "software"}:
                continue

            genre_target = (
                game_genre_keys if raw_type == "game" else software_genre_keys
            )
            tag_target = game_tag_keys if raw_type == "game" else software_tag_keys

            for genre in getattr(game, "genres", []) or []:
                display = canonical_genre_name(genre)

                if display:
                    genre_target.add(canonical_feature_key(display))

            for tag in getattr(game, "tags", {}) or {}:
                key = canonical_feature_key(tag)

                if key:
                    tag_target.add(key)

        self.software_exclusive_genre_keys = software_genre_keys - game_genre_keys
        self.software_exclusive_tag_keys = software_tag_keys - game_tag_keys

    def inferred_steam_type(self, game):
        is_test_build = getattr(game, "is_test_build", None)

        if callable(is_test_build) and is_test_build():
            return "test"

        if is_bonus_content_title(getattr(game, "name", "")):
            return "bonus"

        raw_type = getattr(game, "steam_type", "unknown") or "unknown"

        if raw_type != "unknown":
            return raw_type

        if not getattr(game, "metadata_checked", False):
            return "unknown"

        genre_keys = {
            canonical_feature_key(canonical_genre_name(genre))
            for genre in getattr(game, "genres", []) or []
            if canonical_genre_name(genre)
        }
        tag_keys = {
            canonical_feature_key(tag)
            for tag in getattr(game, "tags", {}) or {}
            if canonical_feature_key(tag)
        }

        if (
            genre_keys & self.software_exclusive_genre_keys
            or tag_keys & self.software_exclusive_tag_keys
        ):
            return "software"

        return "game"

    def display_steam_type(self, game):
        raw_type = getattr(game, "steam_type", "unknown") or "unknown"
        inferred = self.inferred_steam_type(game)

        if inferred == "test":
            if raw_type == "unknown":
                return "Unknown (Test / Beta)"

            return "Test / Beta"

        if inferred == "bonus":
            return "Bonus Content"

        if raw_type == "unknown":
            if inferred == "game":
                return "Unknown (Game)"

            if inferred == "software":
                return "Unknown (Software)"

            return "Unknown"

        names = {
            "game": "Game",
            "software": "Software",
            "dlc": "DLC",
            "video": "Video",
            "hardware": "Hardware",
        }

        return names.get(raw_type, raw_type.replace("_", " ").title())

    def is_backlog_eligible(self, game):
        return self.inferred_steam_type(game) not in {
            "test",
            "bonus",
            "software",
            "dlc",
            "video",
            "hardware",
        }
