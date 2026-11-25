"""Airport / city typeahead for the origin and destination inputs.

The frontend calls this as the user types; the provider caches each keyword in
Redis (LOCATIONS_CACHE_TTL), so repeated keystrokes for popular places do not
spend Amadeus quota.
"""

from fastapi import APIRouter, Depends, Query

from app.api.errors import provider_http_exception
from shared.providers import FlightProvider, ProviderError, get_provider

router = APIRouter()


@router.get("")
def search_locations(
    keyword: str = Query(..., min_length=1, max_length=60),
    provider: FlightProvider = Depends(get_provider),
):
    """Airports and cities matching *keyword*, most travelled first.

    Fewer than 2 usable characters returns an empty list without calling the
    provider. Each result's `search_code` is what to send to GET /flights.
    """
    try:
        locations = provider.search_locations(keyword)
    except ProviderError as exc:
        raise provider_http_exception(exc, provider.name, "Location search") from exc
    return {"results": [loc.model_dump() for loc in locations]}
