"""The four tools, as plain functions of (client, arguments) -> text.

server.py registers them with FastMCP; keeping them apart lets the tests call
them directly with a client built on httpx.MockTransport. All of them only
issue GET requests: there is no write path in this package.
"""
import re

from brisa_mcp.airlines import (
    airline_name_for,
    cheapest_of,
    fastest_of,
    group_by_airline,
    offers_with_airline,
)
from brisa_mcp.client import BrisaClient, BrisaError
from brisa_mcp.ranking import Ranked, dedupe, rank_one_way, rank_round_trip
from brisa_mcp.summary import describe_offer, fmt_price, price_range

DEFAULT_AIRLINES = 4  # airline groups shown per search
MAX_AIRLINES = 8  # the api returns ~170 offers (1 MB+); more groups than this is noise for a model
MAX_LEGS = 6  # each leg is one provider search against a limited quota
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AIRLINE_CODE = re.compile(r"^[A-Za-z0-9]{2}$")


def _check_date(name: str, value: str) -> None:
    if not _DATE.match(value or ""):
        raise BrisaError(f"{name} must be formatted YYYY-MM-DD, got {value!r}.")


def _check_airlines(airlines: int) -> int:
    if not 1 <= airlines <= MAX_AIRLINES:
        raise BrisaError(f"airlines must be between 1 and {MAX_AIRLINES}, got {airlines}.")
    return airlines


def _check_airline_code(code: str | None) -> str | None:
    if code is None or code == "":
        return None
    if not _AIRLINE_CODE.match(code):
        raise BrisaError(f"airline must be a 2-character IATA airline code such as 'AI' or 'EY', got {code!r}.")
    return code.upper()


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


def _offer_roles(cheapest: Ranked, fastest: Ranked) -> list[str]:
    if cheapest is fastest:
        return [describe_offer("cheapest and fastest", cheapest)]
    return [describe_offer("cheapest", cheapest), describe_offer("fastest", fastest)]


def _airline_blocks(ranked: list[Ranked], airlines: int, airline: str | None) -> tuple[list[str], Ranked | None]:
    """Text blocks for the airline view of one search, and the cheapest offer they contain.

    Without *airline*: the first `airlines` airline groups by their cheapest offer, two offers
    each (cheapest, fastest), then one line naming the groups that did not fit.
    With *airline* (IATA code): only that airline's own cheapest and fastest offers, whether
    or not it would have made the top.
    """
    groups = group_by_airline(ranked)
    if airline:
        matching = offers_with_airline(ranked, airline)
        if not matching:
            known = ", ".join(g.label for g in groups)
            return [f"No offer includes airline {airline}. Airlines in these results: {known}."], None
        cheapest, fastest = cheapest_of(matching), fastest_of(matching)
        title = (f"{airline_name_for(matching, airline)} ({airline}): {len(matching)} of {len(ranked)} offers "
                 f"include it, price range {price_range(matching)}")
        return [title] + _offer_roles(cheapest, fastest), cheapest

    shown = groups[:airlines]
    blocks = []
    for n, group in enumerate(shown, 1):
        count = f"{len(group.offers)} offer{'s' if len(group.offers) != 1 else ''}"
        first, *others = _offer_roles(group.cheapest, group.fastest)
        blocks.append(f"Airline {n}: {group.label}, {count}\n{first}")  # the heading stays with its first offer
        blocks += others
    rest = groups[airlines:]
    if rest:
        blocks.append(f"{len(rest)} more airline{'s' if len(rest) != 1 else ''}: {', '.join(g.name for g in rest)}")
    return blocks, shown[0].cheapest


def _stats(ranked: list[Ranked]) -> str:
    return f"{len(ranked)} offers from {len(group_by_airline(ranked))} airlines"


def search_flights(
    client: BrisaClient,
    origin: str,
    destination: str,
    date: str,
    return_date: str | None = None,
    adults: int = 1,
    airlines: int = DEFAULT_AIRLINES,
    airline: str | None = None,
) -> str:
    airlines = _check_airlines(airlines)
    airline = _check_airline_code(airline)
    ranked = _search(client, origin, destination, date, return_date, adults)
    trip = f"{origin} -> {destination} on {date}" + (f", returning {return_date}" if return_date else " (one way)")
    if not ranked:
        return f"No offers found for {trip}, {adults} adult(s)."
    blocks, _ = _airline_blocks(ranked, airlines, airline)
    header = (
        f"{_stats(ranked)} for {trip}, {adults} adult(s). Price range: {price_range(ranked)}. "
        "Prices are the total for all passengers."
    )
    return "\n\n".join([header] + blocks)


def search_multi_city(client: BrisaClient, legs: list[dict], adults: int = 1, airlines: int = DEFAULT_AIRLINES) -> str:
    if not 2 <= len(legs) <= MAX_LEGS:
        raise BrisaError(f"legs must have between 2 and {MAX_LEGS} entries, got {len(legs)}.")
    airlines = _check_airlines(airlines)
    sections, cheapest, filtered = [], [], False
    for n, leg in enumerate(legs, 1):
        missing = [k for k in ("origin", "destination", "date") if not leg.get(k)]
        if missing:
            raise BrisaError(f"leg {n} is missing {', '.join(missing)}.")
        try:
            airline = _check_airline_code(leg.get("airline"))
        except BrisaError as e:
            raise BrisaError(f"leg {n}: {e}") from None
        try:
            ranked = _search(client, leg["origin"], leg["destination"], leg["date"], None, adults)
        except BrisaError as e:
            raise BrisaError(f"Leg {n} ({leg['origin']} -> {leg['destination']} on {leg['date']}) failed: {e}") from None
        title = f"Leg {n}: {leg['origin']} -> {leg['destination']} on {leg['date']} (one way)"
        if not ranked:
            sections.append(f"{title}\nNo offers found.")
            continue
        blocks, leg_cheapest = _airline_blocks(ranked, airlines, airline)
        if leg_cheapest is not None:
            cheapest.append(leg_cheapest)
        filtered = filtered or airline is not None
        sections.append("\n\n".join([f"{title}: {_stats(ranked)}, price range {price_range(ranked)}."] + blocks))
    note = "Each leg is a separate one-way ticket: separate bookings, no protection if one is delayed or cancelled."
    if len(cheapest) < len(legs):
        total = "Cheapest combined total: unavailable, at least one leg has no offers."
    else:
        currencies = {r.item["currency"] for r in cheapest}
        if len(currencies) > 1:
            total = f"Cheapest combined total: not summed, the legs are priced in different currencies ({', '.join(sorted(currencies))})."
        else:
            what = "the cheapest offer of each leg added up"
            if filtered:
                what += "; a leg with an airline filter counts that airline's cheapest offer"
            total = f"Cheapest combined total: {fmt_price(sum(r.price for r in cheapest), currencies.pop())} ({what})."
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
