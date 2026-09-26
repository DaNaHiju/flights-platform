"""Flights API application package."""

# Python runs a package's __init__ before any of its submodules, so importing
# app.config here guarantees the environment check happens first — before e.g.
# app.api.bookings imports shared.cache, which opens the Redis client.
from app import config  # noqa: F401
