"""Shared pytest fixtures for the worker: a fake Redis client, no database."""

import os

import pytest

# worker.config refuses to import without REDIS_URL, so it must be set BEFORE the
# project imports below. The host is on the reserved .invalid TLD (RFC 2606) and
# can never resolve; the fake_redis fixture replaces the client anyway.
os.environ["REDIS_URL"] = "redis://redis.invalid:6379/0"
# Removed, not just left unset: proves the worker imports and runs without a
# database even when a developer has DATABASE_URL exported in their shell.
os.environ.pop("DATABASE_URL", None)

from shared import cache  # noqa: E402


class FakeRedis:
    """Minimal in-memory stand-in for redis.Redis that also records TTLs."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttls[key] = ex

    def ping(self):
        return True


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Replace the Redis client with an in-memory fake for every test."""
    fake = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", fake)
    return fake
