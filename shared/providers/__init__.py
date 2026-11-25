"""Flight data providers behind one interface.

Callers import from here, never from a concrete provider module:

    from shared.providers import get_provider, ProviderUnavailableError

Swapping the data source means adding a module that implements FlightProvider
(shared/providers/base.py) and a branch in get_provider(); nothing else in the
API, the worker or the frontend changes.
"""

from functools import lru_cache

from shared.config import settings
from shared.providers.base import (
    FlightProvider,
    ProviderBadRequestError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
    is_valid_location_code,
)

__all__ = [
    "FlightProvider",
    "ProviderBadRequestError",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderRateLimitedError",
    "ProviderUnavailableError",
    "get_provider",
    "is_valid_location_code",
]


@lru_cache(maxsize=1)
def get_provider() -> FlightProvider:
    """The configured provider, built once per process (it holds an HTTP pool)."""
    if settings.FLIGHTS_PROVIDER != "amadeus":
        raise RuntimeError(f"Unknown FLIGHTS_PROVIDER: {settings.FLIGHTS_PROVIDER!r}")

    # Imported here so a future second provider does not load Amadeus code.
    from shared.providers.amadeus import AmadeusClient, AmadeusProvider

    client = (
        AmadeusClient(settings.AMADEUS_API_KEY, settings.AMADEUS_GATEWAY_URL)
        if settings.AMADEUS_API_KEY
        else None
    )
    return AmadeusProvider(
        client,
        search_timeout=settings.AMADEUS_SEARCH_TIMEOUT_SECONDS,
        lookup_timeout=settings.AMADEUS_LOOKUP_TIMEOUT_SECONDS,
        max_results_per_merchant=settings.AMADEUS_MAX_RESULTS_PER_MERCHANT,
        airlines_cache_ttl=settings.AIRLINES_CACHE_TTL,
        locations_cache_ttl=settings.LOCATIONS_CACHE_TTL,
    )
