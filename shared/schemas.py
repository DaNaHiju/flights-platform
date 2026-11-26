"""Provider-neutral schemas shared by the API and the worker.

Every FlightProvider returns these models, whatever its own wire format. That
is what makes the provider swappable: the API, the cache, the bookings table
and the frontend only ever see the shapes defined here.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from shared.airports import airport_name, city_and_country


class Leg(BaseModel):
    """A single flight (segment) inside a FlightOffer."""

    # Resolved airline name (e.g. "British Airways"); the code is kept alongside.
    airline: str
    airline_code: Optional[str] = None
    # Marketing carrier code + number, e.g. "BA322".
    flight_number: str
    # Name of the airline that actually flies it, when it differs (codeshare).
    operating_airline: Optional[str] = None
    departure_airport: str
    arrival_airport: str
    # Local time at each airport WITH its UTC offset, exactly as the provider
    # sent it. Never convert these to the viewer's timezone.
    departure_datetime: str
    arrival_datetime: str
    duration_minutes: int
    departure_airport_code: Optional[str] = None
    arrival_airport_code: Optional[str] = None
    departure_city: Optional[str] = None
    arrival_city: Optional[str] = None
    departure_country_code: Optional[str] = None
    arrival_country_code: Optional[str] = None


class FlightOffer(BaseModel):
    """One priced itinerary in one direction (one bound)."""

    # Stable id built from the itinerary; POST /bookings looks the offer up by it.
    offer_id: str
    price: float
    currency: str
    duration_minutes: int
    # Same value as duration_minutes, named for what it is: the whole itinerary,
    # first departure to last arrival, including layovers.
    total_duration_minutes: int
    stops: int
    primary_airline: str
    primary_airline_code: Optional[str] = None
    # Every distinct airline name on the itinerary, in flight order.
    carriers: List[str] = Field(default_factory=list)
    # Airline that sells the offer (its IATA code).
    merchant: Optional[str] = None
    # Redirects to the airline's own booking page. Optional: some offers have none.
    deep_link: Optional[str] = None
    legs: List[Leg]


class RoundTripOffer(BaseModel):
    """An outbound + return pair, sold and priced together."""

    model_config = ConfigDict(populate_by_name=True)

    price: float
    currency: str
    merchant: Optional[str] = None
    deep_link: Optional[str] = None
    outbound: FlightOffer
    # "return" is a Python keyword, so the attribute is return_ and the JSON key
    # stays "return" (dump with by_alias=True).
    return_: FlightOffer = Field(alias="return")


class Location(BaseModel):
    """An airport or a city, as offered by the origin/destination typeahead."""

    id: str
    iata_code: str
    sub_type: str  # "AIRPORT" or "CITY"
    name: str
    detailed_name: Optional[str] = None
    city_name: Optional[str] = None
    city_code: Optional[str] = None
    country_name: Optional[str] = None
    country_code: Optional[str] = None
    # The value to send as origin/destination: "LHR+" pins one airport,
    # "LON" covers every airport of the city.
    search_code: str


class Deal(BaseModel):
    """A single top-deal entry, computed from FLIGHTS_DEFAULT_ORIGIN."""

    destination: str
    departure_date: str
    # Set when the deal is a round trip; None for a one-way deal. Deals cached
    # before round-trip deals existed have no such key and still validate.
    return_date: Optional[str] = None
    # For a round trip, the total of the cheapest outbound + return pair.
    price: float
    currency: str
    airline: str
    origin: Optional[str] = None
    origin_airport_name: Optional[str] = None
    origin_city: Optional[str] = None
    origin_country_code: Optional[str] = None
    destination_airport_name: Optional[str] = None
    destination_city: Optional[str] = None
    destination_country_code: Optional[str] = None
    total_duration_minutes: Optional[int] = None


def airport_fields(prefix: str, code: str | None) -> dict:
    """Code, airport name, city and country of an airport, keyed with *prefix*."""
    city, country = city_and_country(code)
    return {
        f"{prefix}_airport_code": code,
        f"{prefix}_city": city,
        f"{prefix}_country_code": country,
    }


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
