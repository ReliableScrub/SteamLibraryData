import threading
import time
from typing import ClassVar

import requests
from fake_useragent import UserAgent
from howlongtobeatpy import HowLongToBeat, SearchModifiers
from howlongtobeatpy.HTMLRequests import HTMLRequests

FALLBACK_USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


class HLTBClient:
    AUTH_REFRESH_STATUS_CODES: ClassVar[set[int]] = {
        400,
        401,
        403,
        404,
    }

    def __init__(self):
        self._session = requests.Session()
        self._parser = HowLongToBeat(0.0)

        self._user_agent = None
        self._search_url = None
        self._auth_struct = None
        self._auth_initialized = False

        # Search requests are deliberately serialized. HLTB was less reliable
        # when multiple searches were sent concurrently during bulk updates.
        self._request_lock = threading.Lock()
        self._stats_lock = threading.Lock()

        self._stats = {
            "auth_refreshes": 0,
            "auth_refresh_seconds": 0.0,
            "search_posts": 0,
            "search_post_seconds": 0.0,
            "auth_retries": 0,
            "request_failures": 0,
        }

    def reset_stats(self):
        with self._stats_lock:
            for key in self._stats:
                if key.endswith("_seconds"):
                    self._stats[key] = 0.0
                else:
                    self._stats[key] = 0

    def get_stats(self):
        with self._stats_lock:
            return self._stats.copy()

    def reset(self):
        with self._request_lock:
            self._session.close()
            self._session = requests.Session()

            self._user_agent = None
            self._search_url = None
            self._auth_struct = None
            self._auth_initialized = False

        self.reset_stats()

    def _increment_stat(
        self,
        key,
        amount=1,
    ):
        with self._stats_lock:
            self._stats[key] += amount

    def _add_seconds(
        self,
        key,
        seconds,
    ):
        with self._stats_lock:
            self._stats[key] += seconds

    def _get_user_agent(self):
        if self._user_agent is not None:
            return self._user_agent

        try:
            self._user_agent = UserAgent().random.strip()

        except Exception:  # noqa: BLE001 - external user-agent provider boundary
            self._user_agent = FALLBACK_USER_AGENT

        return self._user_agent

    def _refresh_auth(self):
        refresh_start = time.perf_counter()
        self._increment_stat("auth_refreshes")

        user_agent = self._get_user_agent()

        try:
            search_info = HTMLRequests.send_website_request_getcode(user_agent)

            search_path = None

            if search_info is not None and search_info.search_url is not None:
                search_path = search_info.search_url

            auth_struct = HTMLRequests.send_website_get_auth_token(
                search_path,
                user_agent,
            )

        except requests.RequestException:
            self._increment_stat("request_failures")

            self._auth_struct = None
            self._auth_initialized = False

            return False

        finally:
            refresh_seconds = time.perf_counter() - refresh_start

            self._add_seconds(
                "auth_refresh_seconds",
                refresh_seconds,
            )

        if search_path is not None:
            self._search_url = HTMLRequests.BASE_URL + search_path

        else:
            self._search_url = HTMLRequests.SEARCH_URL

        self._auth_struct = auth_struct
        self._auth_initialized = True

        return True

    def _post_search(
        self,
        game_name,
        search_modifiers,
        page,
    ):
        user_agent = self._get_user_agent()

        headers = HTMLRequests.get_search_request_headers(
            self._auth_struct,
            user_agent,
        )

        payload = HTMLRequests.get_search_request_data(
            game_name,
            search_modifiers,
            page,
            self._auth_struct,
        )

        post_start = time.perf_counter()
        self._increment_stat("search_posts")

        try:
            response = self._session.post(
                self._search_url,
                headers=headers,
                data=payload,
                timeout=60,
            )

        except requests.RequestException as error:
            print(f"HLTB transport exception for {game_name}: {error}")

            self._increment_stat("request_failures")

            return None

        finally:
            post_seconds = time.perf_counter() - post_start

            self._add_seconds(
                "search_post_seconds",
                post_seconds,
            )

        return response

    def _parse_results(
        self,
        game_name,
        response_text,
        similarity_case_sensitive,
    ):
        return self._parser._HowLongToBeat__parse_web_result(
            game_name,
            response_text,
            input_similarity_case_sensitive=(similarity_case_sensitive),
        )

    def search(
        self,
        game_name,
        search_modifiers=SearchModifiers.NONE,
        similarity_case_sensitive=True,
        page=1,
    ):
        if game_name is None or len(game_name) == 0:
            return None

        with self._request_lock:
            if not self._auth_initialized and not self._refresh_auth():
                return None

            response = self._post_search(
                game_name,
                search_modifiers,
                page,
            )

            if response is None:
                return None

            if response.status_code == 200:
                return self._parse_results(
                    game_name,
                    response.text,
                    similarity_case_sensitive,
                )

            if response.status_code == 429:
                print(f"HLTB rate limited: {game_name}")

                self._increment_stat("request_failures")

                return None

            if response.status_code not in self.AUTH_REFRESH_STATUS_CODES:
                print(
                    f"HLTB transport response: {response.status_code} for {game_name}"
                )

                self._increment_stat("request_failures")

                return None

            # The cached search URL/auth may have expired or changed. Refresh
            # both once, then retry the same search. Higher-level retry logic
            # still handles transient server/network failures.
            self._increment_stat("auth_retries")

            self._auth_initialized = False

            if not self._refresh_auth():
                return None

            response = self._post_search(
                game_name,
                search_modifiers,
                page,
            )

            if response is None:
                return None

            if response.status_code == 200:
                return self._parse_results(
                    game_name,
                    response.text,
                    similarity_case_sensitive,
                )

            if response.status_code == 429:
                print(f"HLTB rate limited after auth refresh: {game_name}")

            else:
                print(
                    f"HLTB transport response after auth refresh: "
                    f"{response.status_code} "
                    f"for {game_name}"
                )

            self._increment_stat("request_failures")

            return None


HLTB_CLIENT = HLTBClient()
