"""FlightProvider backed by the Amadeus Travel Builder APIs.

Three endpoints are used, all authenticated with an `X-API-Key` header:

- GET /api/v3/search/                    flight search (one-way, round trip)
- GET /v1/reference-data/airlines        airline code -> airline name
- GET /v1/reference-data/locations       airport / city typeahead

Two layers, kept apart on purpose:

- AmadeusClient: HTTP only. Auth header, timeouts, retries, and mapping of
  HTTP failures to the provider errors in shared.providers.base. No parsing.
- AmadeusProvider: turns Amadeus responses into the provider-neutral schemas
  (shared.schemas) and caches reference data (airlines, locations) in Redis.

The API key never leaves this process: it is read from the environment and
only ever sent to the Amadeus gateway.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime
from typing import Callable, Iterable
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from shared.airports import airport_name
from shared.cache import try_get_json, try_set_json
from shared.providers.base import (
    ProviderBadRequestError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from shared.schemas import (
    CheckedBag,
    FlightOffer,
    Leg,
    Location,
    RoundTripOffer,
    airport_fields,
)
from shared.utils.logging import log

SEARCH_PATH = "/api/v3/search/"
AIRLINES_PATH = "/v1/reference-data/airlines"
LOCATIONS_PATH = "/v1/reference-data/locations"

CONNECT_TIMEOUT_SECONDS = 3.0
# On a 429 we wait inline once, but only if the gateway asks for a short wait.
# Anything longer is better answered with a 503 + Retry-After than a hung request.
MAX_INLINE_RETRY_WAIT_SECONDS = 2.0
SERVER_ERROR_RETRY_WAIT_SECONDS = 0.5
# Gateway error code for an invalid API key (sent with HTTP 400, not 401).
INVALID_API_KEY_CODE = "38187"
# Merchant error codes meaning "rate limited" (126 is for the whole search).
MERCHANT_RATE_LIMIT_CODES = ("123", "126")
# The airline lookup's query string is capped at 2048 bytes: ~100 codes is safe.
AIRLINE_CODES_PER_REQUEST = 100
TYPEAHEAD_RESULTS = 8
KEYWORD_MAX_LENGTH = 30
KEYWORD_MIN_LENGTH = 2


def _query(params: Iterable[tuple[str, str]]) -> str:
    """Build a query string by hand.

    Form encoders (urlencode, httpx params) write a space as "+", which the
    locations endpoint rejects, and they would mangle the "+" that pins an
    airport. quote() percent-encodes both: " " -> %20, "+" -> %2B, while commas
    stay raw because the lists are comma-separated.
    """
    return "&".join(
        f"{quote(name, safe='')}={quote(str(value), safe=',')}" for name, value in params
    )


def _error_detail(response: httpx.Response) -> str:
    """Short human-readable reason from any of the gateway's error body shapes."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict):
        # Flight search 400: "message" is itself a JSON string of param -> reason.
        if "message" in body:
            return str(body["message"])[:300]
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            return f"{first.get('code')} {first.get('title')} {first.get('detail') or ''}".strip()
    return str(body)[:200]


def _gateway_code(response: httpx.Response) -> str | None:
    try:
        errors = response.json().get("errors")
        return str(errors[0].get("code")) if errors else None
    except (ValueError, AttributeError, IndexError, TypeError):
        return None


def _retry_after_seconds(response: httpx.Response, default: int = 1) -> int:
    try:
        return max(1, int(response.headers.get("Retry-After", default)))
    except ValueError:
        return default


