"""Tests for GET /flights: validation, caching and error mapping.

The provider is a stub here; tests/test_amadeus.py covers the real one.
"""

import redis
from fastapi.testclient import TestClient

from shared import cache
from shared.providers import (
    ProviderBadRequestError,
    ProviderNotConfiguredError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from shared.schemas import FlightOffer, Leg, RoundTripOffer

PARAMS = {"origin": "TLV", "destination": "MAD", "date": "2099-01-01"}
RT_PARAMS = {**PARAMS, "return_date": "2099-01-08"}


def make_offer(offer_id: str = "offer-1", price: float = 250.0) -> FlightOffer:
    leg = Leg(
        airline="El Al Israel Airlines",
        airline_code="LY",
        flight_number="LY395",
        departure_airport="Ben Gurion International Airport",
        arrival_airport="Adolfo Suarez Madrid-Barajas Airport",
        departure_datetime="2099-01-01T08:00:00+02:00",
        arrival_datetime="2099-01-01T12:15:00+01:00",
        duration_minutes=315,
        departure_airport_code="TLV",
        arrival_airport_code="MAD",
    )
    return FlightOffer(
        offer_id=offer_id,
        price=price,
        currency="USD",
        duration_minutes=315,
        total_duration_minutes=315,
        stops=0,
        primary_airline="El Al Israel Airlines",
        primary_airline_code="LY",
        carriers=["El Al Israel Airlines"],
        merchant="LY",
        deep_link="https://example.test/LY/book",
        legs=[leg],
    )


class StubProvider:
    """Records calls; returns *offers* or raises *error*."""

    name = "stub"

    def __init__(self, offers=None, error=None):
        self.offers = offers if offers is not None else [make_offer()]
        self.error = error
        self.calls: list[tuple] = []

    def search_one_way(self, *args):
        self.calls.append(("one_way", *args))
        if self.error:
            raise self.error
        return self.offers

    def search_round_trip(self, *args):
        self.calls.append(("round_trip", *args))
        if self.error:
            raise self.error
        return [
            RoundTripOffer(
                price=500.0,
                currency="USD",
                deep_link="https://example.test/rt",
                outbound=make_offer("o"),
                return_=make_offer("r"),
            )
        ]

    def search_locations(self, keyword):
        self.calls.append(("locations", keyword))
        if self.error:
            raise self.error
        return []


# --- validation ----------------------------------------------------------------


def test_invalid_code_is_400(client: TestClient, use_provider):
    stub = use_provider(StubProvider())
    response = client.get("/flights/", params={**PARAMS, "origin": "AB1"})
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_iata_code"}
    assert stub.calls == []


def test_pinned_airport_code_is_accepted_and_passed_through(client, use_provider):
    stub = use_provider(StubProvider())
    response = client.get("/flights/", params={**PARAMS, "origin": "tlv+"})
    assert response.status_code == 200
    assert stub.calls[0][1] == "TLV+"


def test_same_origin_and_destination_is_400(client, use_provider):
    use_provider(StubProvider())
    response = client.get("/flights/", params={**PARAMS, "destination": "TLV+"})
    assert response.status_code == 400
    assert response.json() == {"error": "same_origin_and_destination"}


def test_invalid_date_format(client, use_provider):
    use_provider(StubProvider())
    response = client.get("/flights/", params={**PARAMS, "date": "not-a-date"})
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_date_format"}


def test_date_in_past(client, use_provider):
    use_provider(StubProvider())
    response = client.get("/flights/", params={**PARAMS, "date": "2000-01-01"})
    assert response.json() == {"error": "date_in_past"}


def test_return_before_departure(client, use_provider):
    use_provider(StubProvider())
    response = client.get("/flights/", params={**PARAMS, "return_date": "2098-12-31"})
    assert response.json() == {"error": "return_before_departure"}


def test_return_date_invalid_format(client, use_provider):
    use_provider(StubProvider())
    response = client.get("/flights/", params={**PARAMS, "return_date": "nope"})
    assert response.json() == {"error": "invalid_date_format"}


# --- success and caching -------------------------------------------------------


def test_one_way_success_shape(client, use_provider):
    use_provider(StubProvider())
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 200
    data = response.json()
    assert (data["cached"], data["cached_at"]) == (False, None)
    offer = data["results"][0]
    assert offer["offer_id"] == "offer-1"
    assert offer["deep_link"] == "https://example.test/LY/book"
    assert offer["legs"][0]["departure_datetime"] == "2099-01-01T08:00:00+02:00"


def test_second_identical_search_is_served_from_cache(client, use_provider):
    stub = use_provider(StubProvider())
    first = client.get("/flights/", params=PARAMS)
    second = client.get("/flights/", params=PARAMS)
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["results"] == first.json()["results"]
    assert len(stub.calls) == 1


def test_empty_result_is_cached_too(client, use_provider):
    stub = use_provider(StubProvider(offers=[]))
    client.get("/flights/", params=PARAMS)
    second = client.get("/flights/", params=PARAMS)
    assert second.json() == {"results": [], "cached": True, "cached_at": second.json()["cached_at"]}
    assert len(stub.calls) == 1


def test_round_trip_has_its_own_cache_key_and_shape(client, use_provider):
    stub = use_provider(StubProvider())
    client.get("/flights/", params=PARAMS)
    rt = client.get("/flights/", params=RT_PARAMS)
    rt_again = client.get("/flights/", params=RT_PARAMS)

    assert [c[0] for c in stub.calls] == ["one_way", "round_trip"]
    body = rt.json()["results"][0]
    assert set(body) >= {"price", "currency", "deep_link", "outbound", "return"}
    assert rt_again.json()["cached"] is True


def test_cache_key_includes_provider_and_currency():
    from app.api.flights import _search_cache_key

    assert _search_cache_key("amadeus", "TLV", "MAD", "2099-01-01", 1, "USD") == (
        "search:amadeus:TLV:MAD:2099-01-01:1:USD"
    )
    assert _search_cache_key("amadeus", "TLV", "MAD", "2099-01-01", 1, "USD", "2099-01-08") != (
        _search_cache_key("amadeus", "TLV", "MAD", "2099-01-01", 1, "USD")
    )


def test_one_way_offers_are_cached_for_bookings(client, use_provider, fake_redis):
    use_provider(StubProvider())
    client.get("/flights/", params=PARAMS)
    assert "offer:offer-1" in fake_redis.store


class DownRedis:
    def get(self, key):
        raise redis.ConnectionError("down")

    def set(self, key, value, ex=None):
        raise redis.ConnectionError("down")

    def ping(self):
        return False


def test_search_still_works_when_redis_is_down(client, use_provider, monkeypatch):
    monkeypatch.setattr(cache, "redis_client", DownRedis())
    use_provider(StubProvider())
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 200
    assert response.json()["cached"] is False


# --- error mapping -------------------------------------------------------------


def test_provider_unavailable_is_502(client, use_provider):
    use_provider(StubProvider(error=ProviderUnavailableError("timeout")))
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 502
    assert response.json() == {"error": "provider_unavailable"}


def test_rate_limited_is_503_with_retry_after(client, use_provider):
    use_provider(StubProvider(error=ProviderRateLimitedError("quota", retry_after=42)))
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 503
    assert response.json() == {"error": "provider_rate_limited"}
    assert response.headers["Retry-After"] == "42"


def test_not_configured_is_503(client, use_provider):
    use_provider(StubProvider(error=ProviderNotConfiguredError("no key")))
    response = client.get("/flights/", params=RT_PARAMS)
    assert response.status_code == 503
    assert response.json() == {"error": "provider_not_configured"}


def test_provider_bad_request_is_400(client, use_provider):
    use_provider(StubProvider(error=ProviderBadRequestError("bad dates")))
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_search"}


def test_errors_are_not_cached(client, use_provider):
    stub = use_provider(StubProvider(error=ProviderUnavailableError("x")))
    client.get("/flights/", params=PARAMS)
    client.get("/flights/", params=PARAMS)
    assert len(stub.calls) == 2


def test_errors_are_counted_by_reason(client, use_provider):
    use_provider(StubProvider(error=ProviderRateLimitedError("quota")))
    client.get("/flights/", params=PARAMS)
    metrics = client.get("/metrics").text
    assert 'provider_errors_total{provider="stub",reason="rate_limited"}' in metrics


def test_without_api_key_the_real_provider_answers_503(client):
    # No override: the real get_provider(), and conftest removed AMADEUS_API_KEY.
    from shared.providers import get_provider

    get_provider.cache_clear()
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 503
    assert response.json() == {"error": "provider_not_configured"}
