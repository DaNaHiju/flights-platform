"""Tests for the flights search API. fli itself is mocked — these don't hit Google."""

from fastapi.testclient import TestClient

from shared.providers import ProviderUnavailableError

RAW_OFFER = {
    "legs": [
        {
            "airline": "Air Europa",
            "flight_number": "1302",
            "departure_airport": "Ben Gurion International Airport",
            "arrival_airport": "Madrid Barajas International Airport",
            "departure_datetime": "2099-01-01T16:05:00",
            "arrival_datetime": "2099-01-01T20:20:00",
            "duration": 315,
        }
    ],
    "price": 1839.0,
    "currency": "USD",
    "duration": 315,
    "stops": 0,
    "primary_airline": "Air Europa",
    "primary_airline_name": "Air Europa",
    "booking_token": "TOKEN123",
}


def _valid_iata(code):
    return code in {"TLV", "MAD", "JFK"}


def test_search_flights_invalid_iata(client: TestClient):
    response = client.get(
        "/flights/",
        params={"origin": "AB1", "destination": "JFK", "date": "2099-01-01"},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_iata_code"}


def test_search_flights_invalid_date_format(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)
    response = client.get(
        "/flights/",
        params={"origin": "TLV", "destination": "MAD", "date": "not-a-date"},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_date_format"}


def test_search_flights_date_in_past(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)
    response = client.get(
        "/flights/",
        params={"origin": "TLV", "destination": "MAD", "date": "2000-01-01"},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "date_in_past"}


def test_search_flights_success(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)
    monkeypatch.setattr("app.api.flights.search_one_way", lambda *a, **k: [RAW_OFFER])

    response = client.get(
        "/flights/",
        params={"origin": "TLV", "destination": "MAD", "date": "2099-01-01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cached"] is False
    assert data["cached_at"] is None
    assert len(data["results"]) == 1

    offer = data["results"][0]
    assert offer["offer_id"] == "TOKEN123"
    assert offer["price"] == 1839.0
    assert offer["primary_airline"] == "Air Europa"
    assert offer["legs"][0]["flight_number"] == "1302"
    # amenities / co2 / aircraft / layovers must not leak into the public response
    assert "amenities" not in offer["legs"][0]
    assert "co2_emissions_g" not in offer


def test_search_flights_cache_hit(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)
    calls = {"n": 0}

    def fake_search(*args, **kwargs):
        calls["n"] += 1
        return [RAW_OFFER]

    monkeypatch.setattr("app.api.flights.search_one_way", fake_search)

    params = {"origin": "TLV", "destination": "MAD", "date": "2099-01-01"}
    first = client.get("/flights/", params=params)
    second = client.get("/flights/", params=params)

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["cached_at"] is not None
    assert calls["n"] == 1


def test_search_flights_provider_unavailable(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)

    def raise_error(*args, **kwargs):
        raise ProviderUnavailableError("boom")

    monkeypatch.setattr("app.api.flights.search_one_way", raise_error)

    response = client.get(
        "/flights/",
        params={"origin": "TLV", "destination": "MAD", "date": "2099-01-01"},
    )
    assert response.status_code == 502
    assert response.json() == {"error": "provider_unavailable"}
