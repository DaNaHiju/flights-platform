"""Pydantic schemas for flight offers, shared by the API and the worker."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from shared.airports import airport_name, city_and_country, iata_from_airport


class Leg(BaseModel):
    """A single flight leg inside a FlightOffer."""

    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_datetime: str
    arrival_datetime: str
    duration_minutes: int
    # Added fields (None when the airport is not in airportsdata); old
    # consumers ignore them.
    departure_airport_code: Optional[str] = None
    arrival_airport_code: Optional[str] = None
    departure_city: Optional[str] = None
    arrival_city: Optional[str] = None
    departure_country_code: Optional[str] = None
    arrival_country_code: Optional[str] = None


class FlightOffer(BaseModel):
    """Public flight offer shape.

    This is a subset of fli's raw response. amenities, legroom,
    co2_emissions, aircraft, and layovers are deliberately excluded —
    they're Google Flights' own presentation detail and add noise to the
    booking use case, which only needs price, schedule, and airline
    identity. See docs/api-contract.md section 3.
    """

    offer_id: str
    price: float
    currency: str
    duration_minutes: int
    # Same value as duration_minutes, named for what it is: the whole itinerary.
    total_duration_minutes: int
    stops: int
    primary_airline: str
    legs: List[Leg]


class Deal(BaseModel):
    """A single top-deal entry, computed from FLIGHTS_DEFAULT_ORIGIN."""

    destination: str
    departure_date: str
    price: float
    currency: str
    airline: str
    # Added fields. Deals cached before they existed lack them; readers must tolerate that.
    origin: Optional[str] = None
    origin_airport_name: Optional[str] = None
    origin_city: Optional[str] = None
    origin_country_code: Optional[str] = None
    destination_airport_name: Optional[str] = None
    destination_city: Optional[str] = None
    destination_country_code: Optional[str] = None
    total_duration_minutes: Optional[int] = None


def deal_airport_fields(origin: str, destination: str) -> dict:
    """The location fields of a Deal for a route, from the shared enrichment."""
    o_city, o_country = city_and_country(origin)
    d_city, d_country = city_and_country(destination)
    return {
        "origin": origin,
        "origin_airport_name": airport_name(origin),
        "origin_city": o_city,
        "origin_country_code": o_country,
        "destination_airport_name": airport_name(destination),
        "destination_city": d_city,
        "destination_country_code": d_country,
    }


def _leg_from_raw(leg: dict) -> Leg:
    dep = iata_from_airport(leg["departure_airport"])
    arr = iata_from_airport(leg["arrival_airport"])
    dep_city, dep_country = city_and_country(dep)
    arr_city, arr_country = city_and_country(arr)
    return Leg(
        airline=leg["airline"],
        flight_number=leg["flight_number"],
        departure_airport=leg["departure_airport"],
        arrival_airport=leg["arrival_airport"],
        departure_datetime=leg["departure_datetime"],
        arrival_datetime=leg["arrival_datetime"],
        duration_minutes=leg["duration"],
        departure_airport_code=dep,
        arrival_airport_code=arr,
        departure_city=dep_city,
        arrival_city=arr_city,
        departure_country_code=dep_country,
        arrival_country_code=arr_country,
    )


def flight_offer_from_raw(raw: dict) -> FlightOffer:
    """Trim a raw fli FlightResult dict down to the public FlightOffer shape."""
    primary_airline = (
        raw.get("primary_airline_name") or raw.get("primary_airline") or ""
    )
    return FlightOffer(
        offer_id=raw["booking_token"],
        price=raw["price"],
        currency=raw["currency"],
        duration_minutes=raw["duration"],
        total_duration_minutes=raw["duration"],
        stops=raw["stops"],
        primary_airline=primary_airline,
        legs=[_leg_from_raw(leg) for leg in raw["legs"]],
    )
