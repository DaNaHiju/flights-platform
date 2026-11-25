"""Prometheus metrics used by code shared between the API and the worker."""

from prometheus_client import Counter

# reason: unavailable | rate_limited | not_configured | bad_request.
# A plain sum(rate(provider_errors_total[5m])) keeps working across all reasons.
provider_errors = Counter(
    "provider_errors_total",
    "Total number of failed calls to the flight data provider",
    ["provider", "reason"],
)
