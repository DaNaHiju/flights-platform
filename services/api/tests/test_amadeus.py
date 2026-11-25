"""Unit tests for the Amadeus client and provider. The gateway is mocked."""

import httpx
import pytest
import redis

from shared import cache
from shared.providers import (
    ProviderBadRequestError,
    ProviderNotConfiguredError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from shared.providers.amadeus import (
    AmadeusProvider,
    display_name,
    normalize_keyword,
)
from tests.amadeus_fixtures import (
    AIRLINES,
    AIRLINES_RESPONSE,
    LOCATIONS,
    LOCATIONS_RESPONSE,
    ROUND_TRIP_RESPONSE,
    SEARCH,
    TEST_API_KEY,
    FakeGateway,
    flight,
    json_response,
    result,
    standard_gateway,
)

# --- one-way search ------------------------------------------------------------


def test_one_way_sends_documented_query_and_auth_header():
    gw = standard_gateway()
    gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 2, "USD")

    request = gw.calls(SEARCH)[0]
    assert request.headers["X-API-Key"] == TEST_API_KEY
    params = request.url.params
    assert params["origins"] == "TLV"
    assert params["destinations"] == "MAD"
    assert params["dates"] == "2099-01-01"
    assert params["flow"] == "NETWORK"
    assert params["adults"] == "2"
    assert params["currency"] == "USD"
    assert params["locale"] == "en-US"
    assert params["number_of_results"] == "20"


def test_pinned_airport_plus_is_sent_percent_encoded():
    gw = standard_gateway()
    gw.provider().search_one_way("LCY+", "MAD", "2099-01-01", 1, "USD")

    raw_query = gw.calls(SEARCH)[0].url.query.decode()
    # "+" must arrive as %2B: a raw "+" decodes as a space and fails validation.
    assert "origins=LCY%2B" in raw_query


def test_one_way_offers_are_parsed_and_sorted_by_price():
    gw = standard_gateway()
    offers = gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")

    assert [o.price for o in offers] == [199.0, 250.5, 410.0]
    ly = offers[1]
    assert ly.currency == "USD"
    assert ly.merchant == "LY"
    assert ly.deep_link == "https://example.test/LY/book"
    assert ly.primary_airline == "El Al Israel Airlines"
    assert ly.primary_airline_code == "LY"
    assert ly.stops == 0
    leg = ly.legs[0]
    assert leg.flight_number == "LY395"
    # Local times with their offsets, exactly as sent: no timezone conversion.
    assert leg.departure_datetime == "2099-01-01T08:00:00+02:00"
    assert leg.arrival_datetime == "2099-01-01T12:15:00+01:00"
    assert leg.duration_minutes == 315
    assert (leg.departure_airport_code, leg.arrival_airport_code) == ("TLV", "MAD")
    assert (leg.arrival_city, leg.arrival_country_code) == ("Madrid", "ES")


def test_connection_has_stops_partner_names_and_no_deep_link():
    gw = standard_gateway()
    lh = gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")[0]

    assert lh.stops == 1
    assert lh.deep_link is None  # shown without a link, not dropped
    assert lh.carriers == ["Lufthansa", "Swiss"]
    assert lh.legs[1].operating_airline == "Lufthansa"
    # 05:00+02:00 -> 12:35+01:00 is 8h35m elapsed, layover included.
    assert lh.total_duration_minutes == 8 * 60 + 35


def test_total_duration_uses_offsets_not_bound_duration():
    # The skill's DST example: 31h40m elapsed while bound.duration says 32:40.
    gw = FakeGateway().on(AIRLINES, AIRLINES_RESPONSE)
    ey = flight("EY", "20", "LHR", "AUH", "2027-03-27T18:00:00Z", "2027-03-28T05:00:00+04:00", "07:00")
    ey2 = flight("EY", "474", "AUH", "SIN", "2027-03-28T22:00:00+04:00", "2027-03-29T09:40:00+08:00", "07:40")
    body = {"results": [result("EY", 900.0, [[ey, ey2]])]}
    body["results"][0]["bounds"][0]["duration"] = "32:40"
    gw.on(SEARCH, body)

    offer = gw.provider().search_one_way("LHR", "SIN", "2027-03-27", 1, "USD")[0]
    assert offer.total_duration_minutes == 31 * 60 + 40


