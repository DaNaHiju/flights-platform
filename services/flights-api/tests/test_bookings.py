"""Tests for the bookings API."""

from fastapi.testclient import TestClient

from app.cache import set_json

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

VALID_PAYLOAD = {
    "offer_id": "TOKEN123",
    "passenger": {
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": "1990-01-01",
    },
    "contact_email": "jane@example.com",
}


def _seed_offer():
    set_json("offer:TOKEN123", RAW_OFFER, ttl=600)


def test_create_booking_success(client: TestClient):
    _seed_offer()
    response = client.post("/bookings/", json=VALID_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "confirmed"
    assert "booking_id" in data
    assert data["snapshot"]["offer_id"] == "TOKEN123"
    assert data["snapshot"]["price"] == 1839.0


def test_create_booking_offer_expired(client: TestClient):
    """No matching offer:{token} in cache — treated as an expired offer."""
    response = client.post("/bookings/", json={**VALID_PAYLOAD, "offer_id": "MISSING"})
    assert response.status_code == 409
    assert response.json() == {"error": "offer_expired"}


def test_create_booking_invalid_passenger_data(client: TestClient):
    _seed_offer()
    payload = {
        **VALID_PAYLOAD,
        "passenger": {
            "first_name": "",
            "last_name": "Doe",
            "date_of_birth": "1990-01-01",
        },
    }
    response = client.post("/bookings/", json=payload)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_passenger_data"}


def test_get_booking_by_id(client: TestClient):
    _seed_offer()
    created = client.post("/bookings/", json=VALID_PAYLOAD).json()

    response = client.get(f"/bookings/{created['booking_id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["booking_id"]
    assert response.json()["contact_email"] == "jane@example.com"


def test_get_booking_not_found(client: TestClient):
    response = client.get("/bookings/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json() == {"error": "booking_not_found"}
