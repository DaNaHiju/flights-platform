"""Canned Amadeus Travel Builder responses and a fake gateway for tests.

Shapes follow the documented responses (flight search v3, airlines, locations).
No test talks to the real gateway: FakeGateway is an httpx.MockTransport.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Callable

import httpx

from shared.providers.amadeus import AmadeusClient, AmadeusProvider

TEST_API_KEY = "test-key-not-a-secret"


def flight(
    airline: str,
    number: str,
    origin: str,
    destination: str,
    departs_at: str,
    arrives_at: str,
    duration: str,
    **extra,
) -> dict:
    return {
        "marketing_airline": airline,
        "flight_number": number,
        "origin": {"airport": origin},
        "destination": {"airport": destination},
        "departs_at": departs_at,
        "arrives_at": arrives_at,
        "duration": duration,
        "booking_infos": [{"ptc": "ADT", "priced_ptc": "ADT", "travel_class": "ECONOMY"}],
        **extra,
    }


def result(merchant: str, price: float, bounds: list[list[dict]], deep_link=True, currency="USD"):
    body = {
        "bounds": [{"duration": "00:00", "flights": flights} for flights in bounds],
        "fare": {
            "currency": currency,
            "itinerary_price": {"total_fare": price, "tax": 10.0},
        },
        "merchant": merchant,
    }
    if deep_link:
        body["deep_link"] = f"https://example.test/{merchant}/book"
    return body


# TLV -> MAD, one direct LY flight and one UX flight via... direct too, priced higher.
LY_DIRECT = flight(
    "LY", "395", "TLV", "MAD", "2099-01-01T08:00:00+02:00", "2099-01-01T12:15:00+01:00", "05:15"
)
UX_DIRECT = flight(
    "UX", "1302", "TLV", "MAD", "2099-01-01T16:05:00+02:00", "2099-01-01T20:20:00+01:00", "05:15"
)
# A connection on a partner: LH sells it, the second flight is marketed by LX.
LH_VIA_FRA = [
    flight("LH", "687", "TLV", "FRA", "2099-01-01T05:00:00+02:00", "2099-01-01T08:15:00+01:00", "04:15"),
    flight(
        "LX", "4100", "FRA", "MAD", "2099-01-01T10:00:00+01:00", "2099-01-01T12:35:00+01:00", "02:35",
        operating_airline="LH", operating_airline_type="IATA",
    ),
]

ONE_WAY_RESPONSE = {
    "request_id": "req-1",
    "results": [
        result("UX", 410.0, [[UX_DIRECT]]),
        result("LY", 250.5, [[LY_DIRECT]]),
        result("LH", 199.0, [LH_VIA_FRA], deep_link=False),
    ],
    "errors": {"IB": "120 - No flight found on this route for merchant IB"},
    "meta": {"carriers": {"LY": {"name": "El Al"}}},
}

LY_BACK = flight(
    "LY", "396", "MAD", "TLV", "2099-01-08T13:30:00+01:00", "2099-01-08T19:30:00+02:00", "05:00"
)
ROUND_TRIP_RESPONSE = {
    "request_id": "req-2",
    "results": [
        result("LY", 520.0, [[LY_DIRECT], [LY_BACK]]),
        result("UX", 480.0, [[UX_DIRECT], [LY_BACK]]),
    ],
}

AIRLINES_RESPONSE = {
    "data": [
        {"type": "airline", "iataCode": "LH", "icaoCode": "DLH", "businessName": "LUFTHANSA"},
        {"type": "airline", "iataCode": "LX", "icaoCode": "SWR", "businessName": "SWISS"},
        {"type": "airline", "iataCode": "LY", "icaoCode": "ELY", "businessName": "EL AL ISRAEL AIRLINES"},
        {"type": "airline", "iataCode": "UX", "icaoCode": "AEA", "businessName": "AIR EUROPA"},
        {"type": "airline", "iataCode": "XX", "businessName": "UNDEFINED"},
    ]
}

LOCATIONS_RESPONSE = {
    "meta": {"count": 3},
    "data": [
        {
            "type": "location", "subType": "CITY", "name": "MADRID", "detailedName": "MADRID/ES",
            "id": "CMAD", "iataCode": "MAD",
            "address": {"cityName": "MADRID", "cityCode": "MAD", "countryName": "SPAIN", "countryCode": "ES"},
        },
        {
            "type": "location", "subType": "AIRPORT", "name": "ADOLFO SUAREZ BARAJAS",
            "detailedName": "MADRID/ES:ADOLFO SUAREZ BARAJAS", "id": "AMAD", "iataCode": "MAD",
            "address": {"cityName": "MADRID", "cityCode": "MAD", "countryName": "SPAIN", "countryCode": "ES"},
        },
        # Duplicate id: must be shown once.
        {
            "type": "location", "subType": "CITY", "name": "MADRID", "detailedName": "MADRID/ES",
            "id": "CMAD", "iataCode": "MAD", "address": {"cityName": "MADRID", "countryName": "SPAIN"},
        },
    ],
}

Handler = Callable[[httpx.Request], httpx.Response]


def json_response(body: dict, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body), headers=headers or {})


class FakeGateway:
    """Routes requests by path to queued responses and records every request."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self._routes: dict[str, list] = defaultdict(list)
        self.sleeps: list[float] = []

    def on(self, path: str, *responses) -> "FakeGateway":
        """Queue responses for *path*. The last one repeats once the queue runs out.

        Each item is an httpx.Response, a dict (sent as 200 JSON) or an
        exception instance (raised, e.g. httpx.ReadTimeout).
        """
        self._routes[path].extend(responses)
        return self

    def calls(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == path]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self._routes.get(request.url.path)
        if not queue:
            return json_response({"errors": [{"code": 404}]}, status=404)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            return json_response(item)
        return item

    def provider(self, **kwargs) -> AmadeusProvider:
        client = AmadeusClient(
            TEST_API_KEY,
            "https://gateway.test",
            transport=httpx.MockTransport(self.handler),
            sleep=self.sleeps.append,
        )
        return AmadeusProvider(client, **kwargs)


SEARCH = "/api/v3/search/"
AIRLINES = "/v1/reference-data/airlines"
LOCATIONS = "/v1/reference-data/locations"


def standard_gateway() -> FakeGateway:
    return (
        FakeGateway()
        .on(SEARCH, ONE_WAY_RESPONSE)
        .on(AIRLINES, AIRLINES_RESPONSE)
        .on(LOCATIONS, LOCATIONS_RESPONSE)
    )
