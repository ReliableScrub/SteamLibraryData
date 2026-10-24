import requests


class SteamSpyError(RuntimeError):
    pass


class SteamSpyUnavailableError(SteamSpyError):
    pass


class SteamSpyResponseError(SteamSpyError):
    pass


def get_game_metadata(app_id):
    url = "https://steamspy.com/api.php"

    params = {
        "request": "appdetails",
        "appid": app_id,
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

    except requests.Timeout as error:
        raise SteamSpyUnavailableError(
            "SteamSpy did not respond in time. Try again later."
        ) from error

    except requests.ConnectionError as error:
        raise SteamSpyUnavailableError(
            "Could not connect to SteamSpy. Check your internet connection."
        ) from error

    except requests.RequestException as error:
        raise SteamSpyError("The SteamSpy request could not be completed.") from error

    if response.status_code == 429:
        raise SteamSpyUnavailableError(
            "SteamSpy is temporarily rate-limiting requests. Try again later."
        )

    if 500 <= response.status_code < 600:
        raise SteamSpyUnavailableError(
            "SteamSpy is currently unavailable. Try again later."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise SteamSpyError(
            f"SteamSpy returned HTTP {response.status_code}."
        ) from error

    try:
        data = response.json()
    except ValueError as error:
        raise SteamSpyResponseError(
            "SteamSpy returned an unexpected response."
        ) from error

    if not isinstance(data, dict):
        raise SteamSpyResponseError("SteamSpy returned an unexpected response.")

    genre_text = data.get("genre")

    if genre_text is None:
        genre_text = ""

    elif not isinstance(genre_text, str):
        raise SteamSpyResponseError("SteamSpy returned unexpected genre data.")

    canonical_genres = {
        "free to play": "Free To Play",
    }

    genres = []
    seen_genres = set()

    for genre in genre_text.split(","):
        genre = " ".join(genre.split())

        if not genre:
            continue

        genre = canonical_genres.get(
            genre.casefold(),
            genre,
        )

        genre_key = genre.casefold()

        if genre_key in seen_genres:
            continue

        seen_genres.add(genre_key)
        genres.append(genre)

    tags = data.get("tags")

    if tags is None:
        tags = {}

    elif isinstance(tags, list):
        tags = {tag: 0 for tag in tags if isinstance(tag, str)}

    elif not isinstance(tags, dict):
        raise SteamSpyResponseError("SteamSpy returned unexpected tag data.")

    positive = data.get("positive")
    negative = data.get("negative")

    if positive is not None:
        if isinstance(positive, bool):
            raise SteamSpyResponseError(
                "SteamSpy returned unexpected positive-review data."
            )

        try:
            positive = int(positive)
        except (TypeError, ValueError) as error:
            raise SteamSpyResponseError(
                "SteamSpy returned unexpected positive-review data."
            ) from error

        if positive < 0:
            raise SteamSpyResponseError(
                "SteamSpy returned unexpected positive-review data."
            )

    if negative is not None:
        if isinstance(negative, bool):
            raise SteamSpyResponseError(
                "SteamSpy returned unexpected negative-review data."
            )

        try:
            negative = int(negative)
        except (TypeError, ValueError) as error:
            raise SteamSpyResponseError(
                "SteamSpy returned unexpected negative-review data."
            ) from error

        if negative < 0:
            raise SteamSpyResponseError(
                "SteamSpy returned unexpected negative-review data."
            )

    return genres, tags, positive, negative
