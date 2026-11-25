"""Bookings API router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import BookingCreate, BookingORM, BookingResponse
from app.utils.metrics import bookings_created
from shared.cache import get_json
from shared.schemas import FlightOffer
from shared.utils.logging import log

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_booking(payload: dict, db: Session = Depends(get_db)):
    """Register a booking against a previously returned offer.

    Frozen-intent booking: the offer is not re-confirmed against the provider
    here (the real purchase happens on the airline's site, through the offer's
    deep_link, and we don't own seat inventory). We only require that the
    offer is still in the offer:{offer_id} cache written by GET /flights. A
    miss there means the offer is gone from cache, which we treat as expired.
    """
    try:
        booking_in = BookingCreate(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_passenger_data"},
        ) from exc

    raw_offer = get_json(f"offer:{booking_in.offer_id}")
    try:
        offer = FlightOffer.model_validate(raw_offer) if raw_offer is not None else None
    except ValidationError:
        # An entry cached by an older release in another shape: treat as expired.
        offer = None
    if offer is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "offer_expired"},
        )

    booking = BookingORM(
        offer_id=booking_in.offer_id,
        offer_snapshot=raw_offer,
        passenger_name=f"{booking_in.passenger.first_name} {booking_in.passenger.last_name}",
        contact_email=booking_in.contact_email,
        price_amount=offer.price,
        price_currency=offer.currency,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    bookings_created.inc()
    log.info("Booking created id=%s offer_id=%s", booking.id, booking.offer_id)

    return {
        "booking_id": str(booking.id),
        "status": booking.status,
        "snapshot": offer,
    }


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: str, db: Session = Depends(get_db)):
    """Return a single booking by ID or 404."""
    try:
        parsed_id = uuid.UUID(booking_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "booking_not_found"},
        ) from exc

    booking = db.query(BookingORM).filter(BookingORM.id == parsed_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "booking_not_found"},
        )
    return booking
