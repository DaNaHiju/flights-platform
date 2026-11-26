"""Tests for GET /deals: served from Redis only, one-way and round-trip deals alike."""

import json

from fastapi.testclient import TestClient

DEALS_KEY = "deals:top"

ROUND_TRIP_DEAL = {
    "destination": "MAD",
    "departure_date": "2099-01-12",
    "return_date": "2099-01-19",
    "price": 640.0,
    "currency": "ILS",
    "airline": "Iberia",
}
# What the worker wrote before round-trip deals existed: no return_date key.
ONE_WAY_DEAL = {
    "destination": "ATH",
    "departure_date": "2099-01-12",
    "price": 190.0,
    "currency": "ILS",
    "airline": "Aegean Airlines",
}


def store(fake_redis, deals):
    fake_redis.store[DEALS_KEY] = json.dumps(
        {"refreshed_at": "2099-01-01T00:00:00+00:00", "deals": deals}
    )


def test_round_trip_deal_is_served_with_its_return_date(client: TestClient, fake_redis):
    store(fake_redis, [ROUND_TRIP_DEAL])

    body = client.get("/deals").json()

    assert body["deals"] == [ROUND_TRIP_DEAL]
    assert body["deals"][0]["return_date"] == "2099-01-19"


def test_one_way_deals_cached_before_the_change_are_still_served(client: TestClient, fake_redis):
    # Same key, mixed content: a deal without return_date must not break the endpoint.
    store(fake_redis, [ONE_WAY_DEAL, ROUND_TRIP_DEAL])

    response = client.get("/deals")

    assert response.status_code == 200
    deals = response.json()["deals"]
    assert "return_date" not in deals[0]
    assert deals[1]["return_date"] == "2099-01-19"


def test_limit_applies_to_round_trip_deals(client: TestClient, fake_redis):
    store(fake_redis, [ROUND_TRIP_DEAL, {**ROUND_TRIP_DEAL, "destination": "ROM"}])
    assert len(client.get("/deals?limit=1").json()["deals"]) == 1


def test_empty_cache_is_503(client: TestClient):
    response = client.get("/deals")
    assert response.status_code == 503
    assert response.json() == {"error": "deals_not_available"}
