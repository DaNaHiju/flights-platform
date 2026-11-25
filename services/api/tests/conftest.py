"""Shared pytest fixtures: in-memory SQLite DB and a fake Redis client."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# app.config refuses to import without these, so they must be set BEFORE the
# project imports below (a fixture is too late: monkeypatch only exists per test).
# Assigned, not setdefault, so a developer's real DATABASE_URL can never leak into
# a test run. Nothing here is a credential: a local SQLite file, and a Redis host
# on the reserved .invalid TLD (RFC 2606) that can never resolve. The fake_redis
# fixture replaces the client anyway.
SQLALCHEMY_TEST_URL = "sqlite:///./test.db"
os.environ["DATABASE_URL"] = SQLALCHEMY_TEST_URL
os.environ["REDIS_URL"] = "redis://redis.invalid:6379/0"
# Removed so no test can ever reach the real Amadeus gateway, even when a
# developer has a real key exported in their shell.
os.environ.pop("AMADEUS_API_KEY", None)

from shared import cache  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from shared.providers import get_provider  # noqa: E402

engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Swap production DB session for the in-memory test session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


class FakeRedis:
    """Minimal in-memory stand-in for redis.Redis, scoped to a single test."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def ping(self):
        return True


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Replace the Redis client with an in-memory fake for every test."""
    fake = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", fake)
    return fake


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """Return a synchronous test client."""
    return TestClient(app)


@pytest.fixture
def use_provider():
    """Swap the flight provider the API uses: use_provider(some_provider)."""

    def _use(provider):
        app.dependency_overrides[get_provider] = lambda: provider
        return provider

    yield _use
    app.dependency_overrides.pop(get_provider, None)
