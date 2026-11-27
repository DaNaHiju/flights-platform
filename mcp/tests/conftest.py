import itertools
import json
from pathlib import Path

import httpx
import pytest

from brisa_mcp.client import BrisaClient

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "http://brisa.test/api"

_ids = itertools.count(1)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def json_response(body: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


def make_offer(offer_id: str, price: float, minutes: int, *carriers: tuple[str, str], bags=()) -> dict:
    """A minimal one-way FlightOffer with one flight per (airline name, IATA code) in *carriers*.

    Every offer gets its own flight numbers so dedupe never merges two of them.
    """
    legs = []
    for name, code in carriers:
        n = next(_ids)
        legs.append({
            "airline": name,
            "airline_code": code,
            "flight_number": f"{code}{n}",
            "departure_datetime": f"2027-05-10T{n % 24:02d}:00:00+03:00",
            "arrival_datetime": f"2027-05-11T{n % 24:02d}:30:00+09:00",
            "duration_minutes": minutes // len(carriers),
            "departure_airport_code": "TLV",
            "arrival_airport_code": "KIX",
            "departure_airport": "Ben Gurion International Airport",
            "arrival_airport": "Kansai International Airport",
        })
    return {
        "offer_id": offer_id,
        "price": price,
        "currency": "ILS",
        "duration_minutes": minutes,
        "total_duration_minutes": minutes,
        "stops": len(legs) - 1,
        "primary_airline": carriers[0][0],
        "primary_airline_code": carriers[0][1],
        "carriers": [name for name, _ in carriers],
        "deep_link": f"https://example.test/book/{offer_id}",
        "checked_bags": [] if bags == () else bags,
        "legs": legs,
    }


EY = ("Etihad Airways", "EY")
QR = ("Qatar Airways", "QR")
A3 = ("Aegean Airlines", "A3")
LH = ("Lufthansa", "LH")
TK = ("Turkish Airlines", "TK")
AI = ("Air India", "AI")


def airline_mix() -> dict:
    """One dominant airline (EY, 5 offers) and five others: 6 groups in all.

    Groups by cheapest price: EY 2,400, QR 2,500, A3 + QR 2,550, LH 2,800, TK 2,950, AI 3,100.
    The ids say what each offer is for:
      EY-cheap-short / EY-cheap-long: same price, the shorter one is the group's cheapest.
      EY-fast-low / EY-fast-high: same (shortest) duration, the lower price is the group's fastest.
    """
    offers = [
        make_offer("EY-cheap-long", 2400, 1000, EY),
        make_offer("EY-cheap-short", 2400, 900, EY),
        make_offer("EY-fast-high", 2700, 800, EY),
        make_offer("EY-fast-low", 2600, 800, EY),
        make_offer("EY-slow", 3000, 1200, EY),
        make_offer("QR-only", 2500, 700, QR),  # cheapest and fastest of its group at once
        make_offer("A3QR-cheap", 2550, 1300, A3, QR),
        make_offer("A3QR-fast", 2900, 900, A3, QR),
        make_offer("LH-only", 2800, 1100, LH),
        make_offer("TK-only", 2950, 1000, TK),
        make_offer("AI-cheap", 3100, 1000, AI),
        make_offer("AI-fast", 3300, 950, AI),
    ]
    return {"results": offers}


@pytest.fixture
def make_client():
    """make_client(handler) -> (BrisaClient, requests); every request is recorded."""

    def factory(handler):
        requests: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        return BrisaClient(BASE, 5.0, transport=httpx.MockTransport(recording)), requests

    return factory
