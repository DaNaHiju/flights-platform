"""Prometheus metrics definitions for the flights API."""

from prometheus_client import Counter, Histogram

request_count = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)

request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

bookings_created = Counter(
    "bookings_created_total",
    "Total number of bookings successfully created",
)

provider_errors = Counter(
    "provider_errors_total",
    "Total number of failed calls to fli (Google Flights)",
)
