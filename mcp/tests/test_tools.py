import asyncio

import httpx
import pytest

from brisa_mcp import tools
from brisa_mcp.client import BrisaError
from brisa_mcp.server import build_server
from tests.conftest import BASE, json_response, load


def flights_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/flights"
    fixture = "flights_round_trip.json" if "return_date" in request.url.params else "flights_one_way.json"
    return json_response(load(fixture))


# ── search_locations ────────────────────────────────────────────────────────

def test_search_locations_lists_the_short_fields(make_client):
    client, requests = make_client(lambda r: json_response(load("locations_tokyo.json")))
    text = tools.search_locations(client, "tokyo")
    assert requests[0].url.params["keyword"] == "tokyo"
    assert "Tokyo | CITY | iata_code=TYO | search_code=TYO | city=Tokyo | country=Japan" in text
    assert "Narita Intl | AIRPORT | iata_code=NRT | search_code=NRT+ | city=Tokyo | country=Japan" in text
    assert "detailed_name" not in text  # only the short list


def test_search_locations_no_match(make_client):
    client, _ = make_client(lambda r: json_response({"results": []}))
    assert "No airports or cities found" in tools.search_locations(client, "zzzz")


# ── search_flights, one way ─────────────────────────────────────────────────

def test_one_way_summary_uses_local_times_and_shows_stops(make_client):
    client, requests = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", sort="cheapest")
    params = requests[0].url.params
    assert (params["origin"], params["destination"], params["date"], params["adults"]) == ("TLV", "NRT+", "2027-01-20", "1")
    assert "return_date" not in params
    # Header: 5 offers sent, one is the same trip sold twice, so 4; range from the cheapest to the priciest.
    assert text.startswith("4 offers for TLV -> NRT+ on 2027-01-20 (one way), 1 adult(s). Price range: 2,580 ILS to 2,802 ILS.")
    first = text.split("\n\n")[1]
    assert first.startswith("1. 2,580 ILS")
    # Local clock times exactly as sent (05:20 +02:00 -> 11:55 +09:00), never converted; +1 day.
    assert "2027-01-20 05:20" in first and "2027-01-21 11:55 (+1 day)" in first
    assert "2 stops" in first and "stop at" in first and "layover" in first
    assert "checked bags: 25 KG" in first
    assert "deep_link: https://example.test/book/" in first


def test_layover_is_computed_across_timezones(make_client):
    client, _ = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", sort="fastest", limit=1)
    # Fastest = 14h15m: TLV 14:25 (+02:00) -> ... -> NRT 11:40 (+09:00) next day.
    assert "14h 15m total" in text
    assert "layover" in text


def test_unknown_bags_are_not_reported_as_no_bag(make_client):
    client, _ = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", sort="cheapest")
    # Only the 3rd offer (the fixture whose checked_bags is null) is unknown.
    blocks = [b for b in text.split("\n\n")[1:]]
    unknown = [b for b in blocks if "checked bags: unknown" in b]
    assert len(unknown) == 1 and "no checked bag" not in unknown[0]


def test_empty_bag_list_means_none_included():
    from brisa_mcp.summary import fmt_bags

    assert fmt_bags([]) == "no checked bag included"
    assert fmt_bags(None) == "unknown"
    # Seen on the real API: a zero allowance is how a fare without a bag is reported.
    assert fmt_bags([{"type": "piece", "quantity": 0, "weight_amount": None, "weight_unit": None, "applicable_legs": [1]}]) == "no checked bag included"
    assert fmt_bags([{"type": "piece", "quantity": 1, "weight_amount": 23, "weight_unit": "KG"}]) == "1 piece(s) of 23 KG each"


def names(text: str) -> list[str]:
    return [line.split(" ")[1] for line in text.splitlines() if line[:2] in {f"{i}." for i in range(1, 10)}]


def prices(text: str) -> list[float]:
    return [float(p.replace(",", "")) for p in names(text)]


def test_sort_orders(make_client):
    client, _ = make_client(flights_handler)
    cheapest = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", sort="cheapest")
    assert prices(cheapest) == [2580, 2769, 2802, 2802]
    fastest = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", sort="fastest")
    assert "1. 2,802 ILS" in fastest and "14h 15m total" in fastest.split("\n\n")[1]
    # best = price/min + duration/min + 0.25*stops: the 1-stop 14h15m at 2,802 beats the 2,580 two-stopper.
    best = tools.search_flights(client, "TLV", "NRT+", "2027-01-20")
    assert prices(best)[0] == 2802 and "14h 15m total" in best.split("\n\n")[1]
    assert prices(best)[-1] == 2580


