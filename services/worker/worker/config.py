"""Worker settings: the shared settings plus what only the worker needs.

No DATABASE_URL here on purpose — the worker only reads fli and writes Redis.
There is no refresh interval either: each run refreshes once and exits; how
often it runs is the CronJob's schedule (manifests repo).
"""

import os

from shared.config import SHARED_REQUIRED_ENV, SharedSettings, require_env

# The worker's complete list, checked in ONE call. Runs at import time —
# worker/__init__.py imports this module first, before shared.cache connects.
REQUIRED_ENV = SHARED_REQUIRED_ENV
require_env(*REQUIRED_ENV)


class Settings(SharedSettings):
    """Worker settings; inherits REDIS_URL, LOG_LEVEL, ENVIRONMENT, APP_NAME, ..."""

    FLIGHTS_DEFAULT_ORIGIN: str = os.getenv("FLIGHTS_DEFAULT_ORIGIN", "TLV")
    DEALS_CACHE_TTL: int = int(os.getenv("DEALS_CACHE_TTL", "7200"))


settings = Settings()
