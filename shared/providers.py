"""Flight data provider — wraps the `fli` library (reverse-engineered Google Flights).

fli has no API key and no official quota. It depends on an internal Google
endpoint that can change shape without notice — see docs/api-contract.md
open questions. Every call here is expected to occasionally fail with
ProviderUnavailableError; callers should map that to a 502.
"""

from fli.models import Airport, FlightSearchFilters, PassengerInfo
from fli.search import SearchFlights
from fli.search.exceptions import SearchClientError
from fli.search.flights import SearchParseError

from shared.utils.logging import log


class ProviderUnavailableError(Exception):
    """Raised when fli cannot be reached or its response can't be parsed."""


def is_valid_iata(code: str) -> bool:
    """Return True if *code* is a known 3-letter IATA airport code."""
    return code.upper() in Airport.__members__


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

    try:
        results = SearchFlights().search(filters, currency=currency)
    except (SearchClientError, SearchParseError) as exc:
        raise ProviderUnavailableError(str(exc)) from exc
    except (
        Exception
    ) as exc:  # fli wraps curl_cffi/network errors as bare exceptions too
        log.warning("Unexpected error calling fli: %s", exc)
        raise ProviderUnavailableError(str(exc)) from exc

    if not results:
        return []

    # One-way searches never expand into round-trip tuples.
    return [r.model_dump(mode="json") for r in results if r.price is not None]