def test_results_without_price_are_dropped():
    no_price = result("LY", 1.0, [[flight("LY", "1", "TLV", "MAD", "2099-01-01T08:00:00+02:00", "2099-01-01T12:00:00+01:00", "05:00")]])
    no_price["fare"]["itinerary_price"] = {}
    gw = FakeGateway().on(SEARCH, {"results": [no_price]}).on(AIRLINES, AIRLINES_RESPONSE)
    assert gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD") == []


def test_offer_ids_are_stable_and_distinct():
    first = standard_gateway().provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    second = standard_gateway().provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert [o.offer_id for o in first] == [o.offer_id for o in second]
    assert len({o.offer_id for o in first}) == 3


# --- round trip ----------------------------------------------------------------


def test_round_trip_builds_positional_lists_and_pairs():
    gw = FakeGateway().on(SEARCH, ROUND_TRIP_RESPONSE).on(AIRLINES, AIRLINES_RESPONSE)
    pairs = gw.provider().search_round_trip("TLV", "MAD", "2099-01-01", "2099-01-08", 1, "USD")

    params = gw.calls(SEARCH)[0].url.params
    assert params["origins"] == "TLV,MAD"
    assert params["destinations"] == "MAD,TLV"
    assert params["dates"] == "2099-01-01,2099-01-08"

    assert [p.price for p in pairs] == [480.0, 520.0]
    cheapest = pairs[0]
    assert cheapest.deep_link == "https://example.test/UX/book"
    assert cheapest.outbound.legs[0].flight_number == "UX1302"
    assert cheapest.return_.legs[0].flight_number == "LY396"
    dumped = cheapest.model_dump(by_alias=True)
    assert set(dumped) >= {"price", "currency", "outbound", "return", "deep_link"}


# --- airline names (lookup + cache) --------------------------------------------


def test_airline_names_are_one_batched_call_then_cached(fake_redis):
    gw = standard_gateway()
    provider = gw.provider()
    provider.search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    provider.search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")

    lookups = gw.calls(AIRLINES)
    assert len(lookups) == 1
    assert lookups[0].url.params["airlineCodes"] == "LH,LX,LY,UX"
    assert '"Swiss"' == fake_redis.store["airline:LX"]


def test_unknown_airline_code_is_shown_as_code_and_cached():
    gw = FakeGateway().on(AIRLINES, AIRLINES_RESPONSE)
    provider = gw.provider()
    assert provider.airline_names(["XX", "LY"]) == {"XX": "XX", "LY": "El Al Israel Airlines"}
    provider.airline_names(["XX"])
    assert len(gw.calls(AIRLINES)) == 1


def test_airline_lookup_failure_falls_back_to_codes_without_failing_search():
    gw = standard_gateway()
    gw._routes[AIRLINES] = [json_response({}, status=500)]
    offers = gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert offers[1].primary_airline == "LY"


def test_display_name():
    assert display_name("BRITISH AIRWAYS") == "British Airways"
    assert display_name("KLM ROYAL DUTCH AIRLINES") == "KLM Royal Dutch Airlines"


# --- error handling --------------------------------------------------------------


def test_429_with_short_retry_after_waits_once_and_succeeds():
    gw = standard_gateway()
    gw._routes[SEARCH] = [
        json_response({}, status=429, headers={"Retry-After": "1"}),
        gw._routes[SEARCH][0],
    ]
    offers = gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert len(offers) == 3
    assert gw.sleeps == [1]


def test_429_twice_raises_rate_limited():
    gw = FakeGateway().on(SEARCH, json_response({}, status=429, headers={"Retry-After": "1"}))
    with pytest.raises(ProviderRateLimitedError):
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert len(gw.calls(SEARCH)) == 2


def test_429_with_long_retry_after_is_not_waited_inline():
    gw = FakeGateway().on(SEARCH, json_response({}, status=429, headers={"Retry-After": "30"}))
    with pytest.raises(ProviderRateLimitedError) as info:
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert info.value.retry_after == 30
    assert gw.sleeps == []
    assert len(gw.calls(SEARCH)) == 1


def test_search_wide_rate_limit_code_in_errors_raises_rate_limited():
    gw = FakeGateway().on(SEARCH, {"results": [], "errors": {"*": "126 - Rate limit reached"}})
    with pytest.raises(ProviderRateLimitedError):
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")


