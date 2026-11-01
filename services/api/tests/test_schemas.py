"""Airport enrichment and duration fields of the public schemas. No network."""

from fastapi.testclient import TestClient

from fli.models import Airport

from shared.schemas import flight_offer_from_raw
from tests.test_flights import RAW_OFFER


def _raw(dep: str, arr: str, legs: int = 1) -> dict:
    leg = dict(RAW_OFFER["legs"][0], departure_airport=dep, arrival_airport=arr)
    return dict(RAW_OFFER, legs=[leg] * legs)


def test_leg_has_code_city_and_country():
    leg = flight_offer_from_raw(RAW_OFFER).legs[0]
    assert leg.departure_airport_code == "TLV"
    assert leg.arrival_airport_code == "MAD"
    assert (leg.departure_city, leg.departure_country_code) == ("Tel Aviv", "IL")
    assert (leg.arrival_city, leg.arrival_country_code) == ("Madrid", "ES")
    # Existing fields are untouched.
    assert leg.departure_airport == "Ben Gurion International Airport"


def test_code_not_in_airportsdata_gives_null_city_and_country():
    # PBI exists in fli but not in airportsdata.
    offer = flight_offer_from_raw(_raw(Airport.PBI.value, Airport.TLV.value))
    leg = offer.legs[0]
    assert leg.departure_airport_code == "PBI"
    assert leg.departure_city is None
    assert leg.departure_country_code is None
    assert leg.arrival_city == "Tel Aviv"


def test_unknown_airport_name_gives_null_code():
    leg = flight_offer_from_raw(_raw("Nowhere Field", "Nowhere Field")).legs[0]
    assert leg.departure_airport_code is None
    assert leg.departure_city is None


def test_total_duration_and_leg_duration():
    offer = flight_offer_from_raw(RAW_OFFER)
    assert offer.total_duration_minutes == 315 == offer.duration_minutes
    assert offer.legs[0].duration_minutes == 315


def test_old_cached_offer_without_new_fields_still_parses():
    # A raw offer cached before this change has exactly the old keys.
    assert "departure_airport_code" not in RAW_OFFER["legs"][0]
    assert flight_offer_from_raw(RAW_OFFER).legs[0].arrival_airport_code == "MAD"


def test_response_keeps_every_old_field_and_adds_new_ones(
    client: TestClient, monkeypatch, fake_redis
):
    monkeypatch.setattr("app.api.flights.is_valid_iata", lambda c: True)
    monkeypatch.setattr(
        "app.api.flights.search_one_way", lambda *a, **k: [RAW_OFFER]
    )
    body = client.get(
        "/flights/", params={"origin": "TLV", "destination": "MAD", "date": "2099-01-01"}
    ).json()
    offer = body["results"][0]
    for key in ("offer_id", "price", "currency", "duration_minutes", "stops",
                "primary_airline", "legs"):
        assert key in offer
    assert offer["total_duration_minutes"] == 315
    assert offer["legs"][0]["arrival_city"] == "Madrid"
    for key in ("airline", "flight_number", "departure_airport", "arrival_airport",
                "departure_datetime", "arrival_datetime", "duration_minutes"):
        assert key in offer["legs"][0]


def test_round_trip_both_legs_have_duration_and_airports(
    client: TestClient, monkeypatch, fake_redis
):
    monkeypatch.setattr("app.api.flights.is_valid_iata", lambda c: True)
    back = _raw("Madrid Barajas International Airport", "Ben Gurion International Airport")
    pair = {"price": 900.0, "currency": "USD", "outbound": RAW_OFFER, "return": back}
    monkeypatch.setattr("app.api.flights.search_round_trip", lambda *a, **k: [pair])
    body = client.get(
        "/flights/",
        params={"origin": "TLV", "destination": "MAD", "date": "2099-01-01",
                "return_date": "2099-01-10"},
    ).json()
    result = body["results"][0]
    assert result["outbound"]["total_duration_minutes"] == 315
    assert result["return"]["total_duration_minutes"] == 315
    assert result["return"]["legs"][0]["departure_airport_code"] == "MAD"
