"""Tests for the bookings API."""

from fastapi.testclient import TestClient

from shared.cache import set_json
from tests.test_flights import make_offer

RAW_OFFER = make_offer("TOKEN123", price=1839.0).model_dump(mode="json")

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
    assert data["status"] == "recorded"
    assert "booking_id" in data
    assert data["snapshot"]["offer_id"] == "TOKEN123"
    assert data["snapshot"]["price"] == 1839.0


def test_create_booking_offer_expired(client: TestClient):
    """No matching offer:{token} in cache — treated as an expired offer."""
    response = client.post("/bookings/", json={**VALID_PAYLOAD, "offer_id": "MISSING"})
    assert response.status_code == 409
    assert response.json() == {"error": "offer_expired"}


def test_offer_cached_in_an_old_shape_is_treated_as_expired(client: TestClient):
    # An entry written by the previous (fli-based) release under the same key.
    set_json("offer:TOKEN123", {"booking_token": "TOKEN123", "price": 1.0}, ttl=600)
    response = client.post("/bookings/", json=VALID_PAYLOAD)
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
