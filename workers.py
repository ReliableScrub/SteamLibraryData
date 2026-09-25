from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from api.steam_api import get_owned_games
from storage.database import save_game


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

        except Exception as error:
            if not self._cancel_requested.is_set():
                self.failed.emit(f"{type(error).__name__}: {error}")

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
    ):
        super().__init__()

        self.games = games
        self.updater = updater
        self.task_name = task_name
        self.action_text = action_text
        self._cancel_requested = Event()

    def cancel(self):
        self._cancel_requested.set()

    @Slot()
    def run(self):
        total = len(self.games)

        try:
            for index, game in enumerate(
                self.games,
                start=1,
            ):
                if self._cancel_requested.is_set():
                    break

                self.status_changed.emit(f"{self.action_text} {game.name}...")

                try:
                    # Finish the current item cleanly even if
                    # cancellation is requested while it runs.
                    self.updater(game)
                    save_game(game)

                except Exception as error:
                    self.item_failed.emit(
                        f"{self.task_name} failed for "
                        f"{game.name}: "
                        f"{type(error).__name__}: {error}"
                    )

                self.progress_changed.emit(
                    index,
                    total,
                )

                if self._cancel_requested.is_set():
                    break

        finally:
            self.finished.emit()


class ResultBatchWorker(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(str, int, int)
    result_ready = Signal(object, object)
    item_failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        games,
        fetcher,
        task_name,
        action_text,
    ):
        super().__init__()

        self.games = games
        self.fetcher = fetcher
        self.task_name = task_name
        self.action_text = action_text
        self._cancel_requested = Event()

    def cancel(self):
        self._cancel_requested.set()

    @Slot()
    def run(self):
        total = len(self.games)

        try:
            for index, game in enumerate(
                self.games,
                start=1,
            ):
                if self._cancel_requested.is_set():
                    break

                self.status_changed.emit(f"{self.action_text} {game.name}...")

                try:
                    # If cancellation happens during the fetch,
                    # keep the result for this already-started item,
                    # then stop before starting another one.
                    result = self.fetcher(game)

                    self.result_ready.emit(
                        game,
                        result,
                    )

                except Exception as error:
                    self.item_failed.emit(
                        f"{self.task_name} failed for "
                        f"{game.name}: "
                        f"{type(error).__name__}: {error}"
                    )

                self.progress_changed.emit(
                    self.task_name,
                    index,
                    total,
                )

                if self._cancel_requested.is_set():
                    break

        finally:
            self.finished.emit()


class ConcurrentResultWorker(QObject):
    status_changed = Signal(str)
    progress_changed = Signal(str, int, int)
    result_ready = Signal(object, object)
    item_failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        games,
        fetcher,
        task_name,
        action_text,
        max_workers=4,
    ):
        super().__init__()

        self.games = games
        self.fetcher = fetcher
        self.task_name = task_name
        self.action_text = action_text
        self.max_workers = max(
            1,
            max_workers,
        )
        self._cancel_requested = Event()

    def cancel(self):
        self._cancel_requested.set()

    def _submit_next(
        self,
        executor,
        game_iterator,
        futures,
    ):
        if self._cancel_requested.is_set():
            return False

        try:
            game = next(game_iterator)
        except StopIteration:
            return False

        self.status_changed.emit(f"{self.action_text} {game.name}...")

        future = executor.submit(
            self.fetcher,
            game,
        )

        futures[future] = game

        return True

    @Slot()
    def run(self):
        total = len(self.games)
        completed = 0
        game_iterator = iter(self.games)
        futures = {}

        executor = ThreadPoolExecutor(max_workers=self.max_workers)

        try:
            for _ in range(self.max_workers):
                if not self._submit_next(
                    executor,
                    game_iterator,
                    futures,
                ):
                    break

            while futures:
                done, _ = wait(
                    futures,
                    return_when=FIRST_COMPLETED,
                )

                for future in done:
                    game = futures.pop(future)
                    completed += 1

                    if not future.cancelled():
                        try:
                            result = future.result()

                            # Preserve the result for any request
                            # that was already in flight.
                            self.result_ready.emit(
                                game,
                                result,
                            )

                        except Exception as error:
                            self.item_failed.emit(
                                f"{self.task_name} failed for "
                                f"{game.name}: "
                                f"{type(error).__name__}: {error}"
                            )

                    self.progress_changed.emit(
                        self.task_name,
                        completed,
                        total,
                    )

                    if not self._cancel_requested.is_set():
                        self._submit_next(
                            executor,
                            game_iterator,
                            futures,
                        )

                if self._cancel_requested.is_set():
                    for future in futures:
                        future.cancel()

                    # Already-running futures cannot be killed
                    # safely. They are allowed to finish, but no
                    # new games are submitted.
                    running = {
                        future: game
                        for future, game in futures.items()
                        if not future.cancelled()
                    }

                    futures = running

                    if not futures:
                        break

        finally:
            executor.shutdown(
                wait=True,
                cancel_futures=True,
            )
            self.finished.emit()
