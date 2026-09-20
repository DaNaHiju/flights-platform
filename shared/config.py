"""Application configuration loaded from environment variables."""

import os

# Connection strings have NO default on purpose: if one is missing the process
# must stop at import time with a clear message, not fall back silently to
# localhost and fail later with a confusing connection error.
REQUIRED_ENV = ("DATABASE_URL", "REDIS_URL")


def _check_required_env() -> None:
    """Raise a clear error naming every required variable that is unset or empty."""
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "They have no default and must be injected at runtime: in Kubernetes "
            "by the manifests repo (ExternalSecret / ConfigMap), locally by the "
            "`environment:` block of docker-compose.yml."
        )


_check_required_env()


class Settings:
    """Central settings object; all values read from environment at import time."""

    DATABASE_URL: str = os.environ["DATABASE_URL"]
    REDIS_URL: str = os.environ["REDIS_URL"]
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
