"""Airport enrichment: IATA code, city and country for the public schemas.

fli models airports as an enum whose NAME is the IATA code and whose VALUE is
the airport name. `model_dump(mode="json")` keeps only the value, so the code
has to be recovered from the name. City and country come from `airportsdata`
(MIT, bundled CSV, no network). Anything missing resolves to None.
"""

from functools import lru_cache

import airportsdata
from fli.models import Airport


@lru_cache(maxsize=1)
def _airports() -> dict:
    return airportsdata.load("IATA")


def iata_from_airport(value: str | None) -> str | None:
    """IATA code for fli's airport name (or for a code, returned as is)."""
    if not value:
        return None
    if value in Airport.__members__:
        return value
    try:
        return Airport(value).name
    except ValueError:
        return None


def airport_name(code: str | None) -> str | None:
    """fli's airport name for an IATA code, None when unknown."""
    if not code or code not in Airport.__members__:
        return None
    return Airport[code].value


def city_and_country(code: str | None) -> tuple[str | None, str | None]:
    """(city, ISO 3166-1 alpha-2 country) for an IATA code; (None, None) if unknown."""
    info = _airports().get(code) if code else None
    if not info:
        return None, None
    return info.get("city") or None, info.get("country") or None
