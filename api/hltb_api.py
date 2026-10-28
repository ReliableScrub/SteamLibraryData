import random
import re
import threading
import time
import unicodedata

from howlongtobeatpy import SearchModifiers

from api.hltb_client import HLTB_CLIENT
from api.hltb_page import fetch_hltb_detail_payload, get_hltb_detail_steam_app_id

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

REVIEW_CANDIDATE_LIMIT = 10
STEAM_VERIFY_CANDIDATE_LIMIT = 10
LOG_CANDIDATE_LIMIT = 5
IDENTITY_QUERY_LIMIT = 7
DISCOVERY_QUERY_LIMIT = 7


class HLTBError(RuntimeError):
    pass


class HLTBUnavailableError(HLTBError):
    pass


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


# These are known separate/tutorial/multiplayer components rather than the
# parent game's campaign. Do not silently attach the parent's HLTB time.
HLTB_SKIP_TITLES = {
    "Dark Messiah of Might & Magic Multi-Player",
    "Medal of Honor(TM) Multiplayer",
    "The Ship Tutorial",
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

# Edition/release labels are useful for search discovery, but stripping them
# is NOT proof that two titles are the same game. These variants are only
# used in the Steam-AppID-verified discovery pass.
DISCOVERY_SUFFIXES = [
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
    "Jurassic Edition",
    "Collection",
    "Enhanced",
    "Gold",
    "VR",
    "Edition",
    "Legacy",
    "Reprise",
    "Remastered",
    "Remaster",
    "Multiplayer",
    "Multi-Player",
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


DISCOVERY_SUFFIX_PATTERN = build_suffix_pattern(DISCOVERY_SUFFIXES)
REVIEW_SUFFIX_PATTERN = build_suffix_pattern(REVIEW_SUFFIXES)


def strip_legal_markers(title):
    # Remove legal/storefront markers before Unicode NFKC. NFKC turns ™ into
    # literal "TM". If a marker sits between two word characters, preserve a
    # separator (ACE COMBAT™7 -> ACE COMBAT 7); otherwise remove it outright
    # (Red Alert™ -> Red Alert) so we do not create "Red Alert ,".
    title = re.sub(
        r"(?<=\w)[™®©](?=\w)",
        " ",
        title,
    )
    title = re.sub(
        r"[™®©]",
        "",
        title,
    )
    title = re.sub(
        r"\s*\((?:TM|R|C)\)",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(
        r"\s+([,;:!?])",
        r"\1",
        title,
    )

    return " ".join(title.split())


def normalize_title(title):
    title = strip_legal_markers(title)

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


def is_friends_pass_title(title):
    normalized = normalize_title(title)

    return bool(
        re.search(
            r"\b(?:friend s|friends|friend) pass\b",
            normalized,
        )
    )


def title_tokens(title):
    return sorted(normalize_title(title).split())


def clean_generated_query(query):
    query = re.sub(
        r"\s*[:\-–—|]+\s*$",
        "",
        query,
    )
    query = re.sub(
        r"\s+([,;:!?])",
        r"\1",
        query,
    )

    return " ".join(query.split())


def add_query(queries, query):
    query = clean_generated_query(query)

    if query and query not in queries:
        queries.append(query)


def clean_storefront_markers(title):
    return strip_legal_markers(title)


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


def strip_discovery_suffixes(title):
    return strip_suffixes(
        title,
        DISCOVERY_SUFFIX_PATTERN,
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

    # Do not interpret digits inside decimals such as 1.5 or 2.5 as
    # standalone title numbers.
    return re.sub(
        r"(?<![\d.])\b(?:10|[1-9])\b(?![\d.])",
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


def strip_decorative_dashes(title):
    # Steam often wraps subtitles/edition labels in attached dashes:
    # "-STRIVE-", "-Reloaded-", "-HD ... ReMIX-".
    # Leave ordinary interior hyphens such as "Spider-Man" alone.
    title = re.sub(
        r"^\s*[-–—]+\s*",
        "",
        title,
    )
    title = re.sub(
        r"\s*[-–—]+\s*$",
        "",
        title,
    )
    title = re.sub(
        r"(?:(?<=^)|(?<=\s))[-–—]+(?=\S)",
        "",
        title,
    )
    title = re.sub(
        r"(?<=\S)[-–—]+(?=\s|$)",
        "",
        title,
    )

    return " ".join(title.split())


def normalize_joiner_spacing(title):
    title = re.sub(
        r"\s*&\s*",
        " & ",
        title,
    )
    title = re.sub(
        r"\s*\+\s*",
        " + ",
        title,
    )

    return " ".join(title.split())


def normalize_greek_title_symbols(title):
    # Preserve a word boundary when Sigma is immediately followed by an
    # installment number: Σ2 -> Sigma 2, not Sigma2.
    title = re.sub(
        r"[Σσ](?=\d)",
        "Sigma ",
        title,
    )

    return title.replace("Σ", "Sigma").replace("σ", "Sigma")


def normalize_known_attached_numbers(title):
    # Re;Birth1 / Re;Birth2 / Re;Birth3 are storefront spellings;
    # HLTB uses a space before the installment number.
    return re.sub(
        r"\b(Re[;\s]?Birth)(\d+)\b",
        r"\1 \2",
        title,
        flags=re.IGNORECASE,
    )


def strip_trailing_bracket_descriptor(title):
    return clean_generated_query(
        re.sub(
            r"\s*\[[^\[\]]+\]\s*$",
            "",
            title,
        )
    )


def strip_leading_bracket_descriptor(title):
    return clean_generated_query(
        re.sub(
            r"^\s*\[[^\[\]]+\]\s*",
            "",
            title,
        )
    )


def unwrap_parenthesized_roman(title):
    return re.sub(
        r"\(([IVXLCDM]+)\)",
        r"\1",
        title,
        flags=re.IGNORECASE,
    )


def strip_parenthesized_roman(title):
    return clean_generated_query(
        re.sub(
            r"\s*\([IVXLCDM]+\)\s*",
            " ",
            title,
            flags=re.IGNORECASE,
        )
    )


def is_non_main_hltb_title(title):
    normalized = normalize_title(title)

    if title in HLTB_SKIP_TITLES:
        return True

    # These are normally alternate/test/demo app entries rather than the game
    # whose campaign HLTB describes. Keep this intentionally narrow.
    return bool(
        normalized.endswith((" unstable", " demo"))
        or " experimental server" in f" {normalized}"
    )


def latin_discovery_title(title):
    # Broader-discovery only. This helps bilingual storefront names such as
    # "鬼谷八荒 Tale of Immortal" without treating the stripped form as proof
    # of identity.
    title = normalize_greek_title_symbols(title)
    title = re.sub(
        r"[^\x00-\x7F]+",
        " ",
        title,
    )

    return " ".join(title.split())


def add_alternate_series_queries(
    queries,
    title,
):
    # FATAL FRAME / PROJECT ZERO: Maiden of Black Water
    # -> FATAL FRAME: Maiden of Black Water
    # -> PROJECT ZERO: Maiden of Black Water
    if ":" not in title:
        return

    left, right = title.split(
        ":",
        1,
    )

    if "/" not in left:
        return

    right = right.strip()

    if not right:
        return

    for series_name in left.split("/"):
        series_name = series_name.strip()

        if series_name:
            add_query(
                queries,
                f"{series_name}: {right}",
            )


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

    title = normalize_known_attached_numbers(title)

    title = re.sub(
        r"[!?]+$",
        "",
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

    without_decorative_dashes = strip_decorative_dashes(title)

    add_query(
        queries,
        without_decorative_dashes,
    )

    add_query(
        queries,
        normalize_joiner_spacing(title),
    )

    add_query(
        queries,
        normalize_joiner_spacing(without_decorative_dashes),
    )

    add_query(
        queries,
        normalize_greek_title_symbols(title),
    )

    add_query(
        queries,
        normalize_known_attached_numbers(title),
    )

    add_query(
        queries,
        title.replace(
            "~",
            " ",
        ),
    )

    # Remove acronym-style periods from letters, but do not destroy decimals.
    add_query(
        queries,
        re.sub(
            r"(?<=[A-Za-z])\.(?=[A-Za-z]|\s|$)",
            "",
            title,
        ),
    )

    add_alternate_series_queries(
        queries,
        title,
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

    if "[" not in title and "]" not in title:
        colon_parts = title.split(
            ":",
            1,
        )

        if len(colon_parts) == 2:
            add_query(
                queries,
                colon_parts[0],
            )


DISCOVERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "edition",
    "enhanced",
    "game",
    "legacy",
    "of",
    "remaster",
    "remastered",
    "the",
}


def identity_friendly_title(title):
    """Mechanical changes that preserve the title's identity."""
    title = clean_storefront_markers(title)
    title = unicodedata.normalize("NFKC", title)
    title = normalize_greek_title_symbols(title)
    title = normalize_known_attached_numbers(title)
    title = strip_decorative_dashes(title)
    title = normalize_joiner_spacing(title)

    return " ".join(title.split())


def add_identity_punctuation_queries(queries, title):
    # These variants change punctuation/formatting only. They may therefore
    # participate in conservative title equality matching.
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
        search_friendly_title(title),
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


def useful_discovery_fragment(text):
    text = clean_generated_query(text)

    if not text:
        return False

    tokens = re.findall(
        r"[A-Za-z0-9]+",
        text,
    )

    if len(tokens) >= 2:
        return True

    return bool(tokens and len(tokens[0]) >= 5)


def add_discovery_fragment(
    queries,
    text,
    allow_single=False,
):
    text = clean_generated_query(text)

    if not text:
        return

    tokens = re.findall(
        r"[A-Za-z0-9]+",
        text,
    )

    if len(tokens) >= 2:
        add_query(
            queries,
            text,
        )
        return

    if allow_single and tokens and len(tokens[0]) >= 2:
        add_query(
            queries,
            text,
        )


def strip_discovery_labels(title):
    current = clean_generated_query(title)

    # Apply both edition-like and broader review suffixes. This is discovery
    # only: "Legacy", "VR", "Reprise", etc. can be meaningful in a title.
    while True:
        previous = current
        current = strip_discovery_suffixes(current)
        current = strip_review_suffixes(current)

        if current == previous:
            return current


def add_structural_discovery_queries(queries, title):
    # Colon-separated subtitles often contain the HLTB-facing title:
    # "Killing Floor Mod: Defence Alliance 2" -> "Defence Alliance 2"
    # "Love n War: Hero by Chance" -> "Hero by Chance".
    if ":" in title:
        left, right = title.split(
            ":",
            1,
        )

        add_discovery_fragment(
            queries,
            left,
        )
        add_discovery_fragment(
            queries,
            right,
        )

    # Regional names, collections and bundle-style storefront names often use
    # slash / ampersand / plus separators. Each side is only a search hint;
    # it can never auto-match without conservative title identity or Steam ID.
    for separator in ("/", "&", "+", "|"):
        if separator not in title:
            continue

        for part in title.split(separator):
            part = strip_discovery_labels(part)
            add_discovery_fragment(
                queries,
                part,
            )

    # Publisher/series prefix followed by "Presents..." is another common
    # storefront shape: "BIT.TRIP Presents... Runner2..." -> "Runner2...".
    presents_match = re.search(
        r"\bPresents\b[\s.:;!\-–—]*",
        title,
        flags=re.IGNORECASE,
    )

    if presents_match is not None:
        add_discovery_fragment(
            queries,
            title[presents_match.end() :],
        )


def stopword_reduced_discovery_title(title):
    tokens = re.findall(
        r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?",
        normalize_greek_title_symbols(title),
    )

    if len(tokens) < 3:
        return ""

    reduced = [token for token in tokens if token.casefold() not in DISCOVERY_STOPWORDS]

    if len(reduced) < 2 or reduced == tokens:
        return ""

    return " ".join(reduced)


def add_anchor_discovery_queries(queries, title):
    tokens = re.findall(
        r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)?",
        title,
    )

    # A franchise anchor is useful for two-part glued/renamed titles such as
    # "BlazBlue Centralfiction" or "Ys I". Keep this deliberately narrow so
    # ordinary numbered titles do not devolve into searches for "F1", etc.
    if len(tokens) == 2:
        first = tokens[0]

        if len(first) >= 4 or (
            first.isalpha()
            and len(first) >= 2
            and re.fullmatch(r"[IVXLCDM]+", tokens[1], re.IGNORECASE)
        ):
            add_discovery_fragment(
                queries,
                first,
                allow_single=True,
            )

    # Alternate subtitles sometimes preserve only a distinctive trailing
    # phrase, e.g. "The Secret of the Silver Earring" -> "Silver Earring".
    if (
        len(tokens) >= 4
        and not re.search(r"\d\.\d", title)
        and tokens[-2].casefold() not in DISCOVERY_STOPWORDS
        and len(tokens[-2]) > 1
    ):
        tail = " ".join(tokens[-2:])
        add_discovery_fragment(
            queries,
            tail,
        )


def build_hltb_queries(game_name):
    """Conservative identity queries.

    Every query returned here is allowed to prove identity by normalized title
    equality. Edition/subtitle stripping intentionally does not happen here.
    """
    queries = []

    cleaned = clean_storefront_markers(game_name)
    mechanical = identity_friendly_title(cleaned)

    # Highest-value search form first.
    add_query(
        queries,
        mechanical,
    )

    # Preserve the cleaned storefront form as a second search identity.
    add_query(
        queries,
        cleaned,
    )

    # Parenthesized years are release descriptors rather than title identity.
    no_year = re.sub(
        r"\s*\((?:19|20)\d{2}\)\s*$",
        "",
        mechanical,
    )
    add_query(
        queries,
        no_year,
    )

    no_labeled_year = re.sub(
        r"\s*\([^)]*,\s*(?:19|20)\d{2}\)\s*$",
        "",
        mechanical,
    )
    add_query(
        queries,
        no_labeled_year,
    )

    # Leading/trailing square-bracket labels are storefront descriptors.
    add_query(
        queries,
        strip_leading_bracket_descriptor(mechanical),
    )
    add_query(
        queries,
        strip_trailing_bracket_descriptor(mechanical),
    )

    # "(VI)" and "VI" are formatting variants of the same installment number.
    add_query(
        queries,
        unwrap_parenthesized_roman(mechanical),
    )

    # Arabic/Roman installment numbers are another mechanical representation.
    add_query(
        queries,
        romanize_title_numbers(mechanical),
    )

    for query in queries.copy():
        add_identity_punctuation_queries(
            queries,
            query,
        )

    # Regional dual-series names with the same subtitle are also identity
    # variants, not edition stripping.
    for query in queries.copy():
        add_alternate_series_queries(
            queries,
            query,
        )

    return queries[:IDENTITY_QUERY_LIMIT]


def build_review_queries(game_name):
    """Broader discovery queries.

    These are search hints only. A result from this pass may be accepted only
    if it matches a conservative identity query or is verified against the
    exact Steam AppID.
    """
    queries = []

    cleaned = identity_friendly_title(game_name)

    # Remove clearly external descriptors first.
    descriptor_stripped = strip_trailing_bracket_descriptor(
        strip_leading_bracket_descriptor(cleaned)
    )
    add_discovery_fragment(
        queries,
        descriptor_stripped,
    )

    no_year = re.sub(
        r"\s*\((?:19|20)\d{2}\)\s*$",
        "",
        descriptor_stripped,
    )
    add_discovery_fragment(
        queries,
        no_year,
    )

    no_parenthesized_roman = strip_parenthesized_roman(no_year)

    if no_parenthesized_roman != no_year:
        add_discovery_fragment(
            queries,
            no_parenthesized_roman,
        )

    # Edition/release labels are deliberately discovery-only.
    stripped = strip_discovery_labels(no_year)
    if stripped != no_year:
        add_discovery_fragment(
            queries,
            stripped,
            allow_single=True,
        )

    add_structural_discovery_queries(
        queries,
        no_year,
    )
    add_structural_discovery_queries(
        queries,
        stripped,
    )

    latin_only = latin_discovery_title(stripped)
    if latin_only != stripped:
        add_discovery_fragment(
            queries,
            latin_only,
        )

    reduced = stopword_reduced_discovery_title(stripped)
    add_discovery_fragment(
        queries,
        reduced,
    )

    if stripped == cleaned:
        add_anchor_discovery_queries(
            queries,
            stripped,
        )

    # Do not repeat conservative identities in the broader pass.
    identity_keys = {query.casefold() for query in build_hltb_queries(game_name)}

    queries = [query for query in queries if query.casefold() not in identity_keys]

    return queries[:DISCOVERY_QUERY_LIMIT]


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


def find_safe_match(
    results,
    query,
    steam_app_id=None,
):
    normalized_query = normalize_title(query)
    query_tokens = title_tokens(query)

    try:
        steam_app_id = int(steam_app_id)

    except (TypeError, ValueError):
        steam_app_id = None

    for result in results:
        result_steam_ids = get_result_steam_app_ids(result)

        # If HLTB explicitly associates this result with a different Steam
        # application, title equality must not override that stronger evidence.
        if (
            steam_app_id is not None
            and result_steam_ids
            and steam_app_id not in result_steam_ids
        ):
            continue

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
    steam_app_id=None,
):
    for query in queries:
        match = find_safe_match(
            results,
            query,
            steam_app_id=steam_app_id,
        )

        if match is not None:
            return match

    return None


def search_hltb(
    query,
    game_name,
    use_cache=True,
):
    if use_cache:
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

    raise HLTBUnavailableError(
        "HowLongToBeat could not be reached after "
        f"{max_attempts} attempts. Try again later."
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

    steam_app_ids = []

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
            steam_app_ids.append(value)

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
        "steam_app_ids": sorted(set(steam_app_ids)),
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


def direct_steam_app_id_candidates(
    results,
    steam_app_id,
    query,
):
    try:
        steam_app_id = int(steam_app_id)

    except (TypeError, ValueError):
        return []

    if steam_app_id <= 0:
        return []

    matches = []

    for result in results:
        if steam_app_id not in get_result_steam_app_ids(result):
            continue

        matches.append(
            serialize_candidate(
                result,
                query,
            )
        )

    return matches


def unique_direct_steam_app_id_candidate(
    results,
    steam_app_id,
    query,
):
    matches = direct_steam_app_id_candidates(
        results,
        steam_app_id,
        query,
    )

    unique = {candidate["game_id"]: candidate for candidate in matches}

    if len(unique) != 1:
        return None

    candidate = next(iter(unique.values()))

    print(
        f"HLTB direct Steam App ID match: "
        f"{candidate['game_name']} "
        f"[Steam App ID: {steam_app_id}]"
    )

    return candidate


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
                add_candidate_to_cache(
                    HLTB_STEAM_CANDIDATE_CACHE,
                    steam_app_id,
                    candidate,
                )


def get_cached_candidate_for_steam_app_id(steam_app_id):
    try:
        steam_app_id = int(steam_app_id)

    except (TypeError, ValueError):
        return None

    if steam_app_id <= 0:
        return None

    with HLTB_CACHE_LOCK:
        candidates = HLTB_STEAM_CANDIDATE_CACHE.get(
            steam_app_id,
            {},
        )

        if len(candidates) != 1:
            return None

        candidate = next(iter(candidates.values()))

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
        candidate_steam_ids = set(candidate.get("steam_app_ids", []))

        if candidate_steam_ids and steam_app_id not in candidate_steam_ids:
            continue

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
        add_candidate_to_cache(
            HLTB_STEAM_CANDIDATE_CACHE,
            steam_app_id,
            candidate.copy(),
        )


def remember_candidates(
    candidates,
    results,
    query,
):
    for result in results[:REVIEW_CANDIDATE_LIMIT]:
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
    candidate_names = [result.game_name for result in results[:LOG_CANDIDATE_LIMIT]]

    print(f"{prefix} for {query}: {candidate_names}")


def sort_review_candidates(
    candidates,
    limit=REVIEW_CANDIDATE_LIMIT,
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
    use_cache=True,
):
    identity_queries = build_hltb_queries(game_name)

    if use_cache:
        cached_match = find_cached_safe_candidate(
            identity_queries,
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
    discovery_direct_matches = {}

    # First pass:
    # Conservative identity-preserving queries. A unique direct Steam AppID
    # result is strongest; otherwise exact normalized title equality is allowed.
    for query in identity_queries:
        searched_queries.add(query)
        attempted_queries.append(query)

        results = search_hltb(
            query,
            game_name,
            use_cache=use_cache,
        )

        if not results:
            continue

        cache_search_results(
            results,
            query,
        )

        direct_match = unique_direct_steam_app_id_candidate(
            results,
            steam_app_id,
            query,
        )

        if direct_match is not None:
            return {
                "match": direct_match,
                "candidates": [],
                "attempted_queries": attempted_queries,
            }

        match = find_safe_match(
            results,
            query,
            steam_app_id=steam_app_id,
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

    # Second pass:
    # Broader discovery queries. These transformations may remove edition,
    # subtitle or storefront words, so title equality with the discovery query
    # itself is NOT proof of identity.
    for query in build_review_queries(game_name):
        if query in searched_queries:
            continue

        searched_queries.add(query)
        attempted_queries.append(query)

        results = search_hltb(
            query,
            game_name,
            use_cache=use_cache,
        )

        if not results:
            continue

        cache_search_results(
            results,
            query,
        )

        # A result that exactly matches one of the conservative identities is
        # still safe even though a broader query happened to discover it.
        match = find_safe_match_for_queries(
            results,
            identity_queries,
            steam_app_id=steam_app_id,
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

        for candidate in direct_steam_app_id_candidates(
            results,
            steam_app_id,
            query,
        ):
            discovery_direct_matches[candidate["game_id"]] = candidate

        remember_candidates(
            review_candidates,
            results,
            query,
        )

    # Discovery queries are intentionally allowed to be aggressive. Only one
    # unambiguous HLTB record explicitly carrying this Steam AppID may auto-win.
    if len(discovery_direct_matches) == 1:
        candidate = next(iter(discovery_direct_matches.values()))

        print(
            f"HLTB direct Steam App ID match: "
            f"{candidate['game_name']} "
            f"[Steam App ID: {steam_app_id}]"
        )

        return {
            "match": candidate,
            "candidates": [],
            "attempted_queries": attempted_queries,
        }

    # Multiple HLTB records claiming the same Steam AppID can happen for
    # collections/DLC. Do not arbitrarily choose the first one.
    direct_match_is_ambiguous = len(discovery_direct_matches) > 1

    # Detail-page verification is the expensive fallback. Run it once, after
    # all search discovery, against a single capped candidate set instead of
    # verifying up to N candidates after every query.
    if not direct_match_is_ambiguous:
        verification_candidates = sort_review_candidates(
            review_candidates,
            limit=STEAM_VERIFY_CANDIDATE_LIMIT,
        )

        steam_match = find_steam_verified_candidate(
            verification_candidates,
            steam_app_id,
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


def parse_hltb_game_reference(reference):
    if isinstance(reference, int):
        game_id = reference
    else:
        text = str(reference or "").strip()

        if text.isdigit():
            game_id = int(text)
        else:
            match = re.search(
                r"(?:https?://)?(?:www\.)?howlongtobeat\.com/game/(\d+)(?:[/?#]|$)",
                text,
                flags=re.IGNORECASE,
            )

            if match is None:
                raise ValueError(
                    "Enter a HowLongToBeat game ID or a URL like "
                    "https://howlongtobeat.com/game/12345."
                )

            game_id = int(match.group(1))

    if game_id <= 0:
        raise ValueError("HowLongToBeat game ID must be a positive number.")

    return game_id


def _detail_seconds_to_hours(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None

    if seconds <= 0:
        return None

    return seconds / 3600


def get_hltb_candidate_by_reference(reference):
    game_id = parse_hltb_game_reference(reference)
    detail_payload = fetch_hltb_detail_payload(game_id)

    if detail_payload is None:
        raise HLTBUnavailableError(f"HowLongToBeat game {game_id} could not be loaded.")

    games = detail_payload.get("game")

    if not isinstance(games, list) or not games or not isinstance(games[0], dict):
        raise HLTBError(
            f"HowLongToBeat game {game_id} did not contain a usable game record."
        )

    game_data = games[0]
    game_name = game_data.get("game_name")

    if not isinstance(game_name, str) or not game_name.strip():
        raise HLTBError(f"HowLongToBeat game {game_id} did not contain a usable title.")

    actual_game_id = game_data.get("game_id")

    try:
        actual_game_id = int(actual_game_id)
    except (TypeError, ValueError):
        actual_game_id = game_id

    if actual_game_id <= 0:
        actual_game_id = game_id

    steam_app_ids = set()

    for field in ("profile_steam", "profile_steam_alt"):
        value = game_data.get(field)

        try:
            value = int(value)
        except (TypeError, ValueError):
            continue

        if value > 0:
            steam_app_ids.add(value)

    release_year = None
    release_value = game_data.get("release_world")

    if isinstance(release_value, str):
        match = re.match(r"((?:19|20)\d{2})", release_value.strip())

        if match is not None:
            release_year = int(match.group(1))
    else:
        try:
            release_year = int(release_value)
        except (TypeError, ValueError):
            release_year = None

        if release_year is not None and release_year <= 0:
            release_year = None

    game_type = game_data.get("game_type")

    if not isinstance(game_type, str):
        game_type = None

    candidate = {
        "game_id": actual_game_id,
        "game_name": game_name.strip(),
        "game_web_link": f"https://howlongtobeat.com/game/{actual_game_id}",
        "game_type": game_type,
        "release_year": release_year,
        "main_story": _detail_seconds_to_hours(game_data.get("comp_main")),
        "main_extra": _detail_seconds_to_hours(game_data.get("comp_plus")),
        "completionist": _detail_seconds_to_hours(game_data.get("comp_100")),
        "all_styles": _detail_seconds_to_hours(game_data.get("comp_all")),
        "similarity": 1.0,
        "search_query": f"Manual HLTB ID {actual_game_id}",
        "steam_app_ids": sorted(steam_app_ids),
    }

    for steam_app_id in steam_app_ids:
        cache_detail_steam_app_id(
            actual_game_id,
            steam_app_id,
            candidate,
        )

    return candidate


def get_hltb_data(
    game_name,
    steam_app_id,
    cancel_requested=None,
    force_refresh=None,
):
    game_start = time.perf_counter()

    # Bulk HLTB workers pass a cancellation callback and benefit from
    # process-local caches. A direct selected-game refresh does not, so
    # treat it as a real refresh unless the caller explicitly overrides it.
    if force_refresh is None:
        force_refresh = cancel_requested is None

    if force_refresh:
        reset_hltb_cache()

    try:
        if is_friends_pass_title(game_name):
            print(f"HLTB skipped Friend's Pass app: {game_name}")

            return {
                "status": "no_match",
                "match": None,
                "candidates": [],
            }

        if is_non_main_hltb_title(game_name):
            print(f"HLTB skipped non-main Steam app: {game_name}")

            return {
                "status": "no_match",
                "match": None,
                "candidates": [],
            }

        discovery = discover_hltb_candidates(
            game_name,
            steam_app_id,
            use_cache=not force_refresh,
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
