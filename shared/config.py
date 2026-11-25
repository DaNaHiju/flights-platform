"""Configuration shared by every service, loaded from environment variables.

Only settings that BOTH the API and the worker need live here. Each service
declares its own settings in its own config module (services/api/app/config.py,
services/worker/worker/config.py).

This module does NOT validate anything when imported. Each service calls
`require_env` exactly once, with its complete list (SHARED_REQUIRED_ENV plus
its own), so a single error names every missing variable — not one per deploy.
"""

import os

# Required by code in shared/ itself (shared/cache.py connects to Redis).
SHARED_REQUIRED_ENV = ("REDIS_URL",)


def require_env(*names: str) -> None:
    """Raise a clear error naming every variable in *names* that is unset or empty.

    Connection strings have NO default on purpose: if one is missing the process
    must stop at import time with a clear message, not fall back silently to
    localhost and fail later with a confusing connection error.
    """
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "They have no default and must be injected at runtime: in Kubernetes "
            "by the manifests repo (ExternalSecret / ConfigMap), locally by the "
            "`environment:` block of docker-compose.yml."
        )


class SharedSettings:
    """Settings every service needs; read from the environment at import time."""

    # Read with getenv (None if unset) so importing this module never raises on
    # its own. There is no fallback value: the service's require_env call has
    # already stopped the process if it is missing.
    REDIS_URL: str | None = os.getenv("REDIS_URL")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    APP_NAME: str = os.getenv("APP_NAME", "flights-api")

    # Shared so live search results and cached deals are always priced in the
    # same currency.
    FLIGHTS_CURRENCY: str = os.getenv("FLIGHTS_CURRENCY", "USD")

    # --- Flight data provider -------------------------------------------------
    # Which implementation of shared.providers.FlightProvider to use. Only
    # "amadeus" exists today; the setting is the seam for swapping it later.
    FLIGHTS_PROVIDER: str = os.getenv("FLIGHTS_PROVIDER", "amadeus")

    # Amadeus Travel Builder APIs. The key is a secret: in Kubernetes it comes
    # from an ExternalSecret (manifests repo), locally from your shell. It is
    # deliberately NOT in require_env: without it the service still starts and
    # answers searches with 503 provider_not_configured, instead of crash-looping.
    AMADEUS_API_KEY: str | None = os.getenv("AMADEUS_API_KEY") or None
    AMADEUS_GATEWAY_URL: str = os.getenv(
        "AMADEUS_GATEWAY_URL", "https://api.amadeus.com"
    )
    # A flight search fans out to many airlines, so it gets a longer read timeout
    # than the reference-data lookups (airlines, locations).
    AMADEUS_SEARCH_TIMEOUT_SECONDS: float = float(
        os.getenv("AMADEUS_SEARCH_TIMEOUT_SECONDS", "25")
    )
    AMADEUS_LOOKUP_TIMEOUT_SECONDS: float = float(
        os.getenv("AMADEUS_LOOKUP_TIMEOUT_SECONDS", "5")
    )
    # Cap per airline; a search across every airline can return hundreds of offers.
    AMADEUS_MAX_RESULTS_PER_MERCHANT: int = int(
        os.getenv("AMADEUS_MAX_RESULTS_PER_MERCHANT", "20")
    )

    # Reference data barely changes, so lookups are cached far longer than
    # searches: airline names for 7 days, airport/city typeahead for 1 day.
    AIRLINES_CACHE_TTL: int = int(os.getenv("AIRLINES_CACHE_TTL", "604800"))
    LOCATIONS_CACHE_TTL: int = int(os.getenv("LOCATIONS_CACHE_TTL", "86400"))


settings = SharedSettings()
