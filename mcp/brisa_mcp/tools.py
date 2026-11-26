"""The four tools, as plain functions of (client, arguments) -> text.

server.py registers them with FastMCP; keeping them apart lets the tests call
them directly with a client built on httpx.MockTransport. All of them only
issue GET requests: there is no write path in this package.
"""
import re

from brisa_mcp.client import BrisaClient, BrisaError
from brisa_mcp.ranking import SORT_KEYS, dedupe, rank_one_way, rank_round_trip, sort_ranked
from brisa_mcp.summary import describe_offer, fmt_price, price_range

MAX_LIMIT = 20  # the api returns ~170 offers (1 MB+); more than this is noise for a model
MAX_LEGS = 6  # each leg is one provider search against a limited quota
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(name: str, value: str) -> None:
    if not _DATE.match(value or ""):
        raise BrisaError(f"{name} must be formatted YYYY-MM-DD, got {value!r}.")


def _check_limit(limit: int) -> int:
    if limit < 1:
        raise BrisaError("limit must be at least 1.")
    return min(limit, MAX_LIMIT)


def search_locations(client: BrisaClient, keyword: str) -> str:
    results = client.get("/locations", {"keyword": keyword}).get("results", [])
    if not results:
        return f"No airports or cities found for {keyword!r}. Try another spelling or a shorter keyword."
    lines = [f"{len(results)} location(s) for {keyword!r} (use search_code as origin/destination):"]
    for loc in results:
        lines.append(
            f"- {loc.get('name')} | {loc.get('sub_type')} | iata_code={loc.get('iata_code')} | "
            f"search_code={loc.get('search_code')} | city={loc.get('city_name')} | country={loc.get('country_name')}"
        )
    return "\n".join(lines)


def _search(client: BrisaClient, origin: str, destination: str, date: str, return_date: str | None, adults: int):
    _check_date("date", date)
    params = {"origin": origin, "destination": destination, "date": date, "adults": adults}
    if return_date:
        _check_date("return_date", return_date)
        params["return_date"] = return_date
    results = client.get("/flights", params).get("results", [])
    rank = rank_round_trip if return_date else rank_one_way
    return dedupe([rank(o) for o in results])


def search_flights(
    client: BrisaClient,
    origin: str,
    destination: str,
    date: str,
    return_date: str | None = None,
    adults: int = 1,
    sort: str = "best",
    limit: int = 10,
) -> str:
    if sort not in SORT_KEYS:
        raise BrisaError(f"sort must be one of {', '.join(SORT_KEYS)}, got {sort!r}.")
    limit = _check_limit(limit)
    ranked = _search(client, origin, destination, date, return_date, adults)
    trip = f"{origin} -> {destination} on {date}" + (f", returning {return_date}" if return_date else " (one way)")
    if not ranked:
        return f"No offers found for {trip}, {adults} adult(s)."
    shown = sort_ranked(ranked, sort)[:limit]
    header = (
        f"{len(ranked)} offers for {trip}, {adults} adult(s). Price range: {price_range(ranked)}. "
        f"Showing the top {len(shown)} by '{sort}'. Prices are the total for all passengers."
    )
    return "\n\n".join([header] + [describe_offer(i, r) for i, r in enumerate(shown, 1)])


def search_multi_city(client: BrisaClient, legs: list[dict], adults: int = 1, limit: int = 3) -> str:
    if not 2 <= len(legs) <= MAX_LEGS:
        raise BrisaError(f"legs must have between 2 and {MAX_LEGS} entries, got {len(legs)}.")
    limit = _check_limit(limit)
    sections, cheapest = [], []
    for n, leg in enumerate(legs, 1):
        missing = [k for k in ("origin", "destination", "date") if not leg.get(k)]
        if missing:
            raise BrisaError(f"leg {n} is missing {', '.join(missing)}.")
        try:
            ranked = _search(client, leg["origin"], leg["destination"], leg["date"], None, adults)
        except BrisaError as e:
            raise BrisaError(f"Leg {n} ({leg['origin']} -> {leg['destination']} on {leg['date']}) failed: {e}") from None
        title = f"Leg {n}: {leg['origin']} -> {leg['destination']} on {leg['date']} (one way)"
        if not ranked:
            sections.append(f"{title}\nNo offers found.")
            continue
        top = sort_ranked(ranked, "best")[:limit]
        cheapest.append(min(ranked, key=lambda r: r.price))
        sections.append("\n\n".join([f"{title}: {len(ranked)} offers, price range {price_range(ranked)}. Top {len(top)} by 'best':"]
                                    + [describe_offer(i, r) for i, r in enumerate(top, 1)]))
    note = "Each leg is a separate one-way ticket: separate bookings, no protection if one is delayed or cancelled."
    if len(cheapest) < len(legs):
        total = "Cheapest combined total: unavailable, at least one leg has no offers."
    else:
        currencies = {r.item["currency"] for r in cheapest}
        if len(currencies) > 1:
            total = f"Cheapest combined total: not summed, the legs are priced in different currencies ({', '.join(sorted(currencies))})."
        else:
            total = f"Cheapest combined total: {fmt_price(sum(r.price for r in cheapest), currencies.pop())} (the cheapest offer of each leg added up)."
    return "\n\n".join(sections + [total, note])


def get_deals(client: BrisaClient) -> str:
    data = client.get("/deals")
    deals = data.get("deals", [])
    if not deals:
        return "There are no deals right now."
    lines = [f"{len(deals)} current deal(s), refreshed at {data.get('refreshed_at')}. Prices are live-at-refresh and can be hours old:"]
    for d in deals:
        trip = f"{d['departure_date']} -> {d['return_date']} (round trip)" if d.get("return_date") else f"{d['departure_date']} (one way)"
        duration = f", outbound {d['total_duration_minutes'] // 60}h {d['total_duration_minutes'] % 60:02d}m" if d.get("total_duration_minutes") is not None else ""
        lines.append(
            f"- {d.get('origin_city') or d.get('origin', '?')} ({d.get('origin', '?')}) -> "
            f"{d.get('destination_city') or d['destination']} ({d['destination']}), {trip}: "
            f"{fmt_price(d['price'], d['currency'])}, {d.get('airline', '?')}{duration}"
        )
    return "\n".join(lines)
