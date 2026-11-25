"""One place that turns provider errors into HTTP responses.

Every router that calls the flight provider uses this, so the same failure
always reaches the user with the same status and error code:

    ProviderBadRequestError     -> 400 invalid_search
    ProviderUnavailableError    -> 502 provider_unavailable
    ProviderRateLimitedError    -> 503 provider_rate_limited (+ Retry-After)
    ProviderNotConfiguredError  -> 503 provider_not_configured
"""

from fastapi import HTTPException, status

from shared.providers import (
    ProviderBadRequestError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRateLimitedError,
)
from shared.utils.logging import log
from shared.utils.metrics import provider_errors


def provider_http_exception(exc: ProviderError, provider: str, context: str) -> HTTPException:
    """Log and count *exc*, and return the HTTPException to raise for it."""
    if isinstance(exc, ProviderBadRequestError):
        reason, code, error = "bad_request", status.HTTP_400_BAD_REQUEST, "invalid_search"
    elif isinstance(exc, ProviderRateLimitedError):
        reason, code, error = (
            "rate_limited",
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "provider_rate_limited",
        )
    elif isinstance(exc, ProviderNotConfiguredError):
        reason, code, error = (
            "not_configured",
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "provider_not_configured",
        )
    else:
        reason, code, error = "unavailable", status.HTTP_502_BAD_GATEWAY, "provider_unavailable"

    provider_errors.labels(provider=provider, reason=reason).inc()
    log.warning("%s failed (%s): %s", context, reason, exc)

    headers = None
    if isinstance(exc, ProviderRateLimitedError):
        headers = {"Retry-After": str(exc.retry_after)}
    return HTTPException(status_code=code, detail={"error": error}, headers=headers)