class AmadeusClient:
    """HTTP access to the Amadeus gateway: auth, timeouts, retries, error mapping."""

    def __init__(
        self,
        api_key: str,
        gateway_url: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._http = httpx.Client(
            base_url=gateway_url.rstrip("/"),
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            transport=transport,
        )
        self._sleep = sleep

    def get(self, path: str, query: str, timeout: float) -> dict:
        """GET path?query and return the JSON body, or raise a ProviderError.

        Retries at most once: after a 5xx, or after a 429 that asks for a short
        wait. Timeouts are NOT retried: a search that already took `timeout`
        seconds would double the user's wait for little chance of success.
        """
        url = f"{path}?{query}"
        for attempt in (1, 2):
            try:
                response = self._http.get(
                    url, timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS)
                )
            except httpx.TimeoutException as exc:
                raise ProviderUnavailableError(
                    f"Amadeus did not answer within {timeout}s ({path})"
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError(f"Amadeus unreachable: {exc}") from exc

            status = response.status_code
            if status == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise ProviderUnavailableError("Amadeus sent a non-JSON body") from exc

            if status == 429:
                wait = _retry_after_seconds(response)
                if attempt == 1 and wait <= MAX_INLINE_RETRY_WAIT_SECONDS:
                    self._sleep(wait)
                    continue
                raise ProviderRateLimitedError(
                    f"Amadeus rate limit reached ({path})", retry_after=wait
                )

            if status >= 500:
                if attempt == 1:
                    self._sleep(SERVER_ERROR_RETRY_WAIT_SECONDS)
                    continue
                raise ProviderUnavailableError(f"Amadeus HTTP {status} ({path})")

            if status == 401 or _gateway_code(response) == INVALID_API_KEY_CODE:
                # Our configuration, not the user's input: never a 400 to the user.
                log.error("Amadeus rejected the API key; check AMADEUS_API_KEY")
                raise ProviderUnavailableError("Amadeus rejected the API key")

            if status == 400:
                raise ProviderBadRequestError(_error_detail(response))

            raise ProviderUnavailableError(
                f"Amadeus HTTP {status} ({path}): {_error_detail(response)}"
            )
        # Unreachable: the second attempt always returns or raises.
        raise ProviderUnavailableError("Amadeus retry loop exhausted")


# --- Parsing helpers ----------------------------------------------------------


def _hhmm_to_minutes(value: str | None) -> int:
    """"01:15" -> 75; "32:40" -> 1960 (can exceed 24 h); missing -> 0."""
    if not value or ":" not in value:
        return 0
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _elapsed_minutes(departs_at: str, arrives_at: str) -> int | None:
    """Minutes between two timestamps, honouring each one's own UTC offset.

    This is the reliable total: a bound's own `duration` can be 60 minutes off
    when a layover spans a daylight-saving change.
    """
    try:
        start = datetime.fromisoformat(departs_at)
        end = datetime.fromisoformat(arrives_at)
    except (TypeError, ValueError):
        return None
    if start.tzinfo is None or end.tzinfo is None:
        return None
    return int((end - start).total_seconds() // 60)


def _checked_bags(bound: dict) -> list[CheckedBag] | None:
    """The checked bags included in a bound's fare, or None when unknown.

    None covers a bound with no `included_checked_bags` and one with an item we
    cannot read: a guess ("no bag") would be worse than saying nothing. A list
    that is present but empty is a real answer, so it stays an empty list.
    """
    raw = bound.get("included_checked_bags")
    if not isinstance(raw, list):
        return None
    bags: list[CheckedBag] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("type") not in ("piece", "weight"):
            return None
        try:
            unit = item.get("weight_unit")
            bags.append(
                CheckedBag(
                    type=item["type"],
                    quantity=item.get("quantity"),
                    weight_amount=item.get("weight_amount"),
                    weight_unit=unit.upper() if isinstance(unit, str) else None,
                    applicable_legs=item.get("applicable_legs") or [],
                )
            )
        except ValidationError:
            return None
    return bags


_SHORT_UPPER = re.compile(r"^[^AEIOUY]{1,3}$")
# Airline names that are acronyms but contain a vowel, so the consonant rule
# above would turn them into "Ita" or "Sas". Kept short on purpose: add a name
# here when an airline shows up wrongly capitalised.
_KNOWN_ACRONYMS = frozenset({"ITA", "TAP", "LOT", "SAS", "KLM", "ANA", "JAL"})


def _display_word(word: str) -> str:
    if word.upper() in _KNOWN_ACRONYMS:
        return word.upper()
    if _SHORT_UPPER.match(word):
        return word  # consonant-only, such as "KLM": already an acronym
    return word.capitalize()


def display_name(value: str) -> str:
    """"BRITISH AIRWAYS" -> "British Airways"; acronyms ("KLM", "ITA") stay upper case."""
    return " ".join(_display_word(word) for word in value.split())


_TRANSLITERATE = str.maketrans(
    {"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D"}
)
_KEYWORD_DISALLOWED = re.compile(r"[^A-Za-z0-9 '\"()/:.\-]")


def normalize_keyword(text: str) -> str:
    """Make typed text acceptable to the locations endpoint.

    Keep only the place name (text before the first comma), transliterate to
    ASCII ("Málaga" -> "Malaga"), replace any other disallowed character with a
    space (one stray "&" would fail the whole request) and cap at 30 chars.
    """
    text = text.split(",", 1)[0].translate(_TRANSLITERATE)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = _KEYWORD_DISALLOWED.sub(" ", text)
    return " ".join(text.split())[:KEYWORD_MAX_LENGTH].strip()


def _offer_id(result: dict) -> str:
    """Stable id for an offer: the same itinerary and price always hash the same."""
    flights = [
        (f.get("marketing_airline"), f.get("flight_number"), f.get("departs_at"))
        for bound in result.get("bounds", [])
        for f in bound.get("flights", [])
    ]
    fare = result.get("fare", {})
    material = json.dumps(
        [
            result.get("merchant"),
            flights,
            fare.get("currency"),
            fare.get("itinerary_price", {}).get("total_fare"),
        ],
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()[:24]


class AmadeusProvider:
    """FlightProvider implementation on top of AmadeusClient."""

    name = "amadeus"

    def __init__(
        self,
        client: AmadeusClient | None,
        search_timeout: float = 25.0,
        lookup_timeout: float = 5.0,
        max_results_per_merchant: int = 20,
        airlines_cache_ttl: int = 604800,
        locations_cache_ttl: int = 86400,
    ):
        # client is None when no API key is configured: the service still
        # starts, and every call raises ProviderNotConfiguredError (API: 503).
        self._client = client
        self._search_timeout = search_timeout
        self._lookup_timeout = lookup_timeout
        self._max_results = max_results_per_merchant
        self._airlines_ttl = airlines_cache_ttl
        self._locations_ttl = locations_cache_ttl

    def _require_client(self) -> AmadeusClient:
        if self._client is None:
            raise ProviderNotConfiguredError("AMADEUS_API_KEY is not set")
        return self._client

    # --- Flight search -------------------------------------------------------

    def _search(
        self,
        origins: list[str],
        destinations: list[str],
        dates: list[str],
        adults: int,
        currency: str,
    ) -> list[dict]:
        """Raw `results` of one search call. Lists are positional: leg i is
        origins[i] -> destinations[i] on dates[i]."""
        client = self._require_client()
        query = _query(
            [
                ("origins", ",".join(origins)),
                ("destinations", ",".join(destinations)),
                ("dates", ",".join(dates)),
                ("locale", "en-US"),
                ("flow", "NETWORK"),
                ("adults", str(adults)),
                ("travel_class", "ECONOMY"),
                ("currency", currency),
                ("number_of_results", str(self._max_results)),
            ]
        )
        body = client.get(SEARCH_PATH, query, timeout=self._search_timeout)
        results = body.get("results") or []
        errors = body.get("errors") or {}

        # A merchant with no offers does not fail the search: it appears in
        # `errors`. Only a search-wide rate limit with nothing to show is an error.
        if not results and str(errors.get("*", "")).startswith(MERCHANT_RATE_LIMIT_CODES):
            raise ProviderRateLimitedError("Amadeus search-wide rate limit")
        if errors:
            route = ", ".join(
                f"{o}->{d} on {day}" for o, d, day in zip(origins, destinations, dates)
            )
            log.info("Amadeus: %d merchant(s) returned no offers for %s", len(errors), route)
        return [r for r in results if self._total_price(r) is not None]

    @staticmethod
    def _total_price(result: dict) -> float | None:
        return result.get("fare", {}).get("itinerary_price", {}).get("total_fare")

    def search_one_way(
        self, origin: str, destination: str, date: str, adults: int, currency: str
    ) -> list[FlightOffer]:
        results = self._search([origin], [destination], [date], adults, currency)
        names = self.airline_names(_airline_codes(results))
        offers = [
            self._bound_offer(r, r["bounds"][0], names, _offer_id(r))
            for r in results
            if r.get("bounds")
        ]
        offers.sort(key=lambda o: o.price)
        return offers

    def search_round_trip(
        self,
        origin: str,
        destination: str,
        date: str,
        return_date: str,
        adults: int,
        currency: str,
    ) -> list[RoundTripOffer]:
        # The return leg flies back to where the outbound left from. A pinned
        # airport ("LHR+") stays pinned on the way back.
        results = self._search(
            [origin, destination], [destination, origin], [date, return_date], adults, currency
        )
        names = self.airline_names(_airline_codes(results))
        pairs = []
        for r in results:
            bounds = r.get("bounds") or []
            if len(bounds) != 2:
                continue
            offer_id = _offer_id(r)
            outbound = self._bound_offer(r, bounds[0], names, f"{offer_id}-out")
            inbound = self._bound_offer(r, bounds[1], names, f"{offer_id}-ret")
            pairs.append(
                RoundTripOffer(
                    price=outbound.price,
                    currency=outbound.currency,
                    merchant=r.get("merchant"),
                    deep_link=r.get("deep_link"),
                    outbound=outbound,
                    return_=inbound,
                )
            )
        pairs.sort(key=lambda p: p.price)
        return pairs

    def _bound_offer(
        self, result: dict, bound: dict, names: dict[str, str], offer_id: str
    ) -> FlightOffer:
        """One bound of a result as a FlightOffer.

        The price is always the whole offer's total: Amadeus sells a round trip
        as one fare, and a per-bound price is not sent by every airline.
        """
        flights = bound.get("flights") or []
        legs = [_leg(f, names) for f in flights]
        total = None
        if flights:
            total = _elapsed_minutes(flights[0]["departs_at"], flights[-1]["arrives_at"])
        if total is None:
            total = _hhmm_to_minutes(bound.get("duration"))

        carriers: list[str] = []
        for leg in legs:
            if leg.airline not in carriers:
                carriers.append(leg.airline)

        fare = result.get("fare", {})
        first = legs[0] if legs else None
        return FlightOffer(
            offer_id=offer_id,
            price=float(self._total_price(result)),
            currency=fare.get("currency", ""),
            duration_minutes=total,
            total_duration_minutes=total,
            stops=max(len(legs) - 1, 0),
            primary_airline=first.airline if first else "",
            primary_airline_code=first.airline_code if first else None,
            carriers=carriers,
            merchant=result.get("merchant"),
            deep_link=result.get("deep_link"),
            checked_bags=_checked_bags(bound),
            legs=legs,
        )

    # --- Airline names (reference data, cached) ------------------------------

    def airline_names(self, codes: Iterable[str]) -> dict[str, str]:
        """Map airline codes to display names, one batched call for cache misses.

        Never fails a search: on a lookup error the codes themselves are shown.
        Unknown codes are cached too (as the code), so they do not trigger a
        lookup on every search.
        """
        names: dict[str, str] = {}
        missing: list[str] = []
        for code in sorted(set(codes)):
            cached = try_get_json(f"airline:{code}")
            if cached is not None:
                names[code] = cached
            else:
                missing.append(code)
        if not missing:
            return names

        client = self._require_client()
        for start in range(0, len(missing), AIRLINE_CODES_PER_REQUEST):
            chunk = missing[start : start + AIRLINE_CODES_PER_REQUEST]
            try:
                body = client.get(
                    AIRLINES_PATH,
                    _query([("airlineCodes", ",".join(chunk))]),
                    timeout=self._lookup_timeout,
                )
            except ProviderError as exc:
                log.warning("Airline name lookup failed, showing codes: %s", exc)
                names.update({code: names.get(code, code) for code in chunk})
                continue

            found: dict[str, str] = {}
            for record in body.get("data") or []:
                business = record.get("businessName")
                if not business or business == "UNDEFINED":
                    continue
                for key in (record.get("iataCode"), record.get("icaoCode")):
                    if key:
                        found[key.upper()] = display_name(business)
            for code in chunk:
                name = found.get(code, code)
                names[code] = name
                try_set_json(f"airline:{code}", name, ttl=self._airlines_ttl)
        return names

    # --- Airport / city typeahead (reference data, cached) -------------------

    def search_locations(self, keyword: str) -> list[Location]:
        normalized = normalize_keyword(keyword)
        if len(normalized) < KEYWORD_MIN_LENGTH:
            return []

        cache_key = f"locations:{normalized.lower()}"
        cached = try_get_json(cache_key)
        if cached is not None:
            return [Location.model_validate(item) for item in cached]

        client = self._require_client()
        query = _query(
            [
                ("subType", "AIRPORT,CITY"),
                ("keyword", normalized),
                ("page[limit]", str(TYPEAHEAD_RESULTS)),
                ("view", "FULL"),
            ]
        )
        body = client.get(LOCATIONS_PATH, query, timeout=self._lookup_timeout)

        locations: list[Location] = []
        seen: set[str] = set()
        for record in body.get("data") or []:
            # Keyed by id, not IATA code: AMAD (airport) and CMAD (city) share "MAD".
            location = _location(record)
            if location and location.id not in seen:
                seen.add(location.id)
                locations.append(location)

        try_set_json(
            cache_key, [loc.model_dump() for loc in locations], ttl=self._locations_ttl
        )
        return locations


def _airline_codes(results: list[dict]) -> set[str]:
    """Every marketing and (IATA) operating airline code in a result set."""
    codes: set[str] = set()
    for r in results:
        for bound in r.get("bounds", []):
            for f in bound.get("flights", []):
                if f.get("marketing_airline"):
                    codes.add(f["marketing_airline"])
                if f.get("operating_airline") and f.get("operating_airline_type") != "FREE_TEXT":
                    codes.add(f["operating_airline"])
    return codes


def _leg(flight: dict, names: dict[str, str]) -> Leg:
    code = flight["marketing_airline"]
    dep = flight["origin"]["airport"]
    arr = flight["destination"]["airport"]

    operating = None
    op_code = flight.get("operating_airline")
    if op_code and op_code != code:
        operating = (
            op_code
            if flight.get("operating_airline_type") == "FREE_TEXT"
            else names.get(op_code, op_code)
        )

    return Leg(
        airline=names.get(code, code),
        airline_code=code,
        flight_number=f"{code}{flight['flight_number']}",
        operating_airline=operating,
        departure_airport=airport_name(dep) or dep,
        arrival_airport=airport_name(arr) or arr,
        departure_datetime=flight["departs_at"],
        arrival_datetime=flight["arrives_at"],
        duration_minutes=_hhmm_to_minutes(flight.get("duration")),
        **airport_fields("departure", dep),
        **airport_fields("arrival", arr),
    )


def _location(record: dict) -> Location | None:
    iata = record.get("iataCode")
    sub_type = record.get("subType")
    if not iata or sub_type not in ("AIRPORT", "CITY"):
        return None
    address = record.get("address") or {}
    country_code = address.get("countryCode")
    return Location(
        id=record.get("id") or f"{sub_type[0]}{iata}",
        iata_code=iata,
        sub_type=sub_type,
        name=display_name(record.get("name") or iata),
        detailed_name=record.get("detailedName"),
        city_name=display_name(address["cityName"]) if address.get("cityName") else None,
        city_code=address.get("cityCode"),
        country_name=display_name(address["countryName"]) if address.get("countryName") else None,
        country_code=None if country_code == "ZZ" else country_code,
        # An airport pick searches that airport only; a city covers all of its airports.
        search_code=f"{iata}+" if sub_type == "AIRPORT" else iata,
    )
