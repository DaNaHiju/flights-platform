"""SQLAlchemy ORM models and Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field
from sqlalchemy import JSON, CHAR, Column, DateTime, Numeric, Text, Uuid, func

from app.database import Base

# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class BookingORM(Base):
    """SQLAlchemy model for the bookings table.

    offer_snapshot stores the complete, untrimmed fli response for the
    booked offer — not the trimmed FlightOffer shape (shared/schemas.py).
    See docs/api-contract.md section 4.
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
