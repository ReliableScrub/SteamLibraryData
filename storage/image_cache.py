from pathlib import Path

import requests
import shutil

from api.steam_api import get_game_image_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_CACHE = PROJECT_ROOT / "data" / "images"

def get_cached_image_path(app_id):
    return IMAGE_CACHE / f"{app_id}.jpg"

def get_game_image(app_id):
    IMAGE_CACHE.mkdir(parents=True, exist_ok=True)

    image_path = get_cached_image_path(app_id)

    if image_path.exists():
        return image_path

    image_url = get_game_image_url(app_id)

    response = requests.get(image_url, timeout=10)
    response.raise_for_status()

    image_path.write_bytes(response.content)

    return image_path

def clear_image_cache():
    if IMAGE_CACHE.exists():
        shutil.rmtree(IMAGE_CACHE)