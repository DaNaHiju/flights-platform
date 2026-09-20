"""Redis client and JSON cache helpers."""

import json
from typing import Any

import redis

from app.config import settings

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_json(key: str) -> Any | None:
    """Return the JSON-decoded value at *key*, or None if missing."""
    raw = redis_client.get(key)
    return json.loads(raw) if raw is not None else None


def set_json(key: str, value: Any, ttl: int) -> None:
    """Store *value* as JSON at *key* with a TTL in seconds."""
    redis_client.set(key, json.dumps(value), ex=ttl)


def ping() -> bool:
    """Return True if Redis is reachable."""
    try:
        return bool(redis_client.ping())
    except redis.RedisError:
        return False
