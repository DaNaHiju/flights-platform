"""Application configuration loaded from environment variables."""

import os


class Settings:
    """Central settings object; all values read from environment at import time."""

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/flights",
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    APP_NAME: str = os.getenv("APP_NAME", "flights-api")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # fli has no API key — these just steer what it asks Google Flights for.
    FLIGHTS_CURRENCY: str = os.getenv("FLIGHTS_CURRENCY", "USD")
    FLIGHTS_DEFAULT_ORIGIN: str = os.getenv("FLIGHTS_DEFAULT_ORIGIN", "TLV")

    SEARCH_CACHE_TTL: int = int(os.getenv("SEARCH_CACHE_TTL", "600"))
    DEALS_CACHE_TTL: int = int(os.getenv("DEALS_CACHE_TTL", "7200"))
    # Assumed validity window of a fli booking_token before Google expires it.
    # Unverified — see docs/api-contract.md open questions.
    OFFER_CACHE_TTL: int = int(os.getenv("OFFER_CACHE_TTL", "600"))


settings = Settings()
