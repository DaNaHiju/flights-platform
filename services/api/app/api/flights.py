"""Flights search API router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.errors import provider_http_exception
from app.config import settings
from shared.cache import try_get_json, try_set_json
from shared.providers import (
    FlightProvider,
    ProviderError,
    get_provider,
    is_valid_location_code,
)

router = APIRouter()

DATE_FORMAT = "%Y-%m-%d"


def _search_cache_key(
    provider: str,
    origin: str,
    destination: str,
    travel_date: str,
    adults: int,
    currency: str,
    return_date: str | None = None,
) -> str:
    # The provider name is part of the key: results of different providers have
    # different offer ids, so they must never be served for each other.
    key = f"search:{provider}:{origin}:{destination}:{travel_date}:{adults}:{currency}"
    return f"{key}:rt:{return_date}" if return_date else key


def _parse_date(value: str):
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_date_format"},
        ) from exc


@router.get("")
def search_flights(
    # 3 letters, plus an optional "+" that pins the search to that one airport
    # (what the typeahead sends for an AIRPORT pick).
    origin: str = Query(..., min_length=3, max_length=4),
    destination: str = Query(..., min_length=3, max_length=4),
    date: str = Query(..., alias="date"),
    adults: int = Query(default=1, ge=1, le=9),
    return_date: str | None = Query(default=None),
    provider: FlightProvider = Depends(get_provider),
):
    """Search live offers, one-way or (with return_date) round trip.

    Served from Redis when the same search ran within SEARCH_CACHE_TTL seconds.
    Without return_date each result is a FlightOffer. With it, each result is
    {price, currency, deep_link, outbound, return}: one fare for the pair.
    """
    origin = origin.upper()
    destination = destination.upper()

    if not is_valid_location_code(origin) or not is_valid_location_code(destination):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_iata_code"},
        )
    if origin.rstrip("+") == destination.rstrip("+"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "same_origin_and_destination"},
        )

    travel_date = _parse_date(date)
    if travel_date < datetime.now(timezone.utc).date():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "date_in_past"},
        )
    if return_date is not None and _parse_date(return_date) < travel_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "return_before_departure"},
        )

    currency = settings.FLIGHTS_CURRENCY
    cache_key = _search_cache_key(
        provider.name, origin, destination, date, adults, currency, return_date
    )
    cached = try_get_json(cache_key)
    if cached is not None:
        return {"results": cached["offers"], "cached": True, "cached_at": cached["cached_at"]}

    try:
        if return_date:
            models = provider.search_round_trip(
                origin, destination, date, return_date, adults, currency
            )
        else:
            models = provider.search_one_way(origin, destination, date, adults, currency)
    except ProviderError as exc:
        raise provider_http_exception(
            exc, provider.name, f"Flight search {origin}->{destination}"
        ) from exc

    offers = [m.model_dump(mode="json", by_alias=True) for m in models]

    # An empty answer is NOT cached. Merchants that fail or rate-limit show up as
    # "no offers" too, so remembering it would keep answering "no flights" for
    # SEARCH_CACHE_TTL after the provider has recovered. Searching again is cheap.
    if offers:
        now = datetime.now(timezone.utc).isoformat()
        try_set_json(
            cache_key, {"cached_at": now, "offers": offers}, ttl=settings.SEARCH_CACHE_TTL
        )

        if not return_date:
            # Each one-way offer is also cached on its own, so POST /bookings can
            # look it up by offer_id independently of the search cache's TTL.
            for offer in offers:
                try_set_json(f"offer:{offer['offer_id']}", offer, ttl=settings.OFFER_CACHE_TTL)

    return {"results": offers, "cached": False, "cached_at": None}
