"""Tests for the deals refresh job. The provider is always a stub — no network calls."""

import importlib
import json
import os

import pytest

from shared.providers import ProviderNotConfiguredError, ProviderUnavailableError
from shared.schemas import FlightOffer
from worker import refresh_deals as job
from worker.config import settings


def _offer(price: float, airline: str = "El Al", duration: int = 315) -> FlightOffer:
    """A provider-neutral offer; refresh_deals reads price, airline and duration."""
    return FlightOffer(
        offer_id=f"{airline}-{price}",
        price=price,
        currency="USD",
        duration_minutes=duration,
        total_duration_minutes=duration,
        stops=0,
        primary_airline=airline,
        deep_link="https://example.test/book",
        legs=[],
    )


class StubProvider:
    name = "stub"

    def __init__(self, results: dict):
        self.results = results
        self.calls = 0

    def search_one_way(self, origin, destination, date, adults, currency):
        self.calls += 1
        outcome = self.results.get(destination, [])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def fake_search(monkeypatch):
    """Stub the provider; *results* maps destination -> offers or exception."""
    results: dict = {}
    monkeypatch.setattr(job, "get_provider", lambda: StubProvider(results))
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
    fake_search["MAD"] = ProviderUnavailableError("gateway timeout")
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
    fake_search["MAD"] = ProviderUnavailableError("gateway timeout")

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


def test_deals_carry_airport_and_duration_fields(fake_search, fake_redis):
    fake_search["MAD"] = [_offer(250, duration=315)]

    job.refresh_deals()

    deal = _cached(fake_redis)["deals"][0]
    assert deal["origin"] == settings.FLIGHTS_DEFAULT_ORIGIN
    assert (deal["destination_city"], deal["destination_country_code"]) == ("Madrid", "ES")
    assert deal["destination_airport_name"]
    assert deal["total_duration_minutes"] == 315
    # Existing fields are still there.
    assert {"destination", "departure_date", "price", "currency", "airline"} <= deal.keys()


def test_deal_for_airport_missing_in_airportsdata_has_null_city(
    fake_search, fake_redis, monkeypatch
):
    monkeypatch.setattr(job, "POPULAR_DESTINATIONS", ["PBI"])
    fake_search["PBI"] = [_offer(99)]

    job.refresh_deals()

    deal = _cached(fake_redis)["deals"][0]
    assert deal["destination_city"] is None
    assert deal["destination_country_code"] is None


def test_deals_do_not_store_deep_links(fake_search, fake_redis):
    # Prices are live; a deal can be hours old, so it must be re-searched to book.
    fake_search["MAD"] = [_offer(250)]
    job.refresh_deals()
    assert "deep_link" not in _cached(fake_redis)["deals"][0]


def test_missing_api_key_stops_after_first_destination(monkeypatch, fake_redis):
    stub = StubProvider({d: ProviderNotConfiguredError("no key") for d in job.POPULAR_DESTINATIONS})
    monkeypatch.setattr(job, "get_provider", lambda: stub)
    assert job.refresh_deals() == 0
    assert stub.calls == 1
    assert job.DEALS_CACHE_KEY not in fake_redis.store