def test_limit_is_respected(make_client):
    client, _ = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", limit=2)
    assert len(names(text)) == 2
    assert "Showing the top 2" in text and text.startswith("4 offers")


def test_limit_is_capped(make_client):
    client, _ = make_client(flights_handler)
    # 4 offers exist; asking for 500 shows them all and never more than MAX_LIMIT.
    assert len(names(tools.search_flights(client, "TLV", "NRT+", "2027-01-20", limit=500))) == 4


@pytest.mark.parametrize("kwargs, message", [
    ({"sort": "random"}, "sort must be one of"),
    ({"limit": 0}, "limit must be at least 1"),
    ({"date": "20/01/2027"}, "date must be formatted YYYY-MM-DD"),
    ({"return_date": "soon"}, "return_date must be formatted YYYY-MM-DD"),
])
def test_bad_arguments_fail_before_calling_the_api(make_client, kwargs, message):
    client, requests = make_client(flights_handler)
    args = {"origin": "TLV", "destination": "NRT+", "date": "2027-01-20", **kwargs}
    with pytest.raises(BrisaError, match=message):
        tools.search_flights(client, **args)
    assert requests == []


def test_no_offers(make_client):
    client, _ = make_client(lambda r: json_response({"results": []}))
    assert "No offers found" in tools.search_flights(client, "TLV", "NRT+", "2027-01-20")


# ── search_flights, round trip ──────────────────────────────────────────────

def test_round_trip_shows_both_directions_and_the_pair_price(make_client):
    client, requests = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", return_date="2027-01-30", adults=2, sort="cheapest", limit=1)
    assert requests[0].url.params["return_date"] == "2027-01-30" and requests[0].url.params["adults"] == "2"
    assert "returning 2027-01-30" in text and "2 adult(s)" in text
    first = text.split("\n\n")[1]
    assert first.startswith("1. 4,340 ILS round trip total")
    assert "Outbound:" in first and "Return:" in first
    assert first.count("checked bags:") == 2
    assert first.count("deep_link:") == 1
    assert "(+1 day)" in first  # TLV -> NRT lands the next local day


def test_round_trip_header_counts_pairs_and_price_range(make_client):
    client, _ = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", return_date="2027-01-30")
    assert text.startswith("3 offers for TLV -> NRT+ on 2027-01-20, returning 2027-01-30")
    assert "Price range: 4,340 ILS to" in text


# ── search_multi_city ───────────────────────────────────────────────────────

LEGS = [
    {"origin": "TLV", "destination": "NRT+", "date": "2027-01-20"},
    {"origin": "TYO", "destination": "SEL", "date": "2027-01-27"},
]


def test_multi_city_one_search_per_leg_and_combined_total(make_client):
    client, requests = make_client(flights_handler)
    text = tools.search_multi_city(client, LEGS, adults=1, limit=1)
    assert [r.url.params["origin"] for r in requests] == ["TLV", "TYO"]
    assert all("return_date" not in r.url.params for r in requests)  # one way per leg
    assert "Leg 1: TLV -> NRT+ on 2027-01-20 (one way)" in text and "Leg 2: TYO -> SEL" in text
    assert "Cheapest combined total: 5,160 ILS" in text  # 2 x 2,580
    assert "separate one-way ticket" in text
    assert text.count("deep_link:") == 2  # limit=1 per leg


def test_multi_city_needs_two_to_six_legs(make_client):
    client, requests = make_client(flights_handler)
    with pytest.raises(BrisaError, match="between 2 and 6"):
        tools.search_multi_city(client, LEGS[:1])
    with pytest.raises(BrisaError, match="between 2 and 6"):
        tools.search_multi_city(client, LEGS * 4)
    assert requests == []


def test_multi_city_missing_field_and_failing_leg(make_client):
    client, _ = make_client(flights_handler)
    with pytest.raises(BrisaError, match="leg 2 is missing date"):
        tools.search_multi_city(client, [LEGS[0], {"origin": "TYO", "destination": "SEL"}])

    def second_leg_fails(request):
        if request.url.params["origin"] == "TYO":
            return json_response({"error": "date_in_past"}, 400)
        return json_response(load("flights_one_way.json"))

    client, _ = make_client(second_leg_fails)
    with pytest.raises(BrisaError, match=r"Leg 2 \(TYO -> SEL on 2027-01-27\) failed: .*date_in_past"):
        tools.search_multi_city(client, LEGS)


