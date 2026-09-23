import requests

STORE_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

def get_trailer_url(app_id):
    response = requests.get(
        STORE_DETAILS_URL,
        params={
            "appids": app_id,
            "cc": "US",
            "l": "english"
        },
        timeout=15
    )
    response.raise_for_status()

    result = response.json().get(str(app_id))

    if not result or not result.get("success"):
        return None

    data = result.get("data", {})
    movies = data.get("movies", [])

    if not movies:
        return None
    movie = movies[0]

    if movie.get("hls_h264"):
        return movie["hls_h264"]

    mp4 = movie.get("mp4") or {}

    if mp4.get("480"):
        return mp4["480"]

    if mp4.get("max"):
        return mp4["max"]

    webm = movie.get("webm") or {}

    if webm.get("480"):
        return webm["480"]

    if webm.get("max"):
        return webm["max"]

    return None