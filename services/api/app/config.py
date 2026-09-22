"""API settings: the shared settings plus what only the API needs."""

import os

from shared.config import SHARED_REQUIRED_ENV, SharedSettings, require_env

# The API's complete list, checked in ONE call so a single error names every
# missing variable. Runs at import time — app/__init__.py imports this module
# first, before any code that connects to Redis or PostgreSQL.
REQUIRED_ENV = (*SHARED_REQUIRED_ENV, "DATABASE_URL")
require_env(*REQUIRED_ENV)


class Settings(SharedSettings):
    """API settings; inherits REDIS_URL, LOG_LEVEL, ENVIRONMENT, APP_NAME, ..."""

    DATABASE_URL: str = os.environ["DATABASE_URL"]
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    SEARCH_CACHE_TTL: int = int(os.getenv("SEARCH_CACHE_TTL", "600"))
    # Assumed validity window of a fli booking_token before Google expires it.
    # Unverified — see docs/api-contract.md open questions.
    OFFER_CACHE_TTL: int = int(os.getenv("OFFER_CACHE_TTL", "600"))


settings = Settings()
