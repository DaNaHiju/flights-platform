"""Tests for the deals refresh job. fli is always mocked — no network calls."""

import importlib
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


def test_zero_deals_keeps_previous_cache(fake_search, fake_redis):
    previous = json.dumps(
        {"refreshed_at": "earlier", "deals": [{"destination": "MAD"}]}
    )
    fake_redis.store[job.DEALS_CACHE_KEY] = previous
    fake_redis.ttls[job.DEALS_CACHE_KEY] = 111

    assert job.refresh_deals() == 0

    assert fake_redis.store[job.DEALS_CACHE_KEY] == previous
    assert fake_redis.ttls[job.DEALS_CACHE_KEY] == 111


def test_zero_deals_logs_warning(fake_search, caplog):
    fake_search["MAD"] = ProviderUnavailableError("fli returned no payload (None)")

    with caplog.at_level("WARNING", logger=job.log.name):
        assert job.refresh_deals() == 0

    assert any(
        r.levelname == "WARNING" and "keeping previous" in r.getMessage()
        for r in caplog.records
    )


def test_worker_runs_without_database_url():
    assert "DATABASE_URL" not in os.environ
    assert not hasattr(settings, "DATABASE_URL")


def test_cache_ttl_used_comes_from_settings(fake_search, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "DEALS_CACHE_TTL", 1234)
    fake_search["MAD"] = [_offer(100)]

    job.refresh_deals()

    assert fake_redis.ttls[job.DEALS_CACHE_KEY] == 1234


def test_default_cache_ttl_outlasts_the_six_hour_cronjob(monkeypatch):
    from worker import config

    monkeypatch.delenv("DEALS_CACHE_TTL", raising=False)
    try:
        assert importlib.reload(config).settings.DEALS_CACHE_TTL > 6 * 3600
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_cache_ttl_is_read_from_env(monkeypatch):
    from worker import config

    monkeypatch.setenv("DEALS_CACHE_TTL", "999")
    try:
        assert importlib.reload(config).settings.DEALS_CACHE_TTL == 999
    finally:
        monkeypatch.undo()
        importlib.reload(config)
