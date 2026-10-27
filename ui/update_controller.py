import time
from functools import partial

from PySide6.QtCore import QObject, QThread, Signal

from game_classification import GameClassifier
from game_updates import (
    update_achievements,
    update_hltb,
    update_metadata,
)
from storage.database import (
    delete_games_not_in,
    save_game,
    save_library_fields,
    save_steam_classifications,
)
from workers import (
    BatchUpdateWorker,
    SteamClassificationWorker,
    SteamLibraryRefreshWorker,
)

BATCH_SIZE = 5
METADATA_UI_REFRESH_INTERVAL = 10
SECONDS_PER_DAY = 24 * 60 * 60


class SteamClassificationController(QObject):
    status_changed = Signal(str)
    succeeded = Signal()
    failed = Signal(str)
    finished = Signal(bool)

    def __init__(self, steam_api_key, parent=None):
        super().__init__(parent)

        self.steam_api_key = steam_api_key
        self.thread = None
        self.worker = None
        self._games = None
        self._cancel_requested = False

    def is_running(self):
        return self.thread is not None and self.thread.isRunning()

    def start(self, games):
        if self.is_running() or not games:
            return False

        self._games = games
        self._cancel_requested = False
        owned_app_ids = {game.app_id for game in games}
        self.thread = QThread()
        self.worker = SteamClassificationWorker(owned_app_ids, self.steam_api_key)

        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status_changed.connect(self.status_changed.emit)

        self.worker.succeeded.connect(self._save_results)
        self.worker.failed.connect(self.failed.emit)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)

        self.thread.finished.connect(self._thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        return True

    def cancel(self):
        if not self.is_running():
            return

        self._cancel_requested = True

        if self.worker is not None:
            self.worker.cancel()

    def _save_results(self, classifications):
        if self._games is None:
            self.failed.emit("Classification completed without an active game list.")

            return

        expected_app_ids = {game.app_id for game in self._games}
        returned_app_ids = set(classifications)

        if returned_app_ids != expected_app_ids:
            missing = expected_app_ids - returned_app_ids
            unexpected = returned_app_ids - expected_app_ids

            self.failed.emit(
                f"Steam classification returned an incomplete or unexpected result. Missing IDs: {len(missing)}. Unexpected IDs: {len(unexpected)}."
            )

            return

        try:
            updated_at = save_steam_classifications(classifications)
        except Exception as error:  # noqa: BLE001
            self.failed.emit(
                f"Classification completed, but the results could not be saved. {type(error).__name__}: {error}"
            )

            return

        for game in self._games:
            game.steam_type = classifications[game.app_id]
            game.classification_updated_at = updated_at

        self.succeeded.emit()

    def _thread_finished(self):
        was_cancelled = self._cancel_requested
        self.worker = None
        self.thread = None
        self._games = None
        self._cancel_requested = False

        self.finished.emit(was_cancelled)


class SteamLibraryRefreshController(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal(bool)

    def __init__(self, steam_api_key, parent=None):
        super().__init__(parent)

        self.steam_api_key = steam_api_key
        self.thread = None
        self.worker = None
        self._existing_games = None
        self._cancel_requested = False

    def is_running(self):
        return self.thread is not None and self.thread.isRunning()

    def start(self, steam_id, existing_games):
        if self.is_running():
            return False

        self._existing_games = existing_games
        self._cancel_requested = False
        self.thread = QThread()
        self.worker = SteamLibraryRefreshWorker(steam_id, self.steam_api_key)

        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.succeeded.connect(self._process_results)

        self.worker.failed.connect(self.failed.emit)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)

        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        return True

    def cancel(self):
        if not self.is_running():
            return

        self._cancel_requested = True

        if self.worker is not None:
            self.worker.cancel()

    def _process_results(self, steam_games):
        if self._existing_games is None:
            self.failed.emit(
                "Steam library refresh completed without an active library."
            )

            return

        try:
            existing_by_app_id = {game.app_id: game for game in self._existing_games}

            merged_games = []

            for steam_game in steam_games:
                existing_game = existing_by_app_id.get(steam_game.app_id)

                if existing_game is None:
                    game = steam_game
                    save_game(game)
                    merged_games.append(game)
                    continue

                changed = (
                    existing_game.name != steam_game.name
                    or existing_game.playtime_minutes != steam_game.playtime_minutes
                    or existing_game.playtime_2weeks_minutes
                    != steam_game.playtime_2weeks_minutes
                    or existing_game.last_played_timestamp
                    != steam_game.last_played_timestamp
                )

                existing_game.name = steam_game.name
                existing_game.playtime_minutes = steam_game.playtime_minutes
                existing_game.playtime_2weeks_minutes = (
                    steam_game.playtime_2weeks_minutes
                )
                existing_game.last_played_timestamp = steam_game.last_played_timestamp

                if changed:
                    save_library_fields(existing_game)

                merged_games.append(existing_game)

            delete_games_not_in(game.app_id for game in merged_games)

        except Exception as error:  # noqa: BLE001
            self.failed.emit(
                f"Could not save the refreshed Steam library. "
                f"{type(error).__name__}: {error}"
            )

            return

        self.succeeded.emit(merged_games)

    def _thread_finished(self):
        was_cancelled = self._cancel_requested
        self.worker = None
        self.thread = None
        self._existing_games = None
        self._cancel_requested = False

        self.finished.emit(was_cancelled)


class UpdateController(QObject):
    status_changed = Signal(str, str)
    progress_changed = Signal(str, int, int, bool)
    busy_changed = Signal(bool)
    review_available_changed = Signal(bool)
    games_changed = Signal(object)
    data_changed = Signal()
    error = Signal(str, str)
    item_failed = Signal(str)
    failures_changed = Signal(object)

    def __init__(self, games, steam_api_key, parent=None):
        super().__init__(parent)

        self.games = games
        self.steam_api_key = steam_api_key
        self._library = SteamLibraryRefreshController(steam_api_key, self)
        self._classification = SteamClassificationController(steam_api_key, self)
        self._batch_thread = None
        self._batch_worker = None
        self._batch_source = None
        self._combined_threads = {}
        self._combined_workers = {}
        self._combined_progress = {}
        self._combined_total = 0
        self._classification_followup = None
        self._classification_followup_steam_id = None
        self._classification_followup_succeeded = False
        self._cancel_requested = False
        self._failures = []
        self._batch_completed = 0
        self._batch_total = 0

        self._startup_refresh_active = False
        self._startup_steam_id = None
        self._library_refresh_succeeded = False

        self._library.succeeded.connect(self._library_succeeded)
        self._library.failed.connect(self._library_failed)
        self._library.finished.connect(self._library_finished)

        self._classification.status_changed.connect(
            lambda text: self.status_changed.emit("classification", text)
        )
        self._classification.succeeded.connect(self._classification_succeeded)
        self._classification.failed.connect(self._classification_failed)
        self._classification.finished.connect(self._classification_finished)

    def set_games(self, games):
        self.games = games

        self.refresh_statuses()

    def _classifier(self):
        return GameClassifier(self.games)

    def failures(self):
        return list(self._failures)

    def _reset_failures(self):
        self._failures = []
        self.failures_changed.emit([])

    def _record_item_failure(self, source, message):
        self._failures.append(
            {
                "source": source,
                "message": message,
            }
        )

        self.failures_changed.emit(self.failures())
        self.item_failed.emit(message)

    def is_running(self):
        if self._library.is_running() or self._classification.is_running():
            return True

        if self._batch_thread is not None and self._batch_thread.isRunning():
            return True

        return any(thread.isRunning() for thread in self._combined_threads.values())

    def review_available(self):
        return any(game.hltb_match_status == "review" for game in self.games)

    def achievement_pending_count(self):
        classifier = self._classifier()

        return sum(
            1
            for game in self.games
            if not game.achievements_checked and classifier.is_backlog_eligible(game)
        )

    def has_missing_data(self):
        classifier = self._classifier()

        return any(
            game.classification_updated_at is None
            or not game.metadata_checked
            or (
                classifier.is_backlog_eligible(game)
                and (not game.hltb_checked or not game.achievements_checked)
            )
            for game in self.games
        )

    def missing_data_needs_steam_id(self):
        classifier = self._classifier()

        return any(
            not game.achievements_checked and classifier.is_backlog_eligible(game)
            for game in self.games
        )

    @staticmethod
    def _oldest_first(games, timestamp_attr, limit=None):
        ordered = sorted(
            games,
            key=lambda game: (
                getattr(game, timestamp_attr, None) is not None,
                getattr(game, timestamp_attr, None) or 0,
                game.app_id,
            ),
        )

        if limit is None:
            return ordered

        return ordered[: max(int(limit), 0)]

    @staticmethod
    def _oldest_age_text(games, timestamp_attr):
        if not games:
            return "n/a"

        timestamps = [getattr(game, timestamp_attr, None) for game in games]

        if any(timestamp is None for timestamp in timestamps):
            return "pre-timestamp"

        oldest = min(timestamps)
        age_days = max(0, int(time.time() - oldest) // SECONDS_PER_DAY)

        if age_days == 0:
            return "today"

        if age_days == 1:
            return "1 day"

        return f"{age_days} days"

    def metadata_refreshable_games(self):
        return [game for game in self.games if game.metadata_checked]

    def hltb_refreshable_games(self):
        classifier = self._classifier()

        return [
            game
            for game in self.games
            if game.hltb_checked
            and classifier.is_backlog_eligible(game)
            and game.hltb_match_status != "review"
        ]

    def changed_achievement_games(self):
        classifier = self._classifier()
        games = []

        for game in self.games:
            if not game.achievements_checked:
                continue

            if not classifier.is_backlog_eligible(game):
                continue

            checked_playtime = game.achievements_playtime_minutes

            if checked_playtime is None or game.playtime_minutes > checked_playtime:
                games.append(game)

        return sorted(
            games,
            key=lambda game: (
                game.playtime_minutes - (game.achievements_playtime_minutes or 0),
                game.last_played_timestamp or 0,
            ),
            reverse=True,
        )

    def metadata_refresh_count(self):
        return len(self.metadata_refreshable_games())

    def hltb_refresh_count(self):
        return len(self.hltb_refreshable_games())

    def changed_achievement_count(self):
        return len(self.changed_achievement_games())

    def oldest_metadata_games(self, limit=100):
        return self._oldest_first(
            self.metadata_refreshable_games(),
            "metadata_updated_at",
            limit,
        )

    def oldest_hltb_games(self, limit=25):
        return self._oldest_first(
            self.hltb_refreshable_games(),
            "hltb_updated_at",
            limit,
        )

    def start_oldest_metadata_refresh(self, limit=100):
        if self.is_running():
            return "busy"

        games = self.oldest_metadata_games(limit)

        if not games:
            return "nothing"

        return self._start_batch(
            games=games,
            updater=update_metadata,
            source="metadata",
            task_name="Metadata refresh",
            action_text="Refreshing metadata for",
        )

    def start_oldest_hltb_refresh(self, limit=25):
        if self.is_running():
            return "busy"

        games = self.oldest_hltb_games(limit)

        if not games:
            return "nothing"

        return self._start_batch(
            games=games,
            updater=update_hltb,
            source="hltb",
            task_name="HLTB refresh",
            action_text="Refreshing HLTB for",
        )

    def start_changed_achievement_refresh(self, steam_id):
        if self.is_running():
            return "busy"

        games = self.changed_achievement_games()

        if not games:
            return "nothing"

        if steam_id is None:
            return "steam_id_required"

        steam_api_key = self.steam_api_key

        def achievement_updater(game):
            update_achievements(
                game,
                steam_id,
                steam_api_key,
            )

        return self._start_batch(
            games=games,
            updater=achievement_updater,
            source="achievements",
            task_name="Changed achievements",
            action_text="Refreshing changed achievements for",
        )

    def _start_classification_followup(self, mode, steam_id):
        self._classification_followup = mode
        self._classification_followup_steam_id = steam_id
        self._classification_followup_succeeded = False

        self.status_changed.emit(
            "all",
            "Missing Data: Refreshing Steam classification...",
        )
        self.progress_changed.emit("all", 0, 0, True)
        self.status_changed.emit(
            "classification",
            "Steam Classification: Starting...",
        )
        self.progress_changed.emit("classification", 0, 0, True)

        if not self._classification.start(self.games):
            self._classification_followup = None
            self._classification_followup_steam_id = None
            self.progress_changed.emit("classification", 0, 0, False)
            self.progress_changed.emit("all", 0, 0, False)
            return "failed_to_start"

        self.busy_changed.emit(True)
        return "started"

    def refresh_statuses(self):
        self.status_changed.emit("library", f"Steam Library: {len(self.games)} games")

        classifier = self._classifier()
        eligible_games = [
            game for game in self.games if classifier.is_backlog_eligible(game)
        ]

        matched = sum(
            1 for game in eligible_games if game.hltb_match_status == "matched"
        )
        review = sum(1 for game in eligible_games if game.hltb_match_status == "review")
        no_match = sum(
            1 for game in eligible_games if game.hltb_match_status == "no_match"
        )
        hltb_pending = sum(1 for game in eligible_games if not game.hltb_checked)
        hltb_oldest = self._oldest_age_text(
            self.hltb_refreshable_games(),
            "hltb_updated_at",
        )

        self.status_changed.emit(
            "hltb",
            f"HLTB: {matched} matched | {review} review | {no_match} no match | "
            f"{hltb_pending} pending | oldest: {hltb_oldest}",
        )

        metadata_checked = sum(1 for game in self.games if game.metadata_checked)
        metadata_oldest = self._oldest_age_text(
            self.metadata_refreshable_games(),
            "metadata_updated_at",
        )

        self.status_changed.emit(
            "metadata",
            f"Genre / Tag Data: {metadata_checked} / {len(self.games)} checked | "
            f"oldest: {metadata_oldest}",
        )

        achievement_checked = sum(
            1 for game in eligible_games if game.achievements_checked
        )
        changed_achievements = self.changed_achievement_count()

        self.status_changed.emit(
            "achievements",
            f"Achievements: {achievement_checked} / {len(eligible_games)} checked | "
            f"{changed_achievements} changed since last check",
        )

        self.status_changed.emit("classification", self._classification_status_text())
        self.review_available_changed.emit(review > 0)

    def _classification_status_text(self):
        classified_games = [
            game for game in self.games if game.classification_updated_at is not None
        ]

        if not classified_games:
            return "Steam Classification: Not checked"

        counts = {}

        for game in classified_games:
            counts[game.steam_type] = counts.get(game.steam_type, 0) + 1

        parts = [
            f"{counts.get('game', 0)} game",
            f"{counts.get('software', 0)} software",
            f"{counts.get('dlc', 0)} DLC",
        ]

        if counts.get("video", 0):
            parts.append(f"{counts['video']} video")

        if counts.get("hardware", 0):
            parts.append(f"{counts['hardware']} hardware")

        parts.append(f"{counts.get('unknown', 0)} unknown")

        pending = len(self.games) - len(classified_games)

        if pending:
            parts.append(f"{pending} pending")

        return "Steam Classification: " + " | ".join(parts)

    def start_library_refresh(self, steam_id):
        if self.is_running():
            return "busy"

        self._reset_failures()
        self._cancel_requested = False
        self._library_refresh_succeeded = False

        self.status_changed.emit("library", "Steam Library: Refreshing...")
        self.progress_changed.emit("library", 0, 0, True)

        if not self._library.start(steam_id, self.games):
            self.progress_changed.emit("library", 0, 0, False)

            return "failed_to_start"

        self.busy_changed.emit(True)

        return "started"

    def start_startup_refresh(self, steam_id):
        if self.is_running():
            return "busy"

        self._startup_refresh_active = True
        self._startup_steam_id = steam_id

        result = self.start_library_refresh(steam_id)

        if result != "started":
            self._startup_refresh_active = False
            self._startup_steam_id = None

        return result

    def _library_succeeded(self, merged_games):
        self._library_refresh_succeeded = True
        self.games = merged_games

        self.games_changed.emit(merged_games)
        self.refresh_statuses()

    def _library_failed(self, message):
        self._library_refresh_succeeded = False
        self.status_changed.emit("library", "Steam Library: Refresh failed")

        failure_message = f"Steam library refresh failed: {message}"
        self._record_item_failure("library", failure_message)

        if self._startup_refresh_active:
            return

        self.error.emit("Steam Library", f"Library refresh failed:\n{message}")

    def _library_finished(self, was_cancelled):
        self.progress_changed.emit("library", 0, 0, False)

        if was_cancelled:
            self.status_changed.emit("library", "Steam Library: Refresh cancelled")

        startup_refresh = self._startup_refresh_active
        startup_steam_id = self._startup_steam_id
        library_succeeded = self._library_refresh_succeeded

        self._startup_refresh_active = False
        self._startup_steam_id = None
        self._library_refresh_succeeded = False
        self._cancel_requested = False

        if startup_refresh and not was_cancelled and library_succeeded:
            result = self.start_all_missing(startup_steam_id)

            if result == "started":
                return

            result = self.start_recent_achievement_refresh(startup_steam_id)

            if result == "started":
                return

        self.busy_changed.emit(self.is_running())

    def start_classification(self):
        if self.is_running():
            return "busy"

        if not self.games:
            return "nothing"

        self._reset_failures()
        self._cancel_requested = False

        self.status_changed.emit("classification", "Steam Classification: Starting...")
        self.progress_changed.emit("classification", 0, 0, True)

        if not self._classification.start(self.games):
            self.progress_changed.emit("classification", 0, 0, False)

            return "failed_to_start"

        self.busy_changed.emit(True)

        return "started"

    def _classification_succeeded(self):
        if self._classification_followup is not None:
            self._classification_followup_succeeded = True

        self.data_changed.emit()
        self.refresh_statuses()

    def _classification_failed(self, message):
        self.status_changed.emit(
            "classification", "Steam Classification: Refresh failed"
        )
        self._record_item_failure(
            "classification",
            f"Steam classification failed: {message}",
        )
        self.error.emit(
            "Steam Classification", f"Steam classification failed:\n{message}"
        )

    def _classification_finished(self, was_cancelled):
        self.progress_changed.emit("classification", 0, 0, False)

        followup = self._classification_followup
        steam_id = self._classification_followup_steam_id
        succeeded = self._classification_followup_succeeded

        self._classification_followup = None
        self._classification_followup_steam_id = None
        self._classification_followup_succeeded = False

        if followup is not None:
            if was_cancelled:
                self.progress_changed.emit("all", 0, 0, False)
                self.status_changed.emit("all", "Missing Data: Cancelled")
                self._cancel_requested = False
                self.busy_changed.emit(self.is_running())
                return

            if not succeeded:
                self.progress_changed.emit("all", 0, 0, False)
                self.status_changed.emit(
                    "all",
                    "Missing Data: Steam classification failed",
                )
                self._cancel_requested = False
                self.busy_changed.emit(self.is_running())
                return

            self._cancel_requested = False
            self._start_missing_sources(
                steam_id,
                reset_failures=False,
            )
            return

        if was_cancelled:
            self.status_changed.emit(
                "classification",
                "Steam Classification: Cancelled",
            )

        self._cancel_requested = False
        self.busy_changed.emit(self.is_running())

    def start_hltb_batch(self):
        classifier = self._classifier()
        games = [
            game
            for game in self.games
            if not game.hltb_checked and classifier.is_backlog_eligible(game)
        ]

        if not games:
            return "nothing"

        return self._start_batch(
            games=games[:BATCH_SIZE],
            updater=update_hltb,
            source="hltb",
            task_name="HLTB",
            action_text="Searching HLTB for",
        )

    def start_metadata_batch(self):
        games = [game for game in self.games if not game.metadata_checked]

        if not games:
            return "nothing"

        return self._start_batch(
            games=games[:BATCH_SIZE],
            updater=update_metadata,
            source="metadata",
            task_name="Metadata",
            action_text="Getting metadata for",
        )

    def recent_achievement_games(self):
        classifier = self._classifier()
        games = []

        for game in self.games:
            if not classifier.is_backlog_eligible(game):
                continue

            recent_minutes = game.playtime_2weeks_minutes or 0

            if recent_minutes <= 0:
                continue

            checked_playtime = game.achievements_playtime_minutes

            if (
                checked_playtime is not None
                and game.playtime_minutes <= checked_playtime
            ):
                continue

            games.append(game)

        return sorted(
            games,
            key=lambda game: (
                game.playtime_2weeks_minutes or 0,
                game.last_played_timestamp or 0,
            ),
            reverse=True,
        )

    def start_recent_achievement_refresh(self, steam_id):
        games = self.recent_achievement_games()

        if not games:
            return "nothing"

        steam_api_key = self.steam_api_key

        def achievement_updater(game):
            update_achievements(
                game,
                steam_id,
                steam_api_key,
            )

        return self._start_batch(
            games=games,
            updater=achievement_updater,
            source="achievements",
            task_name="Recent achievements",
            action_text="Refreshing recent achievements for",
        )

    def start_achievement_batch(self, steam_id):
        classifier = self._classifier()
        games = [
            game
            for game in self.games
            if not game.achievements_checked and classifier.is_backlog_eligible(game)
        ]

        if not games:
            return "nothing"

        steam_api_key = self.steam_api_key

        def achievement_updater(game):
            update_achievements(game, steam_id, steam_api_key)

        return self._start_batch(
            games=games[:BATCH_SIZE],
            updater=achievement_updater,
            source="achievements",
            task_name="Achievements",
            action_text="Checking achievements for",
        )

    def _start_batch(self, games, updater, source, task_name, action_text):
        if self.is_running():
            return "busy"

        self._reset_failures()
        self._cancel_requested = False
        self._batch_source = source
        self._batch_completed = 0
        self._batch_total = len(games)

        self.progress_changed.emit(source, 0, len(games), True)

        self._batch_thread = QThread()
        self._batch_worker = BatchUpdateWorker(
            games,
            updater,
            task_name,
            action_text,
            cancel_aware=(source == "hltb"),
        )

        self._batch_worker.moveToThread(self._batch_thread)
        self._batch_thread.started.connect(self._batch_worker.run)
        self._batch_worker.status_changed.connect(
            lambda text: self.status_changed.emit(source, text)
        )

        self._batch_worker.progress_changed.connect(self._batch_progress)
        self._batch_worker.item_failed.connect(
            lambda message, source=source: self._record_item_failure(
                source,
                message,
            )
        )
        self._batch_worker.finished.connect(self._batch_thread.quit)
        self._batch_worker.finished.connect(self._batch_worker.deleteLater)

        self._batch_thread.finished.connect(self._batch_finished)
        self._batch_thread.finished.connect(self._batch_thread.deleteLater)
        self._batch_thread.start()
        self.busy_changed.emit(True)

        return "started"

    def _batch_progress(self, completed, total):
        self._batch_completed = completed

        self.progress_changed.emit(
            self._batch_source,
            completed,
            total,
            True,
        )

        if self._batch_source == "metadata":
            self.data_changed.emit()

    def _batch_finished(self):
        source = self._batch_source
        was_cancelled = self._cancel_requested
        processed = self._batch_completed
        failure_count = len(self._failures)

        if source is not None:
            self.progress_changed.emit(source, 0, 0, False)

        self._batch_worker = None
        self._batch_thread = None
        self._batch_source = None
        self._batch_completed = 0
        self._batch_total = 0
        self._cancel_requested = False

        self.data_changed.emit()
        self.refresh_statuses()

        if source is not None and was_cancelled:
            self.status_changed.emit(
                source,
                f"{self._source_title(source)}: Cancelled - "
                f"{processed} processed, {failure_count} failed",
            )
        elif source is not None and failure_count:
            succeeded = max(processed - failure_count, 0)
            self.status_changed.emit(
                source,
                f"{self._source_title(source)}: Complete - "
                f"{succeeded} succeeded, {failure_count} failed",
            )

        self.busy_changed.emit(self.is_running())

    def start_all_missing(self, steam_id=None):
        if self.is_running():
            return "busy"

        if not self.has_missing_data():
            return "nothing"

        if self.missing_data_needs_steam_id() and steam_id is None:
            return "steam_id_required"

        self._reset_failures()
        self._cancel_requested = False

        needs_classification = any(
            game.classification_updated_at is None for game in self.games
        )

        if needs_classification:
            return self._start_classification_followup(
                "missing",
                steam_id,
            )

        return self._start_missing_sources(
            steam_id,
            reset_failures=False,
        )

    def _start_missing_sources(self, steam_id, reset_failures=True):
        if reset_failures:
            self._reset_failures()

        classifier = self._classifier()
        hltb_games = [
            game
            for game in self.games
            if not game.hltb_checked and classifier.is_backlog_eligible(game)
        ]
        metadata_games = [game for game in self.games if not game.metadata_checked]
        achievement_games = [
            game
            for game in self.games
            if not game.achievements_checked and classifier.is_backlog_eligible(game)
        ]

        if not hltb_games and not metadata_games and not achievement_games:
            self.progress_changed.emit("all", 0, 0, False)
            self.status_changed.emit("all", "Missing Data: Complete")
            self.busy_changed.emit(False)
            return "nothing"

        if achievement_games and steam_id is None:
            return "steam_id_required"

        self._combined_total = (
            len(hltb_games) + len(metadata_games) + len(achievement_games)
        )
        self._combined_progress = {}

        if hltb_games:
            self._combined_progress["hltb"] = 0
        if metadata_games:
            self._combined_progress["metadata"] = 0
        if achievement_games:
            self._combined_progress["achievements"] = 0

        self.status_changed.emit("all", "Missing Data: Updating...")
        self.progress_changed.emit(
            "all",
            0,
            self._combined_total,
            True,
        )

        if hltb_games:
            self._start_combined_source(
                source="hltb",
                games=hltb_games,
                updater=update_hltb,
                action_text="Searching HLTB for",
            )

        if metadata_games:
            self._start_combined_source(
                source="metadata",
                games=metadata_games,
                updater=update_metadata,
                action_text="Getting metadata for",
            )

        if achievement_games:
            steam_api_key = self.steam_api_key

            def achievement_updater(game):
                update_achievements(
                    game,
                    steam_id,
                    steam_api_key,
                )

            self._start_combined_source(
                source="achievements",
                games=achievement_games,
                updater=achievement_updater,
                action_text="Checking achievements for",
            )

        self.busy_changed.emit(True)
        return "started"

    def _start_combined_source(
        self,
        source,
        games,
        updater,
        action_text,
    ):
        self.progress_changed.emit(source, 0, len(games), True)

        thread = QThread()
        worker = BatchUpdateWorker(
            games,
            updater,
            self._source_title(source),
            action_text,
            cancel_aware=(source == "hltb"),
        )

        self._combined_threads[source] = thread
        self._combined_workers[source] = worker

        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.status_changed.connect(
            lambda text, source=source: self.status_changed.emit(source, text)
        )
        worker.progress_changed.connect(
            lambda completed, total, source=source: self._combined_source_progress(
                source,
                completed,
                total,
            )
        )
        worker.item_failed.connect(
            lambda message, source=source: self._record_item_failure(
                source,
                message,
            )
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(
            partial(
                self._combined_thread_finished,
                source,
                thread,
            )
        )
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _combined_source_progress(self, source, completed, total):
        self._combined_progress[source] = completed

        self.progress_changed.emit(
            source,
            completed,
            total,
            True,
        )

        overall_completed = sum(self._combined_progress.values())

        self.progress_changed.emit(
            "all",
            overall_completed,
            self._combined_total,
            True,
        )

        if source == "metadata" and (
            completed == 1
            or completed % METADATA_UI_REFRESH_INTERVAL == 0
            or completed == total
        ):
            self.data_changed.emit()

    def _combined_thread_finished(self, source, thread):
        current_thread = self._combined_threads.get(source)

        if current_thread is not thread:
            return

        self._combined_workers.pop(source, None)
        self._combined_threads.pop(source, None)

        if not self._combined_threads:
            self._finish_combined()

    def _finish_combined(self):
        was_cancelled = self._cancel_requested
        processed = sum(self._combined_progress.values())
        failure_count = len(self._failures)

        for source in ("hltb", "metadata", "achievements"):
            self.progress_changed.emit(source, 0, 0, False)

        self.progress_changed.emit("all", 0, 0, False)
        self.data_changed.emit()
        self.refresh_statuses()

        classifier = self._classifier()
        remaining = sum(
            1 for game in self.games if game.classification_updated_at is None
        )
        remaining += sum(
            1
            for game in self.games
            if not game.hltb_checked and classifier.is_backlog_eligible(game)
        )
        remaining += sum(1 for game in self.games if not game.metadata_checked)
        remaining += sum(
            1
            for game in self.games
            if not game.achievements_checked and classifier.is_backlog_eligible(game)
        )

        if was_cancelled:
            self.status_changed.emit(
                "all",
                f"Missing Data: Cancelled - {processed} processed, "
                f"{failure_count} failed, {remaining} still unchecked",
            )
        elif failure_count:
            self.status_changed.emit(
                "all",
                f"Missing Data: Complete with {failure_count} failures "
                f"({remaining} still unchecked)",
            )
        elif remaining == 0:
            self.status_changed.emit("all", "Missing Data: Complete")
        else:
            self.status_changed.emit(
                "all",
                f"Missing Data: {remaining} still unchecked",
            )

        self._combined_progress = {}
        self._combined_total = 0
        self._cancel_requested = False
        self.busy_changed.emit(self.is_running())

    def cancel(self):
        if not self.is_running():
            return

        self._cancel_requested = True

        if self._library.is_running():
            self.status_changed.emit(
                "library",
                "Steam Library: Stopping...",
            )

            self._library.cancel()

        if self._classification.is_running():
            self.status_changed.emit(
                "classification",
                "Steam Classification: Stopping...",
            )

            self._classification.cancel()

        if self._batch_worker is not None:
            if self._batch_source is not None:
                self.status_changed.emit(
                    self._batch_source,
                    f"{self._source_title(self._batch_source)}: Stopping...",
                )

            self._batch_worker.cancel()

        if self._combined_workers:
            self.status_changed.emit(
                "all",
                "Missing Data: Stopping...",
            )

            for worker in self._combined_workers.values():
                worker.cancel()

    @staticmethod
    def _source_title(source):
        return {
            "hltb": "HLTB",
            "metadata": "Metadata",
            "achievements": "Achievements",
        }.get(source, source.title())
