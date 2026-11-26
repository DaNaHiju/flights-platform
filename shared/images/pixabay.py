"""ImageProvider backed by the Pixabay API.

Pixabay's rules, and where this module honours them:

- The API key travels as the `key` query parameter (Pixabay offers nothing
  else), so the URL is a secret. It must never reach a log, an error message, an
  exception or a response. httpx puts the full URL in its INFO request log and
  in some exception messages: see _RedactKey and the `from None` below.
- Results must be cached 24 h: the API router stores them in Redis.
- Images must not be hotlinked: this module downloads the image and returns its
  bytes; the API serves them.
- The photographer must be credited: user and page URL travel with the bytes.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

import httpx

from shared.images.base import DestinationImage, ImageProviderError
from shared.utils.logging import log

SEARCH_PATH = "/api/"
QUERY_MAX_LENGTH = 100  # Pixabay's limit for `q`
MAX_IMAGE_BYTES = 600 * 1024
# Raster formats only. SVG is an image too, but served from our origin it can
# carry script, so it is not accepted.
ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 3
# Categories tried in order: "travel" first, "places" when it has nothing.
CATEGORIES = ("travel", "places")

_KEY_IN_URL = re.compile(r"([?&]key=)[^&\s\"']+", re.IGNORECASE)


class _RedactKey(logging.Filter):
    """Hide the `key` query parameter in anything httpx or httpcore log.

    httpx logs `HTTP Request: GET https://pixabay.com/api/?key=... "HTTP/1.1 200 OK"`
    at INFO, so any deployment that raises the log level would leak the key.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _KEY_IN_URL.sub(r"\1REDACTED", message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


def _install_log_redaction() -> None:
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, _RedactKey) for f in logger.filters):
            logger.addFilter(_RedactKey())


_install_log_redaction()


def _is_pixabay_host(url: str) -> bool:
    """https on pixabay.com or a subdomain: all the image bytes and page links
    we accept. The URLs come from Pixabay's reply, so they are checked rather
    than fetched or rendered blindly."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "pixabay.com" or host.endswith(".pixabay.com"))


class PixabayProvider:
    """ImageProvider implementation on top of the Pixabay API."""

    name = "pixabay"

    def __init__(
        self,
        api_key: str,
        gateway_url: str = "https://pixabay.com",
        transport: httpx.BaseTransport | None = None,
    ):
        self._api_key = api_key
        self._http = httpx.Client(
            base_url=gateway_url.rstrip("/"),
            timeout=httpx.Timeout(READ_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS),
            transport=transport,
        )

    def find_destination_image(self, city: str, country: str) -> DestinationImage | None:
        hit = self._first_hit(city, country)
        if hit is None:
            return None
        image_url = hit.get("largeImageURL")
        page_url = hit.get("pageURL")
        if not (isinstance(image_url, str) and isinstance(page_url, str)):
            raise ImageProviderError("Pixabay hit without largeImageURL or pageURL")
        if not (_is_pixabay_host(image_url) and _is_pixabay_host(page_url)):
            raise ImageProviderError("Pixabay hit points outside pixabay.com")

        downloaded = self._download(image_url)
        if downloaded is None:
            return None
        data, content_type = downloaded
        return DestinationImage(
            data=data,
            content_type=content_type,
            credit_user=str(hit.get("user") or ""),
            credit_url=page_url,
        )

    # --- Search --------------------------------------------------------------

    def _first_hit(self, city: str, country: str) -> dict | None:
        """First result of "<city> <country>", else of "<country>" alone."""
        terms = [" ".join(part for part in (city, country) if part)]
        if city and country:
            terms.append(country)
        for term in terms:
            for category in CATEGORIES:
                hits = self._search(term[:QUERY_MAX_LENGTH], category)
                if hits:
                    return hits[0]
        return None

    def _search(self, query: str, category: str) -> list[dict]:
        params = {
            "key": self._api_key,
            "q": query,
            "image_type": "photo",
            "orientation": "horizontal",
            "category": category,
            "order": "popular",
            "safesearch": "true",
            "min_width": "1200",
            "per_page": "5",
        }
        try:
            response = self._http.get(SEARCH_PATH, params=params)
        except httpx.TimeoutException:
            raise ImageProviderError("Pixabay search timed out") from None
        except httpx.HTTPError as exc:
            # Not str(exc) and not chained (`from None`): httpx exceptions can
            # carry the request URL, and that URL contains the API key.
            raise ImageProviderError(f"Pixabay search failed ({type(exc).__name__})") from None

        if response.status_code == 429:
            raise ImageProviderError("Pixabay rate limit reached")
        if response.status_code != 200:
            raise ImageProviderError(f"Pixabay search answered HTTP {response.status_code}")
        try:
            hits = response.json().get("hits")
        except (ValueError, AttributeError):
            raise ImageProviderError("Pixabay sent a non-JSON body") from None
        if not isinstance(hits, list):
            raise ImageProviderError("Pixabay reply has no hits list")
        return [hit for hit in hits if isinstance(hit, dict)]

    # --- Download ------------------------------------------------------------

    def _download(self, url: str) -> tuple[bytes, str] | None:
        """The image bytes and content type, or None when the image is not
        acceptable (too big, not a raster image): that is a property of the
        photo, not a temporary failure. Raises ImageProviderError on failures."""
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with self._http.stream("GET", url) as response:
                    if response.is_redirect:
                        url = str(response.next_request.url) if response.next_request else ""
                        if not _is_pixabay_host(url):
                            raise ImageProviderError("Pixabay image redirected outside pixabay.com")
                        continue
                    if response.status_code == 429:
                        raise ImageProviderError("Pixabay rate limit reached")
                    if response.status_code != 200:
                        raise ImageProviderError(
                            f"Pixabay image answered HTTP {response.status_code}"
                        )
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        log.info("Pixabay image rejected: content type %s", content_type or "missing")
                        return None
                    declared = response.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                        log.info("Pixabay image rejected: %s bytes declared", declared)
                        return None
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_IMAGE_BYTES:
                            log.info("Pixabay image rejected: over %d bytes", MAX_IMAGE_BYTES)
                            return None
                    return bytes(data), content_type
            except ImageProviderError:
                raise
            except httpx.TimeoutException:
                raise ImageProviderError("Pixabay image download timed out") from None
            except httpx.HTTPError as exc:
                raise ImageProviderError(
                    f"Pixabay image download failed ({type(exc).__name__})"
                ) from None
        raise ImageProviderError("Pixabay image redirected too many times")
