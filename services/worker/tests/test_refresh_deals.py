"""Tests for the deals refresh job. fli is always mocked — no network calls."""

import json
import os

import pytest

from shared.providers import ProviderUnavailableError
from worker import refresh_deals as job
from worker.config import settings


def _offer(price: float, airline: str = "El Al") -> dict:
    """Return the subset of a raw fli result that refresh_deals reads."""
    return {"price": price, "currency": "USD", "primary_airline_name": airline}


@pytest.fixture
def fake_search(monkeypatch):
    """Replace search_one_way; *results* maps destination -> offers or exception."""
    results: dict = {}

    def search_one_way(origin, destination, date, adults, currency):
        outcome = results.get(destination, [])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(job, "search_one_way", search_one_way)
    return results


def _cached(fake_redis) -> dict:
    return json.loads(fake_redis.store[job.DEALS_CACHE_KEY])


def test_caches_cheapest_offer_per_destination_sorted_by_price(fake_search, fake_redis):
    fake_search["MAD"] = [_offer(300), _offer(250, "Iberia")]
    fake_search["JFK"] = [_offer(180, "United")]

    assert job.refresh_deals() == 2

    deals = _cached(fake_redis)["deals"]
    assert [d["destination"] for d in deals] == ["JFK", "MAD"]
    assert deals[1]["price"] == 250
    assert deals[1]["airline"] == "Iberia"
    assert fake_redis.ttls[job.DEALS_CACHE_KEY] == settings.DEALS_CACHE_TTL


def test_provider_error_skips_only_that_destination(fake_search, fake_redis):
    fake_search["MAD"] = ProviderUnavailableError("google changed shape")
    fake_search["LHR"] = [_offer(120)]

    assert job.refresh_deals() == 1
    assert [d["destination"] for d in _cached(fake_redis)["deals"]] == ["LHR"]


def test_no_offers_still_writes_empty_deal_list(fake_search, fake_redis):
    assert job.refresh_deals() == 0

    cached = _cached(fake_redis)
    assert cached["deals"] == []
    assert "refreshed_at" in cached


def test_worker_runs_without_database_url():
    assert "DATABASE_URL" not in os.environ
    assert not hasattr(settings, "DATABASE_URL")
