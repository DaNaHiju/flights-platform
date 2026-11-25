"""The FlightProvider interface and the errors every provider raises.

Callers (the API routers, the deals worker) depend on this module only. Each
provider maps its own failure modes onto the four errors below, so swapping
the provider never changes how errors reach the user.
"""

from __future__ import annotations

import re
from typing import Protocol

from shared.schemas import FlightOffer, Location, RoundTripOffer

# Three letters (an airport or a city code), optionally followed by "+", which
# pins the search to that exact airport instead of every airport of its city.
LOCATION_CODE_RE = re.compile(r"^[A-Z]{3}\+?$")


def is_valid_location_code(code: str) -> bool:
    """True for "LHR", "LON" or "LHR+" (upper-case); format check only."""
    return bool(LOCATION_CODE_RE.match(code))


class ProviderError(Exception):
    """Base class: the provider could not answer the request."""


class ProviderUnavailableError(ProviderError):
    """Timeout, network error, upstream 5xx, or rejected credentials. API: 502."""


class ProviderRateLimitedError(ProviderError):
    """The provider's quota for our API key is exhausted for now. API: 503."""

    def __init__(self, message: str, retry_after: int = 30):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderNotConfiguredError(ProviderError):
    """No API key is configured for the provider. API: 503."""


class ProviderBadRequestError(ProviderError):
    """The provider rejected the search parameters themselves. API: 400."""


class FlightProvider(Protocol):
    """What the rest of the platform needs from a flight data source."""

    name: str

    def search_one_way(
        self, origin: str, destination: str, date: str, adults: int, currency: str
    ) -> list[FlightOffer]:
        """Priced one-way offers, cheapest first."""
        ...

    def search_round_trip(
        self,
        origin: str,
        destination: str,
        date: str,
        return_date: str,
        adults: int,
        currency: str,
    ) -> list[RoundTripOffer]:
        """Priced outbound + return pairs, cheapest first."""
        ...

    def search_locations(self, keyword: str) -> list[Location]:
        """Airports and cities matching typed text, most travelled first."""
        ...