def test_no_offers_from_any_merchant_is_an_empty_result():
    gw = FakeGateway().on(SEARCH, {"results": [], "errors": {"LY": "120 - No flight found"}})
    assert gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD") == []


def test_server_error_is_retried_once():
    gw = standard_gateway()
    gw._routes[SEARCH] = [json_response({}, status=500), gw._routes[SEARCH][0]]
    assert len(gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")) == 3


def test_two_server_errors_raise_unavailable():
    gw = FakeGateway().on(SEARCH, json_response({}, status=503))
    with pytest.raises(ProviderUnavailableError):
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert len(gw.calls(SEARCH)) == 2


def test_timeout_raises_unavailable_without_retry():
    gw = FakeGateway().on(SEARCH, httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderUnavailableError):
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert len(gw.calls(SEARCH)) == 1


def test_connection_error_raises_unavailable():
    gw = FakeGateway().on(SEARCH, httpx.ConnectError("dns"))
    with pytest.raises(ProviderUnavailableError):
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")


@pytest.mark.parametrize(
    "response",
    [
        json_response({"errors": [{"code": 38187, "title": "Invalid parameters"}]}, status=400),
        json_response({"errors": [{"code": 38191, "title": "Invalid HTTP header"}]}, status=401),
    ],
)
def test_rejected_api_key_is_unavailable_not_bad_request(response):
    gw = FakeGateway().on(SEARCH, response)
    with pytest.raises(ProviderUnavailableError):
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")


def test_validation_error_is_bad_request_with_reason():
    body = {"message": '{"dates":"must be today or later"}'}
    gw = FakeGateway().on(SEARCH, json_response(body, status=400))
    with pytest.raises(ProviderBadRequestError, match="today or later"):
        gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")


def test_missing_api_key_raises_not_configured_without_any_call():
    provider = AmadeusProvider(None)
    with pytest.raises(ProviderNotConfiguredError):
        provider.search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    with pytest.raises(ProviderNotConfiguredError):
        provider.search_locations("Madrid")


# --- locations typeahead -------------------------------------------------------


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("Paris, France", "Paris"),
        ("Málaga", "Malaga"),
        ("Tromsø", "Tromso"),
        ("LON&", "LON"),
        ("  New   York ", "New York"),
        ("x" * 40, "x" * 30),
    ],
)
def test_normalize_keyword(typed, expected):
    assert normalize_keyword(typed) == expected


def test_locations_query_encoding_and_parsing():
    gw = standard_gateway()
    results = gw.provider().search_locations("San José")

    raw_query = gw.calls(LOCATIONS)[0].url.query.decode()
    assert "keyword=San%20Jose" in raw_query  # %20, never "+"
    assert "subType=AIRPORT,CITY" in raw_query
    assert "page%5Blimit%5D=8" in raw_query

    assert [r.id for r in results] == ["CMAD", "AMAD"]  # deduplicated by id
    city, airport = results
    assert (city.sub_type, city.search_code, city.name) == ("CITY", "MAD", "Madrid")
    assert (airport.sub_type, airport.search_code) == ("AIRPORT", "MAD+")
    assert (airport.city_name, airport.country_name, airport.country_code) == (
        "Madrid",
        "Spain",
        "ES",
    )


def test_locations_are_cached_per_keyword(fake_redis):
    gw = standard_gateway()
    provider = gw.provider()
    provider.search_locations("Madrid")
    again = provider.search_locations("madrid")
    assert len(gw.calls(LOCATIONS)) == 1
    assert [r.id for r in again] == ["CMAD", "AMAD"]
    assert "locations:madrid" in fake_redis.store


def test_too_short_keyword_makes_no_call():
    gw = standard_gateway()
    assert gw.provider().search_locations("M") == []
    assert gw.provider().search_locations("!!") == []
    assert gw.calls(LOCATIONS) == []


class DownRedis:
    def get(self, key):
        raise redis.ConnectionError("down")

    def set(self, key, value, ex=None):
        raise redis.ConnectionError("down")


def test_redis_down_does_not_fail_lookups(monkeypatch):
    monkeypatch.setattr(cache, "redis_client", DownRedis())
    gw = standard_gateway()
    assert len(gw.provider().search_locations("Madrid")) == 2
    assert len(gw.provider().search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")) == 3


def test_locations_response_snapshot_is_unchanged():
    # Guards the fixture itself: the duplicate record must stay in it.
    assert len(LOCATIONS_RESPONSE["data"]) == 3
