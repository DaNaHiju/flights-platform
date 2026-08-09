"""SQLAlchemy ORM models and Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List

from pydantic import BaseModel, Field
from sqlalchemy import JSON, CHAR, Column, DateTime, Numeric, Text, Uuid, func

from app.database import Base

# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class BookingORM(Base):
    """SQLAlchemy model for the bookings table.

    offer_snapshot stores the complete, untrimmed fli response for the
    booked offer — not the trimmed FlightOffer shape below. See
    docs/api-contract.md section 4.
    """

    __tablename__ = "bookings"

    # Uuid/JSON (not the Postgres-only UUID/JSONB dialect types) so the
    # ORM also works against the in-memory SQLite used by the test suite.
    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    offer_id = Column(Text, nullable=False)
    offer_snapshot = Column(JSON, nullable=False)
    passenger_name = Column(Text, nullable=False)
    contact_email = Column(Text, nullable=False)
    price_amount = Column(Numeric(10, 2), nullable=False)
    price_currency = Column(CHAR(3), nullable=False)
    status = Column(Text, nullable=False, default="confirmed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Pydantic schemas — flights
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Pydantic schemas — bookings
# ---------------------------------------------------------------------------


class PassengerIn(BaseModel):
    """Passenger details submitted with a booking."""

    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    date_of_birth: date


class BookingCreate(BaseModel):
    """Payload to register a booking against a previously returned offer."""

    offer_id: str
    passenger: PassengerIn
    contact_email: str = Field(..., min_length=5)


class BookingResponse(BaseModel):
    """Booking representation returned by the API."""

    id: uuid.UUID
    offer_id: str
    offer_snapshot: dict
    passenger_name: str
    contact_email: str
    price_amount: float
    price_currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
