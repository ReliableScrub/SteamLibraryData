from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from api.achievements_api import (
    SteamAchievementCancelled,
    get_achievement_totals,
)
from api.hltb_api import HLTBError
from api.steam_api import (
    SteamApiError,
    SteamApiKeyRejected,
    SteamClassificationCancelled,
    classify_owned_apps,
    get_owned_games,
)
from api.steamspy_api import SteamSpyError
from game_updates import update_achievement_from_sources
from local_steam import (
    find_steam_directory,
    get_private_app_ids,
)


def _format_worker_error(error):
    if isinstance(
        error,
        (
            SteamApiError,
            SteamApiKeyRejected,
            HLTBError,
            SteamSpyError,
        ),
    ):
        return str(error)

    return f"{type(error).__name__}: {error}"


class RecommendationBuildWorker(QObject):
    succeeded = Signal()
    failed = Signal(str)
    finished = Signal()

    @Slot()
    def run(self):
        try:
            from recommendations.engine import generate_and_save_recommendations

            generate_and_save_recommendations()
            self.succeeded.emit()

        except Exception as error:  # noqa: BLE001
            self.failed.emit(
                f"Recommendation rebuild failed. {type(error).__name__}: {error}"
            )

        finally:
            self.finished.emit()


class SteamLibraryRefreshWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, steam_id, steam_api_key):
        super().__init__()

        self.steam_id = steam_id
        self.steam_api_key = steam_api_key
        self._cancel_requested = Event()

    def cancel(self):
        self._cancel_requested.set()

    @Slot()
    def run(self):
        try:
            if self._cancel_requested.is_set():
                return

            games = get_owned_games(
                self.steam_id,
                self.steam_api_key,
            )

            if not self._cancel_requested.is_set():
                self.succeeded.emit(games)

        except SteamApiError as error:
            if not self._cancel_requested.is_set():
                self.failed.emit(str(error))

        except Exception as error:  # noqa: BLE001
            if not self._cancel_requested.is_set():
                self.failed.emit(
                    "An unexpected error occurred while refreshing the "
                    "Steam library. "
                    f"{type(error).__name__}: {error}"
                )

        finally:
            self.finished.emit()


class SteamClassificationWorker(QObject):
    status_changed = Signal(str)

    # app_type, page_number, owned_matches
    progress_changed = Signal(str, int, int)

    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        owned_app_ids,
        steam_api_key,
    ):
        super().__init__()

        self.owned_app_ids = set(owned_app_ids)
        self.steam_api_key = steam_api_key
        self._cancel_requested = Event()

    def cancel(self):
        self._cancel_requested.set()

    def _report_progress(
        self,
        app_type,
        page_number,
        owned_matches,
    ):
        self.status_changed.emit(
            f"Steam Classification: "
            f"Scanning {app_type} "
            f"(page {page_number}, "
            f"{owned_matches} owned matches)..."
        )

        self.progress_changed.emit(
            app_type,
            page_number,
            owned_matches,
        )

    @Slot()
    def run(self):
        try:
            if self._cancel_requested.is_set():
                return

            classifications = classify_owned_apps(
                owned_app_ids=self.owned_app_ids,
                steam_api_key=self.steam_api_key,
                cancel_requested=self._cancel_requested.is_set,
                progress_callback=self._report_progress,
            )

            if not self._cancel_requested.is_set():
                self.succeeded.emit(classifications)

        except SteamClassificationCancelled:
            # Cancellation is an expected control path,
            # not an update failure.
            pass

        except SteamApiError as error:
            if not self._cancel_requested.is_set():
                self.failed.emit(str(error))

        except Exception as error:  # noqa: BLE001
            if not self._cancel_requested.is_set():
                self.failed.emit(
                    "An unexpected error occurred during Steam classification. "
                    f"{type(error).__name__}: {error}"
                )

        finally:
            self.finished.emit()


class AchievementUpdateWorker(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(int, int)
    item_failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        games,
        steam_id,
        steam_api_key,
        task_name,
        action_text,
    ):
        super().__init__()

        self.games = list(games)
        self.steam_id = steam_id
        self.steam_api_key = steam_api_key
        self.task_name = task_name
        self.action_text = action_text
        self._cancel_requested = Event()

    def cancel(self):
        self._cancel_requested.set()

    @Slot()
    def run(self):
        total = len(self.games)

        try:
            if self._cancel_requested.is_set():
                return

            self.status_changed.emit(
                f"{self.task_name}: Loading Steam achievement totals..."
            )

            try:
                bulk_totals = get_achievement_totals(
                    self.steam_id,
                    self.steam_api_key,
                    (game.app_id for game in self.games),
                    cancel_requested=self._cancel_requested.is_set,
                )

            except SteamAchievementCancelled:
                return

            except (
                SteamApiKeyRejected,
                SteamApiError,
            ) as error:
                if not self._cancel_requested.is_set():
                    self.item_failed.emit(
                        f"{self.task_name} could not load Steam "
                        f"achievement totals: {_format_worker_error(error)}"
                    )

                return

            except Exception as error:  # noqa: BLE001
                if not self._cancel_requested.is_set():
                    self.item_failed.emit(
                        f"{self.task_name} could not prepare achievement updates: "
                        f"{_format_worker_error(error)}"
                    )

                return

            if self._cancel_requested.is_set():
                return

            steam_dir = find_steam_directory()
            private_app_ids = None

            if steam_dir is not None:
                private_app_ids = get_private_app_ids(
                    self.steam_id,
                    steam_dir=steam_dir,
                )

            for index, game in enumerate(
                self.games,
                start=1,
            ):
                if self._cancel_requested.is_set():
                    break

                self.status_changed.emit(f"{self.action_text} {game.name}...")

                try:
                    update_achievement_from_sources(
                        game=game,
                        steam_id=self.steam_id,
                        steam_api_key=self.steam_api_key,
                        bulk_totals=bulk_totals,
                        steam_dir=steam_dir,
                        private_app_ids=private_app_ids,
                    )

                except Exception as error:  # noqa: BLE001
                    if self._cancel_requested.is_set():
                        break

                    self.item_failed.emit(
                        f"{self.task_name} failed for "
                        f"{game.name}: "
                        f"{_format_worker_error(error)}"
                    )

                self.progress_changed.emit(
                    index,
                    total,
                )

                if self._cancel_requested.is_set():
                    break

        finally:
            self.finished.emit()


class BatchUpdateWorker(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(int, int)
    item_failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        games,
        updater,
        task_name,
        action_text,
        cancel_aware=False,
    ):
        super().__init__()

        self.games = games
        self.updater = updater
        self.task_name = task_name
        self.action_text = action_text
        self.cancel_aware = cancel_aware
        self._cancel_requested = Event()

    def cancel(self):
        self._cancel_requested.set()

    @Slot()
    def run(self):
        total = len(self.games)

        try:
            for index, game in enumerate(self.games, start=1):
                if self._cancel_requested.is_set():
                    break

                self.status_changed.emit(f"{self.action_text} {game.name}...")

                try:
                    if self.cancel_aware:
                        self.updater(
                            game,
                            cancel_requested=self._cancel_requested.is_set,
                        )
                    else:
                        self.updater(game)

                except Exception as error:  # noqa: BLE001
                    if self._cancel_requested.is_set():
                        break

                    self.item_failed.emit(
                        f"{self.task_name} failed for "
                        f"{game.name}: "
                        f"{_format_worker_error(error)}"
                    )

                self.progress_changed.emit(index, total)

                if self._cancel_requested.is_set():
                    break

        finally:
            self.finished.emit()
