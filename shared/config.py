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

    # fli has no API key — this just steers what it asks Google Flights for.
    # Shared so live search results and cached deals are always priced in the
    # same currency.
    FLIGHTS_CURRENCY: str = os.getenv("FLIGHTS_CURRENCY", "USD")


settings = SharedSettings()
