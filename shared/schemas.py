"""Pydantic schemas for flight offers, shared by the API and the worker."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class Leg(BaseModel):
    """A single flight leg inside a FlightOffer."""

    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_datetime: str
    arrival_datetime: str
    duration_minutes: int


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
        stops=raw["stops"],
        primary_airline=primary_airline,
        legs=[
            Leg(
                airline=leg["airline"],
                flight_number=leg["flight_number"],
                departure_airport=leg["departure_airport"],
                arrival_airport=leg["arrival_airport"],
                departure_datetime=leg["departure_datetime"],
                arrival_datetime=leg["arrival_datetime"],
                duration_minutes=leg["duration"],
            )
            for leg in raw["legs"]
        ],
    )
