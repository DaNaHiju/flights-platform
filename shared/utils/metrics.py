"""Prometheus metrics used by code shared between the API and the worker."""

from prometheus_client import Counter

provider_errors = Counter(
    "provider_errors_total",
    "Total number of failed calls to fli (Google Flights)",
)
