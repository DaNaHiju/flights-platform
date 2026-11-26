"""Thin read-only HTTP client for the Brisa API.

Every failure becomes a BrisaError whose message is written for the model:
what happened and what to try next. No raw httpx exception or stack trace
ever reaches the tool result.
"""
import httpx


class BrisaError(Exception):
    """A failure the model can read and act on."""


# Error codes of docs/api-contract.md, turned into advice.
_ERRORS = {
    "invalid_iata_code": (
        "origin/destination must be a 3-letter IATA code, optionally followed by '+' "
        "(e.g. 'TYO' for a city, 'NRT+' for one airport). Use search_locations to find the code."
    ),
    "same_origin_and_destination": "origin and destination are the same place.",
    "invalid_date_format": "dates must be formatted YYYY-MM-DD.",
    "date_in_past": "the date is in the past; use today or a later date.",
    "return_before_departure": "return_date is before the departure date.",
    "invalid_search": "the flight provider rejected these search parameters. Check the codes and dates.",
    "provider_unavailable": (
        "the flight provider is unavailable (timeout, upstream error or rejected key). "
        "Try again in a minute."
    ),
    "provider_rate_limited": "the flight provider quota is exhausted. Try again later.",
    "provider_not_configured": "the Brisa API has no flight provider key configured, so it cannot search.",
    "deals_not_available": "no deals have been computed yet (the worker has not run). Try again later.",
}


class BrisaClient:
    def __init__(self, base_url: str, timeout_seconds: float, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._http = httpx.Client(timeout=timeout_seconds, transport=transport)

    def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = self._http.get(url, params=params)
        except httpx.TimeoutException:
            raise BrisaError(
                f"Brisa API at {self.base_url} did not answer within {self.timeout_seconds:g} s. "
                "Searches can be slow; try again."
            ) from None
        except httpx.TransportError:
            raise BrisaError(f"Brisa API not reachable at {self.base_url}") from None

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError:
                raise BrisaError("Brisa API returned a body that is not JSON.") from None
        raise BrisaError(self._explain(response))

    @staticmethod
    def _explain(response: httpx.Response) -> str:
        status = response.status_code
        code = None
        try:
            body = response.json()
            code = body.get("error") if isinstance(body, dict) else None
        except ValueError:
            pass
        if code in _ERRORS:
            return f"Brisa API error {status} ({code}): {_ERRORS[code]}"
        if status == 422:
            return (
                "Brisa API rejected the request (422): a parameter is missing or invalid. "
                "Check that origin/destination are 3-letter codes (optionally ending in '+'), "
                "dates are YYYY-MM-DD and adults is between 1 and 9."
            )
        if code:
            return f"Brisa API error {status} ({code})."
        return f"Brisa API error {status}."
