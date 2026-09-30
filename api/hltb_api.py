import random
import re
import threading
import time
import unicodedata

from howlongtobeatpy import SearchModifiers

from api.hltb_client import HLTB_CLIENT
from api.hltb_page import get_hltb_detail_steam_app_id

HLTB_STATS_LOCK = threading.Lock()
HLTB_CACHE_LOCK = threading.Lock()

HLTB_STATS = {
    "games_attempted": 0,
    "search_requests": 0,
    "detail_requests": 0,
    "retries": 0,
    "query_cache_hits": 0,
    "title_cache_hits": 0,
    "steam_cache_hits": 0,
    "detail_cache_hits": 0,
    "search_seconds": 0.0,
    "detail_seconds": 0.0,
    "game_seconds": 0.0,
}

# These caches live for the lifetime of the process. A bulk HLTB update can
# therefore reuse useful records returned while processing earlier games.
HLTB_QUERY_CACHE = {}
HLTB_TITLE_CACHE = {}
HLTB_TOKEN_CACHE = {}
HLTB_STEAM_CANDIDATE_CACHE = {}
HLTB_DETAIL_STEAM_CACHE = {}

CACHE_MISS = object()


def reset_hltb_stats():
    with HLTB_STATS_LOCK:
        for key in HLTB_STATS:
            if key.endswith("_seconds"):
                HLTB_STATS[key] = 0.0
            else:
                HLTB_STATS[key] = 0

    HLTB_CLIENT.reset_stats()


def get_hltb_stats():
    with HLTB_STATS_LOCK:
        return HLTB_STATS.copy()


def reset_hltb_cache():
    with HLTB_CACHE_LOCK:
        HLTB_QUERY_CACHE.clear()
        HLTB_TITLE_CACHE.clear()
        HLTB_TOKEN_CACHE.clear()
        HLTB_STEAM_CANDIDATE_CACHE.clear()
        HLTB_DETAIL_STEAM_CACHE.clear()


def reset_hltb_transport():
    HLTB_CLIENT.reset()


def increment_hltb_stat(key, amount=1):
    with HLTB_STATS_LOCK:
        HLTB_STATS[key] += amount


def print_hltb_stats():
    stats = get_hltb_stats()
    transport_stats = HLTB_CLIENT.get_stats()

    games = stats["games_attempted"]
    searches = stats["search_requests"]
    details = stats["detail_requests"]
    retries = stats["retries"]
    query_cache_hits = stats["query_cache_hits"]
    title_cache_hits = stats["title_cache_hits"]
    steam_cache_hits = stats["steam_cache_hits"]
    detail_cache_hits = stats["detail_cache_hits"]

    average_searches = searches / games if games else 0
    average_details = details / games if games else 0
    average_search_time = stats["search_seconds"] / searches if searches else 0
    average_detail_time = stats["detail_seconds"] / details if details else 0

    print()
    print("HLTB performance:")
    print(f"  Games attempted: {games}")
    print(f"  Search requests: {searches}")
    print(f"  Detail requests: {details}")
    print(f"  Retries: {retries}")
    print(f"  Query cache hits: {query_cache_hits}")
    print(f"  Title cache hits: {title_cache_hits}")
    print(f"  Steam ID cache hits: {steam_cache_hits}")
    print(f"  Detail cache hits: {detail_cache_hits}")
    print(f"  Auth refreshes: {transport_stats['auth_refreshes']}")
    print(f"  Auth retries: {transport_stats['auth_retries']}")
    print(f"  Search POSTs: {transport_stats['search_posts']}")
    print(f"  Transport failures: {transport_stats['request_failures']}")
    print(f"  Searches/game: {average_searches:.2f}")
    print(f"  Details/game: {average_details:.2f}")
    print(f"  Average search request: {average_search_time:.2f}s")
    print(f"  Average detail request: {average_detail_time:.2f}s")

    search_posts = transport_stats["search_posts"]

    average_search_post_time = (
        transport_stats["search_post_seconds"] / search_posts if search_posts else 0
    )

    print(f"  Average search POST: {average_search_post_time:.2f}s")
    print(f"  Auth refresh time: {transport_stats['auth_refresh_seconds']:.1f}s")
    print(f"  Total search POST time: {transport_stats['search_post_seconds']:.1f}s")
    print(f"  Total search time: {stats['search_seconds']:.1f}s")
    print(f"  Total detail time: {stats['detail_seconds']:.1f}s")
    print(f"  Total game processing time: {stats['game_seconds']:.1f}s")


