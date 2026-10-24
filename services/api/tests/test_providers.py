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
