"""Airport enrichment and the public schema shapes. No network."""

from shared.airports import airport_name, city_and_country
from shared.schemas import FlightOffer, RoundTripOffer, deal_airport_fields
from tests.test_flights import make_offer


def test_airport_name_city_and_country_come_from_airportsdata():
    assert airport_name("MAD")
    assert city_and_country("TLV") == ("Tel Aviv", "IL")


def test_unknown_airport_resolves_to_none():
    assert airport_name("ZZZ") is None
    assert city_and_country("ZZZ") == (None, None)
    assert airport_name(None) is None


def test_deal_airport_fields():
    fields = deal_airport_fields("TLV", "FCO")
    assert fields["origin"] == "TLV"
    assert (fields["destination_city"], fields["destination_country_code"]) == ("Rome", "IT")


def test_flight_offer_round_trips_through_json():
    # What the cache stores is exactly what bookings reads back.
    offer = make_offer()
    assert FlightOffer.model_validate(offer.model_dump(mode="json")) == offer


def test_round_trip_offer_serializes_return_key():
    pair = RoundTripOffer(price=1.0, currency="USD", outbound=make_offer(), return_=make_offer())
    dumped = pair.model_dump(by_alias=True)
    assert "return" in dumped and "return_" not in dumped
    assert RoundTripOffer.model_validate(dumped) == pair