HLTB_ALIASES = {
    "Sherlock Holmes: The Secret of the Silver Earring": (
        "Sherlock Holmes: The Silver Earring"
    ),
    "Ys I": "Ys I Complete",
}

ROMAN_NUMERALS = {
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "6": "VI",
    "7": "VII",
    "8": "VIII",
    "9": "IX",
    "10": "X",
}

SAFE_SUFFIXES = [
    "Digital Deluxe Edition",
    "Steam Special Edition",
    "Game of the Year Edition",
    "Collector's Edition",
    "Collectors Edition",
    "Anniversary Edition",
    "Definitive Edition",
    "Enhanced Edition",
    "Complete Edition",
    "Ultimate Edition",
    "Remastered Edition",
    "Deluxe Edition",
    "Special Edition",
    "GOTY Edition",
    "Gold Edition",
    "Platinum Edition",
    "Premium Edition",
    "Standard Edition",
    "Steam Edition",
    "HD Edition",
    "Extended Edition",
    "Final Edition",
    "Emperor Edition",
    "Valhalla Edition",
    "Legacy Edition",
    "The Director's Cut",
    "Director's Cut",
    "Directors Cut",
    "Final Cut",
    "HD Remaster",
    "Full HD",
    "Remastered",
    "Remaster",
    "Ω Edition",
    "Deluxe",
    "HD",
]

REVIEW_SUFFIXES = [
    "Complete Pack",
    "Gold Classic",
    "Gold Pack",
    "Collection",
]


def build_suffix_pattern(suffixes):
    alternatives = "|".join(
        re.escape(suffix)
        for suffix in sorted(
            suffixes,
            key=len,
            reverse=True,
        )
    )

    return re.compile(
        rf"(?:\s*[-–—:]\s*|\s+)(?:{alternatives})\s*$",
        re.IGNORECASE,
    )


SAFE_SUFFIX_PATTERN = build_suffix_pattern(SAFE_SUFFIXES)
REVIEW_SUFFIX_PATTERN = build_suffix_pattern(REVIEW_SUFFIXES)


