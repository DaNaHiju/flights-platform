"""Flights search API router."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from shared.cache import get_json, set_json
from shared.providers import (
    ProviderUnavailableError,
    is_valid_iata,
    search_one_way,
    search_round_trip,
)
from shared.schemas import flight_offer_from_raw
from shared.utils.logging import log
from shared.utils.metrics import provider_errors

router = APIRouter()

DATE_FORMAT = "%Y-%m-%d"


def _search_cache_key(
    origin: str,
    destination: str,
    travel_date: str,
    adults: int,
    return_date: str | None = None,
) -> str:
    key = f"search:{origin}:{destination}:{travel_date}:{adults}"
    # One-way keys stay exactly as before, so cached one-way searches survive the deploy.
    return f"{key}:rt:{return_date}" if return_date else key


def _round_trip_offer(raw: dict) -> dict:
    """Public shape of a round trip: the pair's total price and both flights."""
    return {
        "price": raw["price"],
        "currency": raw["currency"],
        "outbound": flight_offer_from_raw(raw["outbound"]),
        "return": flight_offer_from_raw(raw["return"]),
    }


@router.get("")
def search_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: str = Query(..., alias="date"),
    adults: int = Query(default=1, ge=1),
    return_date: str | None = Query(default=None),
):
    """Search live offers, one-way or (with return_date) round trip.

    Served from Redis when recently queried. Without return_date the response is
    unchanged. With it, each result is {price, currency, outbound, return}
    instead of a FlightOffer, and the price is for the whole pair.
    """
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

    if return_date is not None:
        try:
            parsed_return = datetime.strptime(return_date, DATE_FORMAT).date()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_date_format"},
            ) from exc
        if parsed_return < travel_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "return_before_departure"},
            )

    cache_key = _search_cache_key(origin, destination, date, adults, return_date)
    cached = get_json(cache_key)
    if cached is not None:
        to_public = _round_trip_offer if return_date else flight_offer_from_raw
        offers = [to_public(raw) for raw in cached["offers"]]
        return {
            "results": offers,
            "cached": True,
            "cached_at": cached["cached_at"],
        }

    try:
        if return_date:
            raw_offers = search_round_trip(
                origin,
                destination,
                date,
                return_date,
                adults,
                settings.FLIGHTS_CURRENCY,
            )
        else:
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

    if return_date:
        # Not bookable through POST /bookings: no per-offer cache for round trips.
        offers = [_round_trip_offer(raw) for raw in raw_offers]
        return {"results": offers, "cached": False, "cached_at": None}

    # Cache each offer individually so POST /bookings can look it up by
    # booking_token later, independent of the search-result cache's TTL.
    for raw in raw_offers:
        set_json(f"offer:{raw['booking_token']}", raw, ttl=settings.OFFER_CACHE_TTL)

    offers = [flight_offer_from_raw(raw) for raw in raw_offers]
    return {"results": offers, "cached": False, "cached_at": None}
