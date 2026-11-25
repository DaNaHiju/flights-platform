"""Redis client and JSON cache helpers."""

import json
from typing import Any

import redis

from shared.config import settings
from shared.utils.logging import log

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_json(key: str) -> Any | None:
    """Return the JSON-decoded value at *key*, or None if missing."""
    raw = redis_client.get(key)
    return json.loads(raw) if raw is not None else None


def set_json(key: str, value: Any, ttl: int) -> None:
    """Store *value* as JSON at *key* with a TTL in seconds."""
    redis_client.set(key, json.dumps(value), ex=ttl)


def try_get_json(key: str) -> Any | None:
    """Like get_json, but a Redis failure is logged and treated as a cache miss.

    For pure caches in front of the flight provider: Redis being down must make
    requests slower (they go to the provider), not fail them.
    """
    try:
        return get_json(key)
    except redis.RedisError as exc:
        log.warning("Redis read failed for %s, treating as a miss: %s", key, exc)
        return None


def try_set_json(key: str, value: Any, ttl: int) -> None:
    """Like set_json, but a Redis failure is logged and ignored."""
    try:
        set_json(key, value, ttl)
    except redis.RedisError as exc:
        log.warning("Redis write failed for %s, not cached: %s", key, exc)


def ping() -> bool:
    """Return True if Redis is reachable."""
    try:
        return bool(redis_client.ping())
    except redis.RedisError:
        return False
