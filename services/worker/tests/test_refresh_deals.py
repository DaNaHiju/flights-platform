"""Tests for the deals refresh job. The provider is always a stub — no network calls."""

import importlib
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from shared.providers import ProviderNotConfiguredError, ProviderUnavailableError
from shared.schemas import Deal, FlightOffer, RoundTripOffer
from worker import refresh_deals as job
from worker.config import settings


def _flight(price: float, airline: str, duration: int, tag: str) -> FlightOffer:
    return FlightOffer(
        offer_id=f"{airline}-{price}-{tag}",
        price=price,
        currency="USD",
        duration_minutes=duration,
        total_duration_minutes=duration,
        stops=0,
        primary_airline=airline,
        deep_link="https://example.test/book",
        legs=[],
    )


def _offer(price: float, airline: str = "El Al", duration: int = 315) -> RoundTripOffer:
    """A round-trip pair; refresh_deals reads its price, outbound airline and duration."""
    return RoundTripOffer(
        price=price,
        currency="USD",
        deep_link="https://example.test/book",
        outbound=_flight(price, airline, duration, "out"),
        # A different airline and duration on the way back, to prove they are ignored.
        return_=_flight(price, "Return Air", duration + 100, "ret"),
    )


class StubProvider:
    name = "stub"

    def __init__(self, results: dict):
        self.results = results
        self.calls = 0
        self.searches: list[tuple] = []

    def search_round_trip(self, origin, destination, date, return_date, adults, currency):
        self.calls += 1
        self.searches.append((origin, destination, date, return_date, adults, currency))
        outcome = self.results.get(destination, [])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def search_one_way(self, *args, **kwargs):  # pragma: no cover - must not be used
        raise AssertionError("deals are round trips: search_one_way must not be called")


@pytest.fixture
def stub(monkeypatch):
    """The stubbed provider, installed in the job; keeps a record of every search."""
    provider = StubProvider({})
    monkeypatch.setattr(job, "get_provider", lambda: provider)
    return provider


@pytest.fixture
def fake_search(stub):
    """*results* maps destination -> offers or exception."""
    return stub.results


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


# ── Round-trip deals ─────────────────────────────────────────────────────────


def test_searches_a_round_trip_30_days_out_lasting_the_trip_length(fake_search, stub):
    fake_search["MAD"] = [_offer(100)]
    before = datetime.now(timezone.utc).date()

    job.refresh_deals()

    after = datetime.now(timezone.utc).date()
    origin, destination, outbound, back, adults, currency = stub.searches[0]
    assert (origin, destination, adults) == (settings.FLIGHTS_DEFAULT_ORIGIN, "MAD", 1)
    assert currency == settings.FLIGHTS_CURRENCY
    outbound_day = date.fromisoformat(outbound)
    # `before`/`after` bracket the call, so a run across UTC midnight cannot flake.
    assert before + timedelta(days=30) <= outbound_day <= after + timedelta(days=30)
    assert date.fromisoformat(back) - outbound_day == timedelta(days=7)


def test_trip_length_comes_from_the_setting(fake_search, stub, monkeypatch):
    monkeypatch.setattr(settings, "DEALS_TRIP_LENGTH_DAYS", 14)
    fake_search["MAD"] = [_offer(100)]

    job.refresh_deals()

    _, _, outbound, back, _, _ = stub.searches[0]
    assert date.fromisoformat(back) - date.fromisoformat(outbound) == timedelta(days=14)


def test_default_trip_length_is_7_days_and_is_read_from_env(monkeypatch):
    from worker import config

    try:
        monkeypatch.delenv("DEALS_TRIP_LENGTH_DAYS", raising=False)
        assert importlib.reload(config).settings.DEALS_TRIP_LENGTH_DAYS == 7
        monkeypatch.setenv("DEALS_TRIP_LENGTH_DAYS", "10")
        assert importlib.reload(config).settings.DEALS_TRIP_LENGTH_DAYS == 10
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_one_search_call_per_destination_and_never_one_way(fake_search, stub):
    for destination in job.POPULAR_DESTINATIONS:
        fake_search[destination] = [_offer(100)]

    job.refresh_deals()

    assert stub.calls == len(job.POPULAR_DESTINATIONS)


def test_deal_keeps_the_cheapest_pair_with_its_total_and_both_dates(fake_search, stub, fake_redis):
    fake_search["MAD"] = [_offer(900, "Dear Air"), _offer(640, "Cheap Air", duration=400)]

    job.refresh_deals()

    deal = _cached(fake_redis)["deals"][0]
    assert deal["price"] == 640  # the pair's total, not one leg's price
    assert deal["airline"] == "Cheap Air"  # the outbound's, not "Return Air"
    assert deal["total_duration_minutes"] == 400  # the outbound's
    _, _, outbound, back, _, _ = stub.searches[0]
    assert (deal["departure_date"], deal["return_date"]) == (outbound, back)


def test_cached_round_trip_deal_matches_the_deal_schema(fake_search, fake_redis):
    fake_search["MAD"] = [_offer(250)]
    job.refresh_deals()
    deal = Deal.model_validate(_cached(fake_redis)["deals"][0])
    assert deal.return_date is not None


def test_one_way_deals_already_in_redis_still_validate():
    # What the worker wrote before round-trip deals existed: no return_date key.
    old = {"destination": "MAD", "departure_date": "2099-01-01", "price": 250.0,
           "currency": "USD", "airline": "El Al"}
    assert Deal.model_validate(old).return_date is None
