"""Flights search API router."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.cache import get_json, set_json
from app.config import settings
from app.models import flight_offer_from_raw
from app.providers import ProviderUnavailableError, is_valid_iata, search_one_way
from app.utils.logging import log
from app.utils.metrics import provider_errors

router = APIRouter()

DATE_FORMAT = "%Y-%m-%d"


def _search_cache_key(
    origin: str, destination: str, travel_date: str, adults: int
) -> str:
    return f"search:{origin}:{destination}:{travel_date}:{adults}"


@router.get("")
def search_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: str = Query(..., alias="date"),
    adults: int = Query(default=1, ge=1),
):
    """Search live one-way offers. Served from Redis when recently queried."""
    origin = origin.upper()
    destination = destination.upper()

    if not is_valid_iata(origin) or not is_valid_iata(destination):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_iata_code"},
        )

    try:
        travel_date = datetime.strptime(date, DATE_FORMAT).date()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_date_format"},
        ) from exc

    if travel_date < datetime.now(timezone.utc).date():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "date_in_past"},
        )

    cache_key = _search_cache_key(origin, destination, date, adults)
    cached = get_json(cache_key)
    if cached is not None:
        offers = [flight_offer_from_raw(raw) for raw in cached["offers"]]
        return {
            "results": offers,
            "cached": True,
            "cached_at": cached["cached_at"],
        }

    try:
        raw_offers = search_one_way(
            origin, destination, date, adults, settings.FLIGHTS_CURRENCY
        )
    except ProviderUnavailableError as exc:
        provider_errors.inc()
        log.warning(
            "fli search failed origin=%s destination=%s: %s", origin, destination, exc
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "provider_unavailable"},
        ) from exc

    now = datetime.now(timezone.utc).isoformat()
    set_json(
        cache_key,
        {"cached_at": now, "offers": raw_offers},
        ttl=settings.SEARCH_CACHE_TTL,
    )

    # Cache each offer individually so POST /bookings can look it up by
    # booking_token later, independent of the search-result cache's TTL.
    for raw in raw_offers:
        set_json(f"offer:{raw['booking_token']}", raw, ttl=settings.OFFER_CACHE_TTL)

    offers = [flight_offer_from_raw(raw) for raw in raw_offers]
    return {"results": offers, "cached": False, "cached_at": None}
