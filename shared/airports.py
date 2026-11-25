"""Airport enrichment: airport name, city and country for an IATA code.

Data comes from `airportsdata` (MIT, bundled CSV, no network), so enriching a
search result never costs an extra provider call. Anything missing resolves to
None: the provider can return airports that the dataset does not know.
"""

from functools import lru_cache

import airportsdata


@lru_cache(maxsize=1)
def _airports() -> dict:
    return airportsdata.load("IATA")


def airport_name(code: str | None) -> str | None:
    """Airport name for an IATA airport code, None when unknown."""
    info = _airports().get(code) if code else None
    return (info.get("name") or None) if info else None


def city_and_country(code: str | None) -> tuple[str | None, str | None]:
    """(city, ISO 3166-1 alpha-2 country) for an IATA code; (None, None) if unknown."""
    info = _airports().get(code) if code else None
    if not info:
        return None, None
    return info.get("city") or None, info.get("country") or None
