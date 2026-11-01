"""Tests for shared.providers and its effect on GET /flights. fli is mocked — no Google calls."""

import pytest
from fastapi.testclient import TestClient

from shared import providers
from shared.providers import ProviderUnavailableError
from tests.test_flights import RAW_OFFER

PARAMS = {"origin": "TLV", "destination": "MAD", "date": "2099-01-01"}


class FakeResult:
    """Stands in for a fli FlightResult: only what search_one_way reads."""

    def __init__(self, price):
        self.price = price

    def model_dump(self, mode):
        return {**RAW_OFFER, "price": self.price}


def _mock_fli(monkeypatch, results):
    """Make SearchFlights().search(...) return *results* (the fli return value)."""

    class FakeSearchFlights:
        def search(self, filters, currency):
            return results

    monkeypatch.setattr(providers, "SearchFlights", FakeSearchFlights)


def test_none_from_fli_raises_provider_unavailable(monkeypatch):
    _mock_fli(monkeypatch, None)
    with pytest.raises(ProviderUnavailableError):
        providers.search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")


def test_empty_list_from_fli_is_an_empty_result(monkeypatch):
    _mock_fli(monkeypatch, [])
    assert providers.search_one_way("TLV", "MAD", "2099-01-01", 1, "USD") == []


def test_results_from_fli_are_returned_as_dicts(monkeypatch):
    _mock_fli(monkeypatch, [FakeResult(100.0), FakeResult(None)])
    offers = providers.search_one_way("TLV", "MAD", "2099-01-01", 1, "USD")
    assert [o["price"] for o in offers] == [100.0]


def test_api_returns_502_when_fli_returns_none(client: TestClient, monkeypatch):
    _mock_fli(monkeypatch, None)
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 502
    assert response.json() == {"error": "provider_unavailable"}


def test_api_returns_200_empty_when_fli_returns_empty_list(
    client: TestClient, monkeypatch
):
    _mock_fli(monkeypatch, [])
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 200
    assert response.json() == {"results": [], "cached": False, "cached_at": None}


def test_api_returns_200_with_data_when_fli_returns_offers(
    client: TestClient, monkeypatch
):
    _mock_fli(monkeypatch, [FakeResult(100.0)])
    response = client.get("/flights/", params=PARAMS)
    assert response.status_code == 200
    assert response.json()["results"][0]["price"] == 100.0


# --- round trip ---------------------------------------------------------------

RT_PARAMS = {**PARAMS, "return_date": "2099-01-08"}


class FakeRTResult(FakeResult):
    """A fli FlightResult inside a (outbound, return) tuple."""

    currency = "USD"


def _mock_fli_round_trip(monkeypatch, results):
    """Like _mock_fli, but records the kwargs fli's search() was called with."""
    seen = {}

    class FakeSearchFlights:
        def search(self, filters, top_n, currency):
            seen.update(top_n=top_n, trip_type=filters.trip_type, filters=filters)
            return results

    monkeypatch.setattr(providers, "SearchFlights", FakeSearchFlights)
    return seen


def test_round_trip_none_from_fli_raises_provider_unavailable(monkeypatch):
    _mock_fli_round_trip(monkeypatch, None)
    with pytest.raises(ProviderUnavailableError):
        providers.search_round_trip("TLV", "MAD", "2099-01-01", "2099-01-08", 1, "USD")


def test_round_trip_limits_outbounds_and_uses_both_segments(monkeypatch):
    seen = _mock_fli_round_trip(monkeypatch, [])
    providers.search_round_trip("TLV", "MAD", "2099-01-01", "2099-01-08", 1, "USD")

    assert seen["top_n"] == 3  # 1 + 3 requests to Google
    assert seen["trip_type"].name == "ROUND_TRIP"
    out, back = seen["filters"].flight_segments
    assert (out.travel_date, back.travel_date) == ("2099-01-01", "2099-01-08")
    # the return segment flies the opposite way
    assert out.departure_airport == back.arrival_airport
    assert out.arrival_airport == back.departure_airport


def test_round_trip_price_is_the_return_price_cheapest_first(monkeypatch):
    # The outbound carries the same "from" price for every return.
    pairs = [
        (FakeRTResult(144.0), FakeRTResult(222.0)),
        (FakeRTResult(144.0), FakeRTResult(166.0)),
        (FakeRTResult(144.0), FakeRTResult(None)),  # no price: dropped
    ]
    _mock_fli_round_trip(monkeypatch, pairs)
    offers = providers.search_round_trip(
        "TLV", "MAD", "2099-01-01", "2099-01-08", 1, "USD"
    )
    assert [o["price"] for o in offers] == [166.0, 222.0]
    assert set(offers[0]) == {"price", "currency", "outbound", "return"}


def test_api_round_trip_returns_502_when_fli_returns_none(
    client: TestClient, monkeypatch
):
    _mock_fli_round_trip(monkeypatch, None)
    response = client.get("/flights/", params=RT_PARAMS)
    assert response.status_code == 502
    assert response.json() == {"error": "provider_unavailable"}


def test_api_round_trip_response_shape(client: TestClient, monkeypatch):
    _mock_fli_round_trip(monkeypatch, [(FakeRTResult(144.0), FakeRTResult(166.0))])
    response = client.get("/flights/", params=RT_PARAMS)
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["price"] == 166.0
    assert result["outbound"]["offer_id"] == "TOKEN123"
    assert result["return"]["legs"][0]["flight_number"] == "1302"
