"""Grouping offers by airline, so one airline with many schedules cannot fill the answer.

A group is the set of airlines that operate an offer, in flight order: "Etihad Airways" is one
group and "Aegean Airlines + Qatar Airways" is another, so a mixed itinerary is never counted
as either of its carriers alone. For a round trip the airlines of both directions are joined.
Each group exposes its cheapest and its fastest offer.
"""
from dataclasses import dataclass

from brisa_mcp.ranking import Ranked


@dataclass
class AirlineGroup:
    name: str  # "Aegean Airlines + Qatar Airways"
    codes: tuple[str, ...]  # IATA codes of the same airlines, e.g. ("A3", "QR"); may be empty
    offers: list[Ranked]
    cheapest: Ranked  # lowest price; ties go to the shorter trip
    fastest: Ranked  # shortest total duration; ties go to the lower price

    @property
    def label(self) -> str:
        return f"{self.name} ({' + '.join(self.codes)})" if self.codes else self.name


def cheapest_of(offers: list[Ranked]) -> Ranked:
    return min(offers, key=lambda r: (r.price, r.duration))


def fastest_of(offers: list[Ranked]) -> Ranked:
    return min(offers, key=lambda r: (r.duration, r.price))


def _directions(item: dict) -> list[dict]:
    return [item["outbound"], item["return"]] if "outbound" in item else [item]


def _distinct(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v for v in values if v))


def airline_names(r: Ranked) -> tuple[str, ...]:
    names: list[str] = []
    for direction in _directions(r.item):
        names += direction.get("carriers") or [direction.get("primary_airline")]
    return _distinct(names) or ("Unknown airline",)


def airline_codes(r: Ranked) -> tuple[str, ...]:
    codes: list[str | None] = []
    for direction in _directions(r.item):
        legs = direction.get("legs") or []
        codes += [leg.get("airline_code") for leg in legs] or [direction.get("primary_airline_code")]
    return _distinct(codes)


def group_by_airline(ranked: list[Ranked]) -> list[AirlineGroup]:
    """Groups ordered by their cheapest offer (ties: shorter trip, then name)."""
    buckets: dict[tuple[str, ...], list[Ranked]] = {}
    for r in ranked:
        buckets.setdefault(airline_names(r), []).append(r)
    groups = []
    for names, offers in buckets.items():
        cheapest = cheapest_of(offers)
        groups.append(AirlineGroup(
            name=" + ".join(names),
            codes=airline_codes(cheapest),
            offers=offers,
            cheapest=cheapest,
            fastest=fastest_of(offers),
        ))
    return sorted(groups, key=lambda g: (g.cheapest.price, g.cheapest.duration, g.name))


def offers_with_airline(ranked: list[Ranked], code: str) -> list[Ranked]:
    """Offers where *code* operates at least one flight (alone or in a mixed itinerary)."""
    return [r for r in ranked if code.upper() in airline_codes(r)]


def airline_name_for(ranked: list[Ranked], code: str) -> str:
    """The airline's name as the API spells it in the legs of *ranked*, or the code itself."""
    for r in ranked:
        for direction in _directions(r.item):
            for leg in direction.get("legs") or []:
                if (leg.get("airline_code") or "").upper() == code.upper() and leg.get("airline"):
                    return leg["airline"]
    return code.upper()
