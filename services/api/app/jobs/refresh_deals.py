"""Populates the deals:top Redis cache read by GET /deals.

Meant to be run on a schedule (`python -m app.jobs.refresh_deals`) by a
CronJob defined in the manifests repo — this repo owns the job logic, not
the CronJob object itself.
"""

from datetime import datetime, timedelta, timezone

from app.cache import set_json
from app.config import settings
from app.providers import ProviderUnavailableError, search_one_way
from app.utils.logging import log

DEALS_CACHE_KEY = "deals:top"

# Fixed set of popular routes searched from FLIGHTS_DEFAULT_ORIGIN. There's
# no Amadeus-style "inspiration search" equivalent in fli, so top deals are
# just the cheapest offer per destination in this list, sorted by price.
POPULAR_DESTINATIONS = ["MAD", "JFK", "LHR", "CDG", "FCO", "BKK", "BCN", "AMS"]

SEARCH_HORIZON_DAYS = 30


def refresh_deals() -> int:
    """Search each popular destination and cache the cheapest offers. Returns the deal count."""
    origin = settings.FLIGHTS_DEFAULT_ORIGIN
    travel_date = (
        datetime.now(timezone.utc) + timedelta(days=SEARCH_HORIZON_DAYS)
    ).strftime("%Y-%m-%d")

    deals = []
    for destination in POPULAR_DESTINATIONS:
        try:
            offers = search_one_way(
                origin, destination, travel_date, 1, settings.FLIGHTS_CURRENCY
            )
        except ProviderUnavailableError as exc:
            log.warning("Skipping deal for %s->%s: %s", origin, destination, exc)
            continue

        if not offers:
            continue

        cheapest = min(offers, key=lambda o: o["price"])
        primary_airline = (
            cheapest.get("primary_airline_name")
            or cheapest.get("primary_airline")
            or ""
        )
        deals.append(
            {
                "destination": destination,
                "departure_date": travel_date,
                "price": cheapest["price"],
                "currency": cheapest["currency"],
                "airline": primary_airline,
            }
        )

    deals.sort(key=lambda d: d["price"])

    set_json(
        DEALS_CACHE_KEY,
        {"refreshed_at": datetime.now(timezone.utc).isoformat(), "deals": deals},
        ttl=settings.DEALS_CACHE_TTL,
    )
    return len(deals)


if __name__ == "__main__":
    _deal_count = refresh_deals()
    log.info("Refreshed %d deals from %s", _deal_count, settings.FLIGHTS_DEFAULT_ORIGIN)
