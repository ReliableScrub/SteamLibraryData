import random
import re
import time
import unicodedata

from howlongtobeatpy import HowLongToBeat, SearchModifiers

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

    add_query(
        queries,
        game_name,
    )

    alias = HLTB_ALIASES.get(game_name)

    if alias is not None:
        add_query(
            queries,
            alias,
        )

    cleaned = clean_storefront_markers(game_name)

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

    year_only = re.sub(
        r"\([^,()]+,\s*((?:19|20)\d{2})\)",
        r"(\1)",
        cleaned,
    )

    add_query(
        queries,
        year_only,
    )

    no_year = re.sub(
        r"\s*\((?:19|20)\d{2}\)\s*$",
        "",
        cleaned,
    )

    add_query(
        queries,
        no_year,
    )

    no_labeled_year = re.sub(
        r"\s*\([^)]*,\s*(?:19|20)\d{2}\)\s*$",
        "",
        cleaned,
    )

    add_query(
        queries,
        no_labeled_year,
    )

    no_classic_label = re.sub(
        r"\s*\(Classic\)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    add_query(
        queries,
        no_classic_label,
    )

    no_single_player = re.sub(
        r"\s+Single Player\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    add_query(
        queries,
        no_single_player,
    )

    for query in list(queries):
        stripped = strip_safe_suffixes(query)

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

    for query in list(queries):
        add_query(
            queries,
            search_friendly_title(query),
        )

    for query in list(queries):
        add_safe_punctuation_queries(
            queries,
            query,
        )

    for query in list(queries):
        add_query(
            queries,
            normalize_structured_numbers(query),
        )

    for query in list(queries):
        add_query(
            queries,
            romanize_title_numbers(query),
        )

    for query in list(queries):
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
    hltb,
    query,
    game_name,
):
    max_attempts = 3

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        results = hltb.search(
            query,
            SearchModifiers.NONE,
            similarity_case_sensitive=False,
        )

        if results is not None:
            return results

        if attempt == max_attempts:
            break

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
    return {
        "game_id": result.game_id,
        "game_name": result.game_name,
        "game_web_link": result.game_web_link,
        "main_story": result.main_story,
        "main_extra": result.main_extra,
        "completionist": result.completionist,
        "all_styles": result.all_styles,
        "similarity": result.similarity,
        "search_query": query,
    }


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


def get_hltb_data(game_name):
    hltb = HowLongToBeat(0.0)

    safe_queries = build_hltb_queries(game_name)

    review_candidates = {}
    searched_queries = set()
    attempted_queries = []

    # First pass:
    # Try all safe title transformations.
    for query in safe_queries:
        searched_queries.add(query)

        attempted_queries.append(query)

        results = search_hltb(
            hltb,
            query,
            game_name,
        )

        if not results:
            continue

        match = find_safe_match(
            results,
            query,
        )

        if match is not None:
            return {
                "status": "matched",
                "match": serialize_candidate(
                    match,
                    query,
                ),
                "candidates": [],
            }

        remember_candidates(
            review_candidates,
            results,
            query,
        )

    # Second pass:
    # Broader discovery searches.
    for query in build_review_queries(game_name):
        if query in searched_queries:
            continue

        searched_queries.add(query)

        attempted_queries.append(query)

        results = search_hltb(
            hltb,
            query,
            game_name,
        )

        if not results:
            continue

        # Even though this is a broader search,
        # the returned result may still exactly match
        # one of our safe identities or HLTB aliases.
        match = find_safe_match_for_queries(
            results,
            safe_queries,
        )

        if match is not None:
            return {
                "status": "matched",
                "match": serialize_candidate(
                    match,
                    query,
                ),
                "candidates": [],
            }

        remember_candidates(
            review_candidates,
            results,
            query,
        )

    # We found possible HLTB records,
    # but none passed safe automatic matching.
    if review_candidates:
        candidates = sorted(
            review_candidates.values(),
            key=lambda candidate: candidate.get("similarity") or 0,
            reverse=True,
        )[:5]

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
