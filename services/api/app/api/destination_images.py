"""Destination photos: GET /destination-image and GET /destination-image/file/{key}.

The first endpoint answers "is there a photo of this place, and who took it".
The second serves the bytes. Photos come from an ImageProvider (Pixabay), are
downloaded once and kept in Redis, so the browser never talks to the provider
(no hotlinking) and the provider is asked once per place per TTL.

Everything here is best effort: a missing API key, a provider failure or Redis
being down all answer {"available": false} with HTTP 200, never a 500. The page
simply keeps its gradient.
"""

import base64
import hashlib
import re
import unicodedata

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.config import settings
from shared import cache
from shared.images import ImageProvider, ImageProviderError, get_image_provider
from shared.utils.logging import log

router = APIRouter()

CACHE_PREFIX = "destination-image:"
# "No photo found" is cached much shorter than a photo: new photos get uploaded,
# and a miss costs a Pixabay request to re-check.
NOT_FOUND_TTL = 7 * 86400
FILE_CACHE_CONTROL = "public, max-age=86400"
SLUG_MAX_LENGTH = 40
KEY_PATTERN = r"^[a-z0-9_-]{1,100}$"

UNAVAILABLE = {"available": False, "url": None, "credit_user": None, "credit_url": None}


def _slug(text: str) -> str:
    """"Bogotá, D.C." -> "bogota-d-c"; text with no ASCII letters hashes instead."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:SLUG_MAX_LENGTH].strip("-")
    if slug:
        return slug
    return "x" + hashlib.sha1(text.casefold().encode()).hexdigest()[:12]


def image_key(city: str, country: str) -> str:
    """The normalized, URL-safe key of a place: "Hanoi"+"Vietnam" -> "hanoi_vietnam".

    "Bogotá" and "bogota" are the same place, so they share a Redis entry (and
    a Pixabay request). The key is also the last segment of the file URL.
    """
    return f"{_slug(city)}_{_slug(country)}" if country else _slug(city)


def _clean(value: str) -> str:
    return " ".join(value.split())


@router.get("")
def destination_image(
    city: str = Query(..., min_length=1, max_length=60),
    country: str = Query(default="", max_length=60),
    provider: ImageProvider | None = Depends(get_image_provider),
):
    """The photo of a destination, fetched and cached on first use.

    `url` is relative to the API root (the browser reaches it through the same
    prefix it used for this call). `credit_user` and `credit_url` must be shown
    next to the photo: Pixabay's terms require it.
    """
    city, country = _clean(city), _clean(country)
    if not city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "invalid_destination"}
        )
    key = image_key(city, country)
    redis_key = CACHE_PREFIX + key

    try:
        entry = cache.get_json(redis_key)
    except redis.RedisError as exc:
        # Without Redis there is nowhere to keep the bytes, and every request
        # would spend a Pixabay call: no photo until it is back.
        log.warning("Redis read failed for destination image %s: %s", key, exc)
        return UNAVAILABLE
    except ValueError:
        entry = None  # unreadable entry: treated as a miss and overwritten

    if entry is None:
        if provider is None:
            return UNAVAILABLE
        try:
            image = provider.find_destination_image(city, country)
        except ImageProviderError as exc:
            # Not cached: the next request tries again.
            log.warning("Destination image lookup failed for %s: %s", key, exc)
            return UNAVAILABLE

        if image is None:
            entry, ttl = {"found": False}, NOT_FOUND_TTL
        else:
            entry = {
                "found": True,
                "content_type": image.content_type,
                "credit_user": image.credit_user,
                "credit_url": image.credit_url,
                # The shared Redis client decodes replies as text, so the bytes
                # are stored base64-encoded inside the JSON entry.
                "data": base64.b64encode(image.data).decode("ascii"),
            }
            ttl = settings.DESTINATION_IMAGE_TTL
        try:
            cache.set_json(redis_key, entry, ttl=ttl)
        except redis.RedisError as exc:
            log.warning("Redis write failed for destination image %s: %s", key, exc)
            return UNAVAILABLE  # the file endpoint could not serve it anyway

    if not entry.get("found"):
        return UNAVAILABLE
    return {
        "available": True,
        "url": f"/destination-image/file/{key}",
        "credit_user": entry["credit_user"],
        "credit_url": entry["credit_url"],
    }


@router.get("/file/{key}")
def destination_image_file(key: str = Path(..., pattern=KEY_PATTERN)):
    """The cached photo's bytes. 404 when it is not in Redis (expired, never
    fetched, or Redis unreachable)."""
    try:
        entry = cache.get_json(CACHE_PREFIX + key)
    except (redis.RedisError, ValueError):
        entry = None
    if not entry or not entry.get("found"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"error": "image_not_found"}
        )
    return Response(
        content=base64.b64decode(entry["data"]),
        media_type=entry["content_type"],
        headers={
            "Cache-Control": FILE_CACHE_CONTROL,
            # The type was checked when the image was downloaded; keep browsers
            # from second-guessing it.
            "X-Content-Type-Options": "nosniff",
        },
    )
