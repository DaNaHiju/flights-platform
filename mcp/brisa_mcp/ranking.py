"""Normalising offers: a Python port of the helpers in services/web/src/results.ts.

Ported from results.ts: rankOneWay / rankRoundTrip / dedupe. The "best" score and the
sort orders of the web app are not ported: the MCP tools no longer show a top-N list,
they show the cheapest and the fastest offer of each airline (see airlines.py).
"""
from dataclasses import dataclass, field


@dataclass
class Ranked:
    item: dict  # the FlightOffer (one way) or RoundTripOffer (round trip), as the API sent it
    price: float
    duration: int  # minutes; for a round trip, outbound + return
    stops: int  # for a round trip, outbound + return
    signature: str | None = field(default=None)


def total_minutes(offer: dict) -> int:
    # results.ts totalMinutes
    value = offer.get("total_duration_minutes")
    return value if value is not None else offer.get("duration_minutes", 0)


def offer_signature(offer: dict) -> str | None:
    # results.ts offerSignature: flight number + departure time of every leg.
    legs = offer.get("legs") or []
    if not legs:
        return None
    return "|".join(f"{leg.get('flight_number')}@{leg.get('departure_datetime')}" for leg in legs)


def rank_one_way(offer: dict) -> Ranked:
    return Ranked(
        item=offer,
        price=offer["price"],
        duration=total_minutes(offer),
        stops=offer.get("stops", 0),
        signature=offer_signature(offer),
    )


def rank_round_trip(offer: dict) -> Ranked:
    out, back = offer["outbound"], offer["return"]
    sig_out, sig_back = offer_signature(out), offer_signature(back)
    return Ranked(
        item=offer,
        price=offer["price"],
        duration=total_minutes(out) + total_minutes(back),
        stops=out.get("stops", 0) + back.get("stops", 0),
        signature=f"{sig_out}||{sig_back}" if sig_out and sig_back else None,
    )


def dedupe(ranked: list[Ranked]) -> list[Ranked]:
    """Same flights in every leg = the same trip sold twice: keep the cheapest (results.ts dedupe)."""
    cheapest: dict[str, Ranked] = {}
    for r in ranked:
        if r.signature is None:
            continue
        seen = cheapest.get(r.signature)
        if seen is None or r.price < seen.price:
            cheapest[r.signature] = r
    return [r for r in ranked if r.signature is None or cheapest[r.signature] is r]
