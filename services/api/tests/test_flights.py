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


def test_round_trip_has_its_own_cache_key(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)
    calls = {"one_way": 0, "round_trip": 0}

    def fake_one_way(*args, **kwargs):
        calls["one_way"] += 1
        return [RAW_OFFER]

    def fake_round_trip(*args, **kwargs):
        calls["round_trip"] += 1
        return [
            {
                "price": 2000.0,
                "currency": "USD",
                "outbound": RAW_OFFER,
                "return": RAW_OFFER,
            }
        ]

    monkeypatch.setattr("app.api.flights.search_one_way", fake_one_way)
    monkeypatch.setattr("app.api.flights.search_round_trip", fake_round_trip)

    one_way = {"origin": "TLV", "destination": "MAD", "date": "2099-01-01"}
    round_trip = {**one_way, "return_date": "2099-01-08"}
    other_return = {**one_way, "return_date": "2099-01-09"}

    client.get("/flights/", params=one_way)
    rt_first = client.get("/flights/", params=round_trip)
    rt_second = client.get("/flights/", params=round_trip)
    client.get("/flights/", params=other_return)
    one_way_again = client.get("/flights/", params=one_way)

    # The round trip did not read the one-way entry, and vice versa.
    assert calls == {"one_way": 1, "round_trip": 2}
    assert rt_first.json()["cached"] is False
    assert rt_second.json()["cached"] is True
    assert rt_second.json()["results"][0]["price"] == 2000.0
    # One-way keeps its old key and its old response shape.
    assert one_way_again.json()["cached"] is True
    assert one_way_again.json()["results"][0]["offer_id"] == "TOKEN123"


def test_one_way_cache_key_is_unchanged():
    from app.api.flights import _search_cache_key

    assert _search_cache_key("TLV", "MAD", "2099-01-01", 1) == "search:TLV:MAD:2099-01-01:1"
    assert (
        _search_cache_key("TLV", "MAD", "2099-01-01", 1, "2099-01-08")
        != _search_cache_key("TLV", "MAD", "2099-01-01", 1)
    )


def test_return_date_before_departure(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)
    response = client.get(
        "/flights/",
        params={
            "origin": "TLV",
            "destination": "MAD",
            "date": "2099-01-08",
            "return_date": "2099-01-01",
        },
    )
    assert response.status_code == 400
    assert response.json() == {"error": "return_before_departure"}


def test_return_date_invalid_format(client: TestClient, monkeypatch):
    monkeypatch.setattr("app.api.flights.is_valid_iata", _valid_iata)
    response = client.get(
        "/flights/",
        params={
            "origin": "TLV",
            "destination": "MAD",
            "date": "2099-01-01",
            "return_date": "nope",
        },
    )
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_date_format"}