def test_multi_city_does_not_sum_different_currencies(make_client):
    def handler(request):
        body = load("flights_one_way.json")
        if request.url.params["origin"] == "TYO":
            for offer in body["results"]:
                offer["currency"] = "USD"
        return json_response(body)

    client, _ = make_client(handler)
    assert "not summed" in tools.search_multi_city(client, LEGS)


# ── get_deals ───────────────────────────────────────────────────────────────

def test_get_deals(make_client):
    client, requests = make_client(lambda r: json_response(load("deals.json")))
    text = tools.get_deals(client)
    assert requests[0].url.path == "/api/deals"
    assert "2 current deal(s)" in text
    assert "Rome (FCO), 2026-12-26 (one way): 437 ILS, Ita Airways, outbound 3h 50m" in text
    assert "Madrid (MAD), 2027-01-12 -> 2027-01-19 (round trip): 512 ILS, Iberia" in text


def test_get_deals_empty(make_client):
    client, _ = make_client(lambda r: json_response({"deals": [], "refreshed_at": "x"}))
    assert tools.get_deals(client) == "There are no deals right now."


# ── errors ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status, body, expected", [
    (400, {"error": "invalid_iata_code"}, "3-letter IATA code"),
    (400, {"error": "date_in_past"}, "date is in the past"),
    (502, {"error": "provider_unavailable"}, "provider is unavailable"),
    (503, {"error": "provider_rate_limited"}, "quota is exhausted"),
    (503, {"error": "provider_not_configured"}, "no flight provider key"),
    (503, {"error": "deals_not_available"}, "no deals have been computed"),
    (422, {"detail": [{"msg": "field required"}]}, "3-letter codes"),
    (500, {"error": "boom"}, r"Brisa API error 500 \(boom\)"),
])
def test_api_errors_become_clear_messages(make_client, status, body, expected):
    client, _ = make_client(lambda r: json_response(body, status))
    with pytest.raises(BrisaError, match=expected) as info:
        tools.search_flights(client, "TLV", "NRT+", "2027-01-20")
    assert str(status) in str(info.value)


def test_non_json_error_body(make_client):
    client, _ = make_client(lambda r: httpx.Response(502, text="<html>Bad Gateway</html>"))
    with pytest.raises(BrisaError, match="Brisa API error 502."):
        tools.get_deals(client)


def test_unreachable_api(make_client):
    def refuse(request):
        raise httpx.ConnectError("refused")

    client, _ = make_client(refuse)
    with pytest.raises(BrisaError) as info:
        tools.get_deals(client)
    assert str(info.value) == f"Brisa API not reachable at {BASE}"


def test_timeout(make_client):
    def slow(request):
        raise httpx.ReadTimeout("slow")

    client, _ = make_client(slow)
    with pytest.raises(BrisaError, match="did not answer within 5 s"):
        tools.get_deals(client)


# ── the MCP surface ─────────────────────────────────────────────────────────

def test_server_registers_exactly_the_four_read_only_tools(make_client):
    client, _ = make_client(flights_handler)
    listed = asyncio.run(build_server(client).list_tools())
    assert sorted(t.name for t in listed) == ["get_deals", "search_flights", "search_locations", "search_multi_city"]
    flights = next(t for t in listed if t.name == "search_flights")
    assert "YYYY-MM-DD" in flights.description and "NRT+" in flights.description and "search_locations" in flights.description


def test_tool_error_reaches_the_model_without_a_stack_trace(make_client):
    from mcp.server.fastmcp.exceptions import ToolError

    client, _ = make_client(lambda r: json_response({"error": "provider_unavailable"}, 502))
    with pytest.raises(ToolError, match="provider is unavailable"):
        asyncio.run(build_server(client).call_tool("get_deals", {}))


def test_the_client_only_ever_sends_get(make_client):
    client, requests = make_client(flights_handler)
    tools.search_flights(client, "TLV", "NRT+", "2027-01-20")
    tools.search_multi_city(client, LEGS)
    assert {r.method for r in requests} == {"GET"}