def normalize_title(title):
    # Remove storefront/legal markers BEFORE NFKC.
    # NFKC turns ™ into the letters "TM".
    title = title.replace("™", "").replace("®", "").replace("©", "")

    title = re.sub(
        r"\s*\((?:TM|R|C)\)",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = unicodedata.normalize(
        "NFKC",
        title,
    ).lower()

    title = title.replace(
        "&",
        " and ",
    )

    title = re.sub(
        r"[^a-z0-9]+",
        " ",
        title,
    )

    return " ".join(title.split())


def title_tokens(title):
    return sorted(normalize_title(title).split())


def clean_generated_query(query):
    query = re.sub(
        r"\s*[:\-–—|]+\s*$",
        "",
        query,
    )

    return " ".join(query.split())


def add_query(queries, query):
    query = clean_generated_query(query)

    if query and query not in queries:
        queries.append(query)


def clean_storefront_markers(title):
    title = title.replace("™", "").replace("®", "").replace("©", "")

    title = re.sub(
        r"\s*\((?:TM|R|C)\)",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return " ".join(title.split())


def strip_suffixes(title, pattern):
    current = title

    while True:
        stripped = pattern.sub(
            "",
            current,
        )

        stripped = clean_generated_query(stripped)

        if stripped == current:
            return current

        current = stripped


def strip_safe_suffixes(title):
    return strip_suffixes(
        title,
        SAFE_SUFFIX_PATTERN,
    )


def strip_review_suffixes(title):
    return strip_suffixes(
        title,
        REVIEW_SUFFIX_PATTERN,
    )


def romanize_title_numbers(title):
    def replace_number(match):
        number = match.group(0)

        return ROMAN_NUMERALS.get(
            number,
            number,
        )

    return re.sub(
        r"\b(?:10|[1-9])\b",
        replace_number,
        title,
    )


ROMAN_TO_ARABIC = {roman: arabic for arabic, roman in ROMAN_NUMERALS.items()}


NUMBER_WORDS = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


def search_friendly_title(title):
    title = clean_storefront_markers(title)

    title = unicodedata.normalize(
        "NFKC",
        title,
    )

    title = (
        title.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    )

    title = re.sub(
        r'["]',
        "",
        title,
    )

    title = re.sub(
        r"(?<=\w)[;\-](?=\w)",
        " ",
        title,
    )

    return " ".join(title.split())


def normalize_structured_numbers(title):
    label_pattern = (
        r"\b"
        r"(Episode|Ep\.?|Season|Part|Volume|Vol\.?)"
        r"\s*\.?\s*"
        r"(0*[1-9]|10|"
        r"I|II|III|IV|V|VI|VII|VIII|IX|X|"
        r"One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)"
        r"\b"
    )

    def replace_number(match):
        label = match.group(1)
        number = match.group(2)

        normalized_label = label.lower().replace(".", "")

        label_names = {
            "episode": "Episode",
            "ep": "Episode",
            "season": "Season",
            "part": "Part",
            "volume": "Volume",
            "vol": "Volume",
        }

        normalized_number = number

        if number.upper() in ROMAN_TO_ARABIC:
            normalized_number = ROMAN_TO_ARABIC[number.upper()]

        elif number.lower() in NUMBER_WORDS:
            normalized_number = NUMBER_WORDS[number.lower()]

        else:
            normalized_number = str(int(number))

        return f"{label_names[normalized_label]} {normalized_number}"

    return re.sub(
        label_pattern,
        replace_number,
        title,
        flags=re.IGNORECASE,
    )


def add_safe_punctuation_queries(
    queries,
    title,
):
    add_query(
        queries,
        re.sub(
            r"\s*:\s*",
            ": ",
            title,
        ),
    )
    add_query(
        queries,
        title.replace(
            ":",
            " ",
        ),
    )

    # Spy Fox in "Dry Cereal"
    # -> Spy Fox in Dry Cereal
    add_query(
        queries,
        re.sub(
            r'["“”]',
            "",
            title,
        ),
    )

    add_query(
        queries,
        re.sub(
            r"\s+[-–—]\s+",
            ": ",
            title,
        ),
    )

    add_query(
        queries,
        re.sub(
            r"\s+[-–—]\s+",
            " ",
            title,
        ),
    )

    add_query(
        queries,
        re.sub(
            r"(?<=\w)\.(?=\w|\s|$)",
            "",
            title,
        ),
    )


def add_base_title_queries(
    queries,
    title,
):
    dash_parts = re.split(
        r"\s+[-–—]\s+",
        title,
        maxsplit=1,
    )

    if len(dash_parts) == 2:
        add_query(
            queries,
            dash_parts[0],
        )

    colon_parts = title.split(
        ":",
        1,
    )

    if len(colon_parts) == 2:
        add_query(
            queries,
            colon_parts[0],
        )


def build_hltb_queries(game_name):
    queries = []

    alias = HLTB_ALIASES.get(game_name)

    # Explicit aliases are our strongest title-based hint, so try them first.
    if alias is not None:
        add_query(
            queries,
            alias,
        )

    cleaned = clean_storefront_markers(game_name)

    # These transformations are already considered safe by the matcher.
    # Put the likely HLTB-facing forms before the raw Steam storefront name.
    stripped = strip_safe_suffixes(cleaned)

    no_year = re.sub(
        r"\s*\((?:19|20)\d{2}\)\s*$",
        "",
        stripped,
    )

    if no_year != stripped:
        add_query(
            queries,
            no_year,
        )

    no_labeled_year = re.sub(
        r"\s*\([^)]*,\s*(?:19|20)\d{2}\)\s*$",
        "",
        stripped,
    )

    if no_labeled_year != stripped:
        add_query(
            queries,
            no_labeled_year,
        )

    no_classic_label = re.sub(
        r"\s*\(Classic\)\s*$",
        "",
        stripped,
        flags=re.IGNORECASE,
    )

    if no_classic_label != stripped:
        add_query(
            queries,
            no_classic_label,
        )

    no_single_player = re.sub(
        r"\s+Single Player\s*$",
        "",
        stripped,
        flags=re.IGNORECASE,
    )

    if no_single_player != stripped:
        add_query(
            queries,
            no_single_player,
        )

    add_query(
        queries,
        stripped,
    )

    add_query(
        queries,
        stripped.replace(
            "&",
            "and",
        ),
    )

    add_query(
        queries,
        cleaned,
    )

    add_query(
        queries,
        cleaned.replace(
            "&",
            "and",
        ),
    )

    # Keep the exact Steam title as a fallback, but do not spend the first
    # request on legal/storefront markers that HLTB usually omits.
    add_query(
        queries,
        game_name,
    )

    year_only = re.sub(
        r"\([^,()]+,\s*((?:19|20)\d{2})\)",
        r"(\1)",
        cleaned,
    )

    add_query(
        queries,
        year_only,
    )

    for query in queries.copy():
        stripped_query = strip_safe_suffixes(query)

        add_query(
            queries,
            stripped_query,
        )

        add_query(
            queries,
            stripped_query.replace(
                "&",
                "and",
            ),
        )

    for query in queries.copy():
        add_query(
            queries,
            search_friendly_title(query),
        )

    for query in queries.copy():
        add_safe_punctuation_queries(
            queries,
            query,
        )

    for query in queries.copy():
        add_query(
            queries,
            normalize_structured_numbers(query),
        )

    for query in queries.copy():
        add_query(
            queries,
            romanize_title_numbers(query),
        )

    for query in queries.copy():
        if query.count(":") != 1:
            continue

        left, right = query.split(
            ":",
            1,
        )

        left = left.strip()
        right = right.strip()

        if not left or not right:
            continue

        add_query(
            queries,
            f"{right}: {left}",
        )

    return queries


def build_review_queries(game_name):
    queries = []

    cleaned = clean_storefront_markers(game_name)

    no_trailing_descriptor = re.sub(
        r"\s*(?:\([^()]+\)|\[[^\[\]]+\])\s*$",
        "",
        cleaned,
    )

    add_query(
        queries,
        no_trailing_descriptor,
    )

    no_year_descriptor = re.sub(
        r"\s*\([^)]*(?:19|20)\d{2}[^)]*\)\s*$",
        "",
        cleaned,
    )

    add_query(
        queries,
        no_year_descriptor,
    )

    stripped_package = strip_review_suffixes(cleaned)

    add_query(
        queries,
        stripped_package,
    )

    add_base_title_queries(
        queries,
        cleaned,
    )

    add_base_title_queries(
        queries,
        stripped_package,
    )

    add_base_title_queries(
        queries,
        no_year_descriptor,
    )

    return queries


def get_result_titles(result):
    titles = [
        result.game_name,
    ]

    alias = result.json_content.get("game_alias")

    if isinstance(alias, str):
        alias = alias.strip()

        if alias:
            titles.append(alias)

    return titles


def find_safe_match(results, query):
    normalized_query = normalize_title(query)

    query_tokens = title_tokens(query)

    for result in results:
        for result_title in get_result_titles(result):
            normalized_result = normalize_title(result_title)

            result_tokens = title_tokens(result_title)

            if normalized_result == normalized_query:
                return result

            if result_tokens == query_tokens:
                return result

    return None


def find_safe_match_for_queries(
    results,
    queries,
):
    for query in queries:
        match = find_safe_match(
            results,
            query,
        )

        if match is not None:
            return match

    return None


def search_hltb(
    query,
    game_name,
):
    with HLTB_CACHE_LOCK:
        cached_results = HLTB_QUERY_CACHE.get(
            query,
            CACHE_MISS,
        )

        if cached_results is not CACHE_MISS:
            cached_results = list(cached_results)

    if cached_results is not CACHE_MISS:
        increment_hltb_stat("query_cache_hits")

        return cached_results

    max_attempts = 3

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        request_start = time.perf_counter()

        results = HLTB_CLIENT.search(
            query,
            SearchModifiers.NONE,
            similarity_case_sensitive=False,
        )

        request_seconds = time.perf_counter() - request_start

        with HLTB_STATS_LOCK:
            HLTB_STATS["search_requests"] += 1
            HLTB_STATS["search_seconds"] += request_seconds

        if results is not None:
            with HLTB_CACHE_LOCK:
                HLTB_QUERY_CACHE[query] = tuple(results)

            return results

        if attempt == max_attempts:
            break

        increment_hltb_stat("retries")

        delay = 5 * (2 ** (attempt - 1)) + random.uniform(0, 2)

        print(f"HLTB request failed for {query}. Retrying in {delay:.1f}s...")

        time.sleep(delay)

    raise RuntimeError(
        f"HLTB request failed after {max_attempts} attempts for {game_name}"
    )


def serialize_candidate(
    result,
    query,
):
    json_content = result.json_content

    if not isinstance(json_content, dict):
        json_content = {}

    game_type = json_content.get("game_type")

    if not isinstance(game_type, str):
        game_type = None

    release_year = json_content.get("release_world")

    try:
        release_year = int(release_year)

    except (TypeError, ValueError):
        release_year = None

    if release_year is not None and release_year <= 0:
        release_year = None

    return {
        "game_id": result.game_id,
        "game_name": result.game_name,
        "game_web_link": result.game_web_link,
        "game_type": game_type,
        "release_year": release_year,
        "main_story": result.main_story,
        "main_extra": result.main_extra,
        "completionist": result.completionist,
        "all_styles": result.all_styles,
        "similarity": result.similarity,
        "search_query": query,
    }


def get_result_steam_app_ids(result):
    json_content = result.json_content

    if not isinstance(json_content, dict):
        return set()

    steam_app_ids = set()

    for field in (
        "profile_steam",
        "profile_steam_alt",
    ):
        value = json_content.get(field)

        try:
            value = int(value)

        except (TypeError, ValueError):
            continue

        if value > 0:
            steam_app_ids.add(value)

    return steam_app_ids


def add_candidate_to_cache(
    cache,
    key,
    candidate,
):
    bucket = cache.setdefault(
        key,
        {},
    )

    bucket[candidate["game_id"]] = candidate


def cache_search_results(
    results,
    query,
):
    if not results:
        return

    with HLTB_CACHE_LOCK:
        for result in results:
            candidate = serialize_candidate(
                result,
                query,
            )

            for result_title in get_result_titles(result):
                normalized_title = normalize_title(result_title)
                token_key = tuple(title_tokens(result_title))

                if normalized_title:
                    add_candidate_to_cache(
                        HLTB_TITLE_CACHE,
                        normalized_title,
                        candidate,
                    )

                if token_key:
                    add_candidate_to_cache(
                        HLTB_TOKEN_CACHE,
                        token_key,
                        candidate,
                    )

            for steam_app_id in get_result_steam_app_ids(result):
                HLTB_STEAM_CANDIDATE_CACHE[steam_app_id] = candidate


def get_cached_candidate_for_steam_app_id(steam_app_id):
    try:
        steam_app_id = int(steam_app_id)

    except (TypeError, ValueError):
        return None

    if steam_app_id <= 0:
        return None

    with HLTB_CACHE_LOCK:
        candidate = HLTB_STEAM_CANDIDATE_CACHE.get(steam_app_id)

        if candidate is None:
            return None

        return candidate.copy()


def get_cached_candidates_for_query(query):
    normalized_query = normalize_title(query)
    token_key = tuple(title_tokens(query))

    with HLTB_CACHE_LOCK:
        normalized_candidates = HLTB_TITLE_CACHE.get(
            normalized_query,
            {},
        )

        if normalized_candidates:
            return [candidate.copy() for candidate in normalized_candidates.values()]

        token_candidates = HLTB_TOKEN_CACHE.get(
            token_key,
            {},
        )

        return [candidate.copy() for candidate in token_candidates.values()]


def find_cached_safe_candidate(
    queries,
    steam_app_id,
):
    steam_candidate = get_cached_candidate_for_steam_app_id(steam_app_id)

    if steam_candidate is not None:
        increment_hltb_stat("steam_cache_hits")

        return steam_candidate

    for query in queries:
        candidates = get_cached_candidates_for_query(query)

        if len(candidates) != 1:
            continue

        candidate = candidates[0]
        candidate["search_query"] = query

        increment_hltb_stat("title_cache_hits")

        return candidate

    return None


def get_cached_detail_steam_app_id(hltb_game_id):
    with HLTB_CACHE_LOCK:
        return HLTB_DETAIL_STEAM_CACHE.get(
            hltb_game_id,
            CACHE_MISS,
        )


def cache_detail_steam_app_id(
    hltb_game_id,
    steam_app_id,
    candidate,
):
    if steam_app_id is None:
        return

    with HLTB_CACHE_LOCK:
        HLTB_DETAIL_STEAM_CACHE[hltb_game_id] = steam_app_id
        HLTB_STEAM_CANDIDATE_CACHE[steam_app_id] = candidate.copy()


def remember_candidates(
    candidates,
    results,
    query,
):
    for result in results[:5]:
        candidate = serialize_candidate(
            result,
            query,
        )

        game_id = candidate["game_id"]
        existing = candidates.get(game_id)

        if existing is None:
            candidates[game_id] = candidate
            continue

        new_score = candidate.get("similarity") or 0

        old_score = existing.get("similarity") or 0

        if new_score > old_score:
            candidates[game_id] = candidate


def print_candidates(
    prefix,
    query,
    results,
):
    candidate_names = [result.game_name for result in results[:5]]

    print(f"{prefix} for {query}: {candidate_names}")


def sort_review_candidates(
    candidates,
    limit=5,
):
    return sorted(
        candidates.values(),
        key=lambda candidate: candidate.get("similarity") or 0,
        reverse=True,
    )[:limit]


def find_steam_verified_candidate(
    candidates,
    steam_app_id,
    checked_hltb_ids=None,
):
    if checked_hltb_ids is None:
        checked_hltb_ids = set()

    try:
        steam_app_id = int(steam_app_id)

    except (TypeError, ValueError):
        return None

    if steam_app_id <= 0:
        return None

    for candidate in candidates:
        hltb_game_id = candidate.get("game_id")

        if hltb_game_id is None:
            continue

        if hltb_game_id in checked_hltb_ids:
            continue

        checked_hltb_ids.add(hltb_game_id)

        cached_steam_app_id = get_cached_detail_steam_app_id(hltb_game_id)

        if cached_steam_app_id is not CACHE_MISS:
            increment_hltb_stat("detail_cache_hits")

            if cached_steam_app_id == steam_app_id:
                increment_hltb_stat("steam_cache_hits")

                return candidate

            continue

        detail_start = time.perf_counter()

        candidate_steam_app_id = get_hltb_detail_steam_app_id(hltb_game_id)

        detail_seconds = time.perf_counter() - detail_start

        with HLTB_STATS_LOCK:
            HLTB_STATS["detail_requests"] += 1
            HLTB_STATS["detail_seconds"] += detail_seconds

        if candidate_steam_app_id is None:
            continue

        cache_detail_steam_app_id(
            hltb_game_id,
            candidate_steam_app_id,
            candidate,
        )

        if candidate_steam_app_id == steam_app_id:
            print(
                f"HLTB Steam App ID match: "
                f"{candidate['game_name']} "
                f"[Steam App ID: {steam_app_id}]"
            )

            return candidate

    return None


def discover_hltb_candidates(
    game_name,
    steam_app_id,
):
    safe_queries = build_hltb_queries(game_name)

    cached_match = find_cached_safe_candidate(
        safe_queries,
        steam_app_id,
    )

    if cached_match is not None:
        return {
            "match": cached_match,
            "candidates": [],
            "attempted_queries": [],
        }

    review_candidates = {}
    searched_queries = set()
    attempted_queries = []
    checked_hltb_ids = set()

    # First pass:
    # Try all safe title transformations.
    for query in safe_queries:
        searched_queries.add(query)

        attempted_queries.append(query)

        results = search_hltb(
            query,
            game_name,
        )

        if not results:
            continue

        cache_search_results(
            results,
            query,
        )

        match = find_safe_match(
            results,
            query,
        )

        if match is not None:
            return {
                "match": serialize_candidate(
                    match,
                    query,
                ),
                "candidates": [],
                "attempted_queries": attempted_queries,
            }

        remember_candidates(
            review_candidates,
            results,
            query,
        )

        current_candidates = [
            serialize_candidate(
                result,
                query,
            )
            for result in results[:5]
        ]

        steam_match = find_steam_verified_candidate(
            current_candidates,
            steam_app_id,
            checked_hltb_ids,
        )

        if steam_match is not None:
            return {
                "match": steam_match,
                "candidates": [],
                "attempted_queries": attempted_queries,
            }

    # Second pass:
    # Broader discovery searches.
    for query in build_review_queries(game_name):
        if query in searched_queries:
            continue

        searched_queries.add(query)

        attempted_queries.append(query)

        results = search_hltb(
            query,
            game_name,
        )

        if not results:
            continue

        cache_search_results(
            results,
            query,
        )

        # Even though this is a broader search,
        # the returned result may still exactly match
        # one of our safe identities or HLTB aliases.
        match = find_safe_match_for_queries(
            results,
            safe_queries,
        )

        if match is not None:
            return {
                "match": serialize_candidate(
                    match,
                    query,
                ),
                "candidates": [],
                "attempted_queries": attempted_queries,
            }

        remember_candidates(
            review_candidates,
            results,
            query,
        )

        current_candidates = [
            serialize_candidate(
                result,
                query,
            )
            for result in results[:5]
        ]

        steam_match = find_steam_verified_candidate(
            current_candidates,
            steam_app_id,
            checked_hltb_ids,
        )

        if steam_match is not None:
            return {
                "match": steam_match,
                "candidates": [],
                "attempted_queries": attempted_queries,
            }

    return {
        "match": None,
        "candidates": sort_review_candidates(review_candidates),
        "attempted_queries": attempted_queries,
    }


def matched_result(candidate):
    return {
        "status": "matched",
        "match": candidate,
        "candidates": [],
    }


def get_hltb_data(
    game_name,
    steam_app_id,
):
    game_start = time.perf_counter()

    try:
        discovery = discover_hltb_candidates(
            game_name,
            steam_app_id,
        )

        match = discovery["match"]

        if match is not None:
            return matched_result(match)

        candidates = discovery["candidates"]
        attempted_queries = discovery["attempted_queries"]

        # Discovery exhausted both safe title matching
        # and exact Steam App ID verification.
        if candidates:
            candidate_names = [candidate["game_name"] for candidate in candidates]

            print(f"HLTB needs review: {game_name}")

            print(f"  Queries tried: {attempted_queries}")

            print(f"  Candidates: {candidate_names}")

            return {
                "status": "review",
                "match": None,
                "candidates": candidates,
            }

        # Nothing usable was found at all.
        print(f"HLTB no usable match: {game_name}")

        print(f"  Queries tried: {attempted_queries}")

        return {
            "status": "no_match",
            "match": None,
            "candidates": [],
        }

    finally:
        game_seconds = time.perf_counter() - game_start

        with HLTB_STATS_LOCK:
            HLTB_STATS["games_attempted"] += 1
            HLTB_STATS["game_seconds"] += game_seconds
            games_attempted = HLTB_STATS["games_attempted"]

        if game_seconds >= 5:
            print(f"HLTB slow game: {game_name} ({game_seconds:.1f}s)")

        if games_attempted % 100 == 0:
            print_hltb_stats()
