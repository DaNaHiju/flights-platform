"""Populates the deals:top Redis cache read by GET /deals.

Meant to be run on a schedule (`python -m worker.refresh_deals`) by a
CronJob defined in the manifests repo — this repo owns the job logic, not
the CronJob object itself.
"""

from datetime import datetime, timedelta, timezone

from shared.cache import set_json
from shared.providers import ProviderError, ProviderNotConfiguredError, get_provider
from shared.schemas import deal_airport_fields
from shared.utils.logging import log
from worker.config import settings

DEALS_CACHE_KEY = "deals:top"

# Fixed set of popular routes searched from FLIGHTS_DEFAULT_ORIGIN: top deals
# are the cheapest round trip per destination in this list, sorted by price.
# Each run costs one provider search per destination (8 every 6 h), well inside
# quota: a round trip is still ONE search call.
POPULAR_DESTINATIONS = ["MAD", "JFK", "LHR", "CDG", "FCO", "BKK", "BCN", "AMS"]

SEARCH_HORIZON_DAYS = 30


def refresh_deals() -> int:
    """Search each popular destination and cache the cheapest round trips. Returns the deal count.

    Outbound is today + SEARCH_HORIZON_DAYS, return is DEALS_TRIP_LENGTH_DAYS later.
    A deal's price is the total of the cheapest outbound + return pair.
    Does not touch the cache when there are no deals.
    """
    origin = settings.FLIGHTS_DEFAULT_ORIGIN
    departure = datetime.now(timezone.utc) + timedelta(days=SEARCH_HORIZON_DAYS)
    travel_date = departure.strftime("%Y-%m-%d")
    return_date = (departure + timedelta(days=settings.DEALS_TRIP_LENGTH_DAYS)).strftime(
        "%Y-%m-%d"
    )

    provider = get_provider()
    deals = []
    for destination in POPULAR_DESTINATIONS:
        try:
            offers = provider.search_round_trip(
                origin, destination, travel_date, return_date, 1, settings.FLIGHTS_CURRENCY
            )
        except ProviderNotConfiguredError as exc:
            # Same answer for every destination: stop instead of logging 8 times.
            log.warning("Skipping all deals: %s", exc)
            break
        except ProviderError as exc:
            log.warning("Skipping deal for %s->%s: %s", origin, destination, exc)
            continue

        if not offers:
            continue

        # price is the pair's total; airline and duration describe its outbound.
        cheapest = min(offers, key=lambda o: o.price)
        deals.append(
            {
                "destination": destination,
                "departure_date": travel_date,
                "return_date": return_date,
                "price": cheapest.price,
                "currency": cheapest.currency,
                "airline": cheapest.outbound.primary_airline,
                **deal_airport_fields(origin, destination),
                "total_duration_minutes": cheapest.outbound.total_duration_minutes,
                # No deep_link on purpose: prices are live and a deal can be
                # 6 h old, so the user re-searches the route to book it.
            }
        )

    # 0 deals means every search failed or came back empty, almost always a
    # provider outage. Overwriting would replace the last good list with an
    # empty one, so keep it and let its TTL decide when it expires.
    if not deals:
        log.warning(
            "Refreshed 0 deals from %s; keeping previous %s", origin, DEALS_CACHE_KEY
        )
        return 0

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
