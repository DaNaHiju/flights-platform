"""Destination photo providers behind one interface.

Callers import from here, never from a concrete provider module:

    from shared.images import get_image_provider, ImageProviderError

Swapping the photo source means adding a module that implements ImageProvider
(shared/images/base.py) and a branch in get_image_provider().
"""

from functools import lru_cache

from shared.config import settings
from shared.images.base import DestinationImage, ImageProvider, ImageProviderError

__all__ = ["DestinationImage", "ImageProvider", "ImageProviderError", "get_image_provider"]


@lru_cache(maxsize=1)
def get_image_provider() -> ImageProvider | None:
    """The configured provider, built once per process; None without an API key
    (the service then simply has no photos)."""
    if not settings.PIXABAY_API_KEY:
        return None
    from shared.images.pixabay import PixabayProvider

    return PixabayProvider(settings.PIXABAY_API_KEY, settings.PIXABAY_GATEWAY_URL)
