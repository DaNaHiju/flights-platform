"""Flight data provider — wraps the `fli` library (reverse-engineered Google Flights).

fli has no API key and no official quota. It depends on an internal Google
endpoint that can change shape without notice — see docs/api-contract.md
open questions. Every call here is expected to occasionally fail with
ProviderUnavailableError; callers should map that to a 502.
"""

from fli.models import Airport, FlightSearchFilters, PassengerInfo
from fli.models.google_flights.base import TripType
from fli.search import SearchFlights
from fli.search.exceptions import SearchClientError
from fli.search.flights import SearchParseError

from shared.utils.logging import log


class ProviderUnavailableError(Exception):
    """Raised when fli cannot be reached or its response can't be parsed."""


def is_valid_iata(code: str) -> bool:
    """Return True if *code* is a known 3-letter IATA airport code."""
    return code.upper() in Airport.__members__


def _run_search(filters: FlightSearchFilters, **search_kwargs) -> list:
    """Call fli and map its failure modes to ProviderUnavailableError.

    Returns fli's list as is (empty means a genuine empty result).
    """
    try:
        results = SearchFlights().search(filters, **search_kwargs)
    except (SearchClientError, SearchParseError) as exc:
        raise ProviderUnavailableError(str(exc)) from exc
    except (
        Exception
    ) as exc:  # fli wraps curl_cffi/network errors as bare exceptions too
        log.warning("Unexpected error calling fli: %s", exc)
        raise ProviderUnavailableError(str(exc)) from exc

    # fli returns None (no exception) when Google's reply has no flights payload,
    # e.g. a consent page or a soft block. That is a provider failure, not "no
    # flights": an empty list is a genuine empty result.
    if results is None:
        raise ProviderUnavailableError("fli returned no payload (None)")
    return results


def search_one_way(
    origin: str,
    destination: str,
    date: str,
    adults: int,
    currency: str,
) -> list[dict]:
    """Search one-way flights and return them as plain JSON-serializable dicts.

    Returns the raw fli result shape untouched (legs, price, amenities,
    layovers, booking_token, ...). Callers trim it down to the public
    FlightOffer schema and/or cache it as-is for offer_snapshot.
    """
    filters = FlightSearchFilters(
        passenger_info=PassengerInfo(adults=adults),
        flight_segments=[
            {
                "departure_airport": [[Airport[origin.upper()], 0]],
                "arrival_airport": [[Airport[destination.upper()], 0]],
                "travel_date": date,
            }
        ],
    )

    results = _run_search(filters, currency=currency)
    if not results:
        return []

    # One-way searches never expand into round-trip tuples.
    return [r.model_dump(mode="json") for r in results if r.price is not None]


# fli keeps the first `top_n` outbound flights and asks Google for the returns of
# each one with one extra request, so a round trip costs 1 + top_n requests
# (fli/search/flights.py, SearchFlights._expand_multi_leg). Its default is 5.
MAX_ROUND_TRIP_OUTBOUNDS = 3
# Each outbound can bring ~10 returns; keep only the cheapest pairs.
MAX_ROUND_TRIP_RESULTS = 10


def search_round_trip(
    origin: str,
    destination: str,
    date: str,
    return_date: str,
    adults: int,
    currency: str,
) -> list[dict]:
    """Search round trips and return the cheapest outbound + return pairs.

    Each item is {"price", "currency", "outbound", "return"}, the last two in the
    raw fli shape of search_one_way. At most MAX_ROUND_TRIP_OUTBOUNDS outbound
    flights are expanded (1 + 3 requests to Google).

    "price" is the price of the whole pair and comes from the RETURN flight: the
    outbound carries the same cheapest-pair price whichever return is picked,
    while each return carries the price of its own pair (checked with a live
    search, TLV-ATH).
    """
    filters = FlightSearchFilters(
        trip_type=TripType.ROUND_TRIP,
        passenger_info=PassengerInfo(adults=adults),
        flight_segments=[
            {
                "departure_airport": [[Airport[origin.upper()], 0]],
                "arrival_airport": [[Airport[destination.upper()], 0]],
                "travel_date": date,
            },
            {
                "departure_airport": [[Airport[destination.upper()], 0]],
                "arrival_airport": [[Airport[origin.upper()], 0]],
                "travel_date": return_date,
            },
        ],
    )

    pairs = _run_search(
        filters, top_n=MAX_ROUND_TRIP_OUTBOUNDS, currency=currency
    )

    offers = [
        {
            "price": ret.price,
            "currency": ret.currency or currency,
            "outbound": outbound.model_dump(mode="json"),
            "return": ret.model_dump(mode="json"),
        }
        for outbound, ret in pairs
        if ret.price is not None
    ]
    offers.sort(key=lambda o: o["price"])
    return offers[:MAX_ROUND_TRIP_RESULTS]
