"""Plain-text summaries of API answers, written to be read by a model.

Times are local to each airport, exactly as the API sends them (docs/api-contract.md:
"Display as is; never convert"). Nothing here converts a timezone.
"""
from datetime import datetime

from brisa_mcp.ranking import Ranked, total_minutes


def fmt_minutes(minutes: int) -> str:
    hours, mins = divmod(int(minutes), 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def fmt_price(price: float, currency: str) -> str:
    return f"{price:,.0f} {currency}" if float(price).is_integer() else f"{price:,.2f} {currency}"


def _clock(iso: str) -> str:
    return f"{iso[:10]} {iso[11:16]}"  # local wall time as sent: '2027-01-20 05:20'


def _day_offset(first_iso: str, last_iso: str) -> int:
    # Difference between the LOCAL calendar dates, which is what a traveller reads as "+1".
    return (datetime.fromisoformat(last_iso[:10]) - datetime.fromisoformat(first_iso[:10])).days


def _airport(leg: dict, side: str) -> str:
    code = leg.get(f"{side}_airport_code")
    name = leg.get(f"{side}_airport")
    if code and name and name != code:
        return f"{code} ({name})"
    return code or name or "?"


def _layover_minutes(prev_leg: dict, next_leg: dict) -> int:
    # Both timestamps carry their own UTC offset, so the subtraction is exact across timezones.
    gap = datetime.fromisoformat(next_leg["departure_datetime"]) - datetime.fromisoformat(prev_leg["arrival_datetime"])
    return int(gap.total_seconds() // 60)


def fmt_bags(checked_bags: list | None) -> str:
    # null means unknown, never "no bag"; [] means the airline said none is included.
    if checked_bags is None:
        return "unknown"
    if not checked_bags:
        return "no checked bag included"
    # Amadeus says "no bag" as a piece/weight allowance of zero, not as an empty list.
    allowances = [b for b in checked_bags if (b.get("quantity") or b.get("weight_amount") or 0) > 0]
    if not allowances:
        return "no checked bag included"
    parts = []
    for bag in allowances:
        weight = (
            f"{bag['weight_amount']} {bag.get('weight_unit') or ''}".strip()
            if bag.get("weight_amount") is not None
            else None
        )
        if bag.get("type") == "piece" and bag.get("quantity") is not None:
            text = f"{bag['quantity']} piece(s)" + (f" of {weight} each" if weight else "")
        else:
            text = weight or "included (size not stated)"
        parts.append(text)
    return ", ".join(parts)


def describe_direction(offer: dict, indent: str = "   ") -> list[str]:
    """Lines for one direction: times, duration, stops, bags (price excluded)."""
    legs = offer.get("legs") or []
    airlines = ", ".join(offer.get("carriers") or [offer.get("primary_airline", "?")])
    lines = []
    if legs:
        first, last = legs[0], legs[-1]
        plus = _day_offset(first["departure_datetime"], last["arrival_datetime"])
        arrival = _clock(last["arrival_datetime"]) + (f" (+{plus} day{'s' if plus != 1 else ''})" if plus > 0 else "")
        lines.append(
            f"{indent}{_airport(first, 'departure')} {_clock(first['departure_datetime'])} -> "
            f"{_airport(last, 'arrival')} {arrival}  (local times)"
        )
    stops = offer.get("stops", max(len(legs) - 1, 0))
    lines.append(f"{indent}{airlines} | {fmt_minutes(total_minutes(offer))} total | "
                 + ("nonstop" if stops == 0 else f"{stops} stop{'s' if stops != 1 else ''}"))
    for prev, nxt in zip(legs, legs[1:]):
        lines.append(
            f"{indent}  stop at {_airport(prev, 'arrival')}: layover {fmt_minutes(max(_layover_minutes(prev, nxt), 0))}"
        )
    lines.append(f"{indent}checked bags: {fmt_bags(offer.get('checked_bags'))}")
    return lines



def describe_offer(label: str, r: Ranked) -> str:
    """One offer under a label such as "cheapest" or "cheapest and fastest"."""
    offer = r.item
    link = offer.get("deep_link") or "none"
    if "outbound" in offer:  # round trip
        lines = [f"{label}: {fmt_price(offer['price'], offer['currency'])} round trip total",
                 "   Outbound:"]
        lines += describe_direction(offer["outbound"], "     ")
        lines.append("   Return:")
        lines += describe_direction(offer["return"], "     ")
    else:
        lines = [f"{label}: {fmt_price(offer['price'], offer['currency'])}"]
        lines += describe_direction(offer)
    lines.append(f"   deep_link: {link}")
    return "\n".join(lines)


def price_range(ranked: list[Ranked]) -> str:
    currency = ranked[0].item["currency"]
    lo, hi = min(r.price for r in ranked), max(r.price for r in ranked)
    return fmt_price(lo, currency) if lo == hi else f"{fmt_price(lo, currency)} to {fmt_price(hi, currency)}"
