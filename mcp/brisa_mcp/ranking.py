"""Ranking of offers: a Python port of services/web/src/results.ts.

Kept in step with the web app so the model and the UI agree on what "best" means.
Ported from results.ts: rankOneWay / rankRoundTrip / dedupe / bestScore / sortRanked.
"""
from dataclasses import dataclass, field

SORT_KEYS = ("best", "cheapest", "fastest")


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


def best_score(r: Ranked, min_price: float, min_duration: int) -> float:
    """"Best" score, lower is better. Same formula as bestScore in results.ts:

        price / cheapestPrice + duration / shortestDuration + 0.25 * stops

    Price and duration are measured against the best value in the list; each stop
    costs a quarter of that.
    """
    return r.price / min_price + r.duration / min_duration + 0.25 * r.stops


def sort_ranked(ranked: list[Ranked], key: str) -> list[Ranked]:
    """A new list in the order of *key*; ties fall back to price (or duration), as in sortRanked."""
    if not ranked:
        return []
    min_price = min(r.price for r in ranked)
    min_duration = min(r.duration for r in ranked)
    by = {
        "best": lambda r: (best_score(r, min_price, min_duration), r.price),
        "cheapest": lambda r: (r.price, r.duration),
        "fastest": lambda r: (r.duration, r.price),
    }
    return sorted(ranked, key=by[key])
