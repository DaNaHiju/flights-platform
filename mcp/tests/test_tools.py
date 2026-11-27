import asyncio
import re

import httpx
import pytest

from brisa_mcp import tools
from brisa_mcp.client import BrisaError
from brisa_mcp.server import build_server
from tests.conftest import BASE, EY, airline_mix, json_response, load, make_offer


def flights_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/flights"
    fixture = "flights_round_trip.json" if "return_date" in request.url.params else "flights_one_way.json"
    return json_response(load(fixture))


def mix_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/api/flights"
    return json_response(airline_mix())


def group_titles(text: str) -> list[str]:
    return [line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Airline ")]


def group_section(text: str, n: int) -> str:
    """The text of 'Airline n' up to the next group (or the 'more airlines' line)."""
    match = re.search(rf"^Airline {n}:.*?(?=^Airline \d+:|^\d+ more airlines?:|\Z)", text, re.S | re.M)
    assert match, f"no Airline {n} in:\n{text}"
    return match.group(0)


def book_ids(section: str) -> list[str]:
    return re.findall(r"deep_link: https://example.test/book/(\S+)", section)


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


# ── search_flights: airline groups ──────────────────────────────────────────

def test_top_four_airline_groups_by_cheapest_price(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10")
    # 12 offers, 6 groups; the dominant airline (5 offers) takes one slot, not the whole answer.
    assert text.startswith("12 offers from 6 airlines for TLV -> OSA on 2027-05-10 (one way), 1 adult(s).")
    assert "Price range: 2,400 ILS to 3,300 ILS." in text
    assert group_titles(text) == [
        "Etihad Airways (EY), 5 offers",
        "Qatar Airways (QR), 1 offer",
        "Aegean Airlines + Qatar Airways (A3 + QR), 2 offers",
        "Lufthansa (LH), 1 offer",
    ]
    assert "Air India" not in text.split("more airlines")[0]  # AI and TK did not make the top 4


def test_more_airlines_line_names_the_rest(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10")
    assert text.splitlines()[-1] == "2 more airlines: Turkish Airlines, Air India"
    # Names only: no prices, no codes, no deep links in that line.
    assert "AI-cheap" not in text.splitlines()[-1]


def test_more_airlines_line_is_singular_for_one_and_absent_for_none(make_client):
    client, _ = make_client(mix_handler)
    five = tools.search_flights(client, "TLV", "OSA", "2027-05-10", airlines=5)
    assert five.splitlines()[-1] == "1 more airline: Air India"
    six = tools.search_flights(client, "TLV", "OSA", "2027-05-10", airlines=6)
    assert "more airline" not in six and len(group_titles(six)) == 6


def test_airlines_parameter_limits_the_groups(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10", airlines=2)
    assert len(group_titles(text)) == 2
    assert text.splitlines()[-1].startswith("4 more airlines: Aegean Airlines + Qatar Airways, Lufthansa")


def test_cheapest_and_fastest_tie_breaks(make_client):
    client, _ = make_client(mix_handler)
    section = group_section(tools.search_flights(client, "TLV", "OSA", "2027-05-10"), 1)
    # Same price 2,400: the shorter trip (900 min) is the cheapest.
    cheapest = section.split("fastest:")[0]
    assert "cheapest: 2,400 ILS" in cheapest and book_ids(cheapest) == ["EY-cheap-short"]
    assert "15h 00m total" in cheapest
    # Two offers share the shortest duration (800 min): the lower price (2,600) is the fastest.
    fastest = "fastest:" + section.split("fastest:")[1]
    assert "fastest: 2,600 ILS" in fastest and book_ids(fastest) == ["EY-fast-low"]
    assert "13h 20m total" in fastest


def test_same_offer_in_both_roles_is_shown_once(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10")
    qr = group_section(text, 2)
    assert "cheapest and fastest: 2,500 ILS" in qr
    assert book_ids(qr) == ["QR-only"]
    assert "\ncheapest:" not in qr and "\nfastest:" not in qr
    # A group with two different offers shows both, each once.
    assert len(book_ids(group_section(text, 1))) == 2
    assert book_ids(group_section(text, 3)) == ["A3QR-cheap", "A3QR-fast"]


def test_a_mixed_itinerary_is_its_own_group(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10")
    assert "Qatar Airways (QR), 1 offer" in text  # the A3 + QR offers did not join the QR group
    assert "Aegean Airlines + Qatar Airways (A3 + QR), 2 offers" in text


@pytest.mark.parametrize("airlines", [0, -1, 9, 50])
def test_airlines_out_of_range_is_rejected_before_calling_the_api(make_client, airlines):
    client, requests = make_client(mix_handler)
    with pytest.raises(BrisaError, match=rf"airlines must be between 1 and 8, got {airlines}"):
        tools.search_flights(client, "TLV", "OSA", "2027-05-10", airlines=airlines)
    assert requests == []


def test_airlines_eight_is_allowed(make_client):
    client, _ = make_client(mix_handler)
    assert len(group_titles(tools.search_flights(client, "TLV", "OSA", "2027-05-10", airlines=8))) == 6


# ── search_flights: airline filter ──────────────────────────────────────────

def test_airline_outside_the_top_returns_its_cheapest_and_fastest(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10", airline="ai")  # case does not matter
    assert text.startswith("12 offers from 6 airlines for TLV -> OSA")  # header still describes the whole search
    assert "Air India (AI): 2 of 12 offers include it, price range 3,100 ILS to 3,300 ILS" in text
    assert "cheapest: 3,100 ILS" in text and "fastest: 3,300 ILS" in text
    assert book_ids(text) == ["AI-cheap", "AI-fast"]
    assert "Airline 1:" not in text and "more airline" not in text


def test_airline_filter_includes_mixed_itineraries(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10", airline="QR")
    # QR flies alone (1 offer) and with Aegean (2 offers).
    assert "Qatar Airways (QR): 3 of 12 offers include it" in text
    assert "cheapest and fastest: 2,500 ILS" in text and book_ids(text) == ["QR-only"]


def test_airline_without_offers_lists_what_is_available(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_flights(client, "TLV", "OSA", "2027-05-10", airline="BA")
    assert text.startswith("12 offers from 6 airlines")
    assert "No offer includes airline BA." in text
    assert "Etihad Airways (EY)" in text and "Air India (AI)" in text


@pytest.mark.parametrize("code", ["A", "AIR", "A-", "Air India"])
def test_bad_airline_code_is_rejected_before_calling_the_api(make_client, code):
    client, requests = make_client(mix_handler)
    with pytest.raises(BrisaError, match="airline must be a 2-character IATA airline code"):
        tools.search_flights(client, "TLV", "OSA", "2027-05-10", airline=code)
    assert requests == []


# ── search_flights, one way, real API answers ───────────────────────────────

def test_one_way_summary_uses_local_times_and_shows_stops(make_client):
    client, requests = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20")
    params = requests[0].url.params
    assert (params["origin"], params["destination"], params["date"], params["adults"]) == ("TLV", "NRT+", "2027-01-20", "1")
    assert "return_date" not in params
    # 5 offers sent, one is the same trip sold twice, so 4; two airline groups.
    assert text.startswith(
        "4 offers from 2 airlines for TLV -> NRT+ on 2027-01-20 (one way), 1 adult(s). Price range: 2,580 ILS to 2,802 ILS."
    )
    first = group_section(text, 1)
    assert first.startswith("Airline 1: Aegean Airlines + Qatar Airways (A3 + QR), 1 offer")
    assert "cheapest and fastest: 2,580 ILS" in first
    # Local clock times exactly as sent (05:20 +02:00 -> 11:55 +09:00), never converted; +1 day.
    assert "2027-01-20 05:20" in first and "2027-01-21 11:55 (+1 day)" in first
    assert "2 stops" in first and "stop at" in first and "layover" in first
    assert "checked bags: 25 KG" in first
    assert "deep_link: https://example.test/book/" in first


def test_layover_is_computed_across_timezones(make_client):
    client, _ = make_client(flights_handler)
    second = group_section(tools.search_flights(client, "TLV", "NRT+", "2027-01-20"), 2)
    # Etihad's fastest = 14h15m: TLV 14:25 (+02:00) -> AUH -> NRT 11:40 (+09:00) next day.
    fastest = "fastest:" + second.split("fastest:")[1]
    assert "fastest: 2,802 ILS" in fastest and "14h 15m total" in fastest and "layover 1h 40m" in fastest
    assert "cheapest: 2,769 ILS" in second


def test_unknown_bags_are_not_reported_as_no_bag(make_client):
    offers = {"results": [make_offer("unknown-bags", 2500, 900, EY, bags=None), make_offer("none", 2600, 800, EY)]}
    client, _ = make_client(lambda r: json_response(offers))
    section = group_section(tools.search_flights(client, "TLV", "OSA", "2027-05-10"), 1)
    cheapest, fastest = section.split("fastest:")
    assert "checked bags: unknown" in cheapest and "no checked bag" not in cheapest
    assert "checked bags: no checked bag included" in fastest


def test_empty_bag_list_means_none_included():
    from brisa_mcp.summary import fmt_bags

    assert fmt_bags([]) == "no checked bag included"
    assert fmt_bags(None) == "unknown"
    # Seen on the real API: a zero allowance is how a fare without a bag is reported.
    assert fmt_bags([{"type": "piece", "quantity": 0, "weight_amount": None, "weight_unit": None, "applicable_legs": [1]}]) == "no checked bag included"
    assert fmt_bags([{"type": "piece", "quantity": 1, "weight_amount": 23, "weight_unit": "KG"}]) == "1 piece(s) of 23 KG each"


@pytest.mark.parametrize("kwargs, message", [
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
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", return_date="2027-01-30", adults=2, airlines=1)
    assert requests[0].url.params["return_date"] == "2027-01-30" and requests[0].url.params["adults"] == "2"
    assert "returning 2027-01-30" in text and "2 adult(s)" in text
    first = group_section(text, 1)
    assert first.startswith("Airline 1: Aegean Airlines + Qatar Airways + Cyprus Airways (A3 + QR + CY), 2 offers")
    assert "cheapest and fastest: 4,340 ILS round trip total" in first
    assert "Outbound:" in first and "Return:" in first
    assert first.count("checked bags:") == 2
    assert first.count("deep_link:") == 1
    assert "(+1 day)" in first  # TLV -> NRT lands the next local day
    assert text.splitlines()[-1] == "1 more airline: Etihad Airways"


def test_round_trip_header_counts_pairs_airlines_and_price_range(make_client):
    client, _ = make_client(flights_handler)
    text = tools.search_flights(client, "TLV", "NRT+", "2027-01-20", return_date="2027-01-30")
    assert text.startswith("3 offers from 2 airlines for TLV -> NRT+ on 2027-01-20, returning 2027-01-30")
    assert "Price range: 4,340 ILS to 4,693 ILS" in text
    # Same airlines in both directions: the two Aegean + Qatar + Cyprus pairs form one group.
    assert group_titles(text)[0].endswith("2 offers")


# ── search_multi_city ───────────────────────────────────────────────────────

LEGS = [
    {"origin": "TLV", "destination": "NRT+", "date": "2027-01-20"},
    {"origin": "TYO", "destination": "SEL", "date": "2027-01-27"},
]


def test_multi_city_one_search_per_leg_and_combined_total(make_client):
    client, requests = make_client(flights_handler)
    text = tools.search_multi_city(client, LEGS, adults=1, airlines=1)
    assert [r.url.params["origin"] for r in requests] == ["TLV", "TYO"]
    assert all("return_date" not in r.url.params for r in requests)  # one way per leg
    assert "Leg 1: TLV -> NRT+ on 2027-01-20 (one way): 4 offers from 2 airlines, price range 2,580 ILS to 2,802 ILS." in text
    assert "Leg 2: TYO -> SEL" in text
    assert text.count("1 more airline: Etihad Airways") == 2
    assert "Cheapest combined total: 5,160 ILS" in text  # 2 x 2,580
    assert "separate one-way ticket" in text
    assert text.count("deep_link:") == 2  # one airline per leg, and its cheapest is also its fastest


def test_multi_city_shows_the_airline_view_for_every_leg(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_multi_city(client, LEGS)
    legs = text.split("Leg 2:")
    assert len(group_titles(legs[0])) == 4 and len(group_titles(legs[1])) == 4
    assert text.count("2 more airlines: Turkish Airlines, Air India") == 2


def test_multi_city_airline_filter_applies_to_one_leg(make_client):
    client, _ = make_client(mix_handler)
    legs = [{**LEGS[0], "airline": "AI"}, LEGS[1]]
    text = tools.search_multi_city(client, legs)
    leg1, leg2 = text.split("Leg 2:")
    assert "Air India (AI): 2 of 12 offers include it" in leg1 and "Airline 1:" not in leg1
    assert book_ids(leg1) == ["AI-cheap", "AI-fast"]
    assert "Airline 1: Etihad Airways (EY), 5 offers" in leg2  # the other leg is unfiltered
    # AI's cheapest (3,100) on leg 1 + the overall cheapest (2,400) on leg 2.
    assert "Cheapest combined total: 5,500 ILS" in text and "airline filter" in text


def test_multi_city_airline_without_offers_leaves_no_total(make_client):
    client, _ = make_client(mix_handler)
    text = tools.search_multi_city(client, [{**LEGS[0], "airline": "BA"}, LEGS[1]])
    assert "No offer includes airline BA." in text
    assert "Cheapest combined total: unavailable" in text


def test_multi_city_bad_airline_code_names_the_leg(make_client):
    client, requests = make_client(mix_handler)
    with pytest.raises(BrisaError, match="leg 2: airline must be a 2-character IATA airline code"):
        tools.search_multi_city(client, [LEGS[0], {**LEGS[1], "airline": "AIR"}])
    assert len(requests) == 1  # leg 1 was searched, leg 2 never was


@pytest.mark.parametrize("airlines", [0, 9])
def test_multi_city_airlines_out_of_range(make_client, airlines):
    client, requests = make_client(mix_handler)
    with pytest.raises(BrisaError, match="airlines must be between 1 and 8"):
        tools.search_multi_city(client, LEGS, airlines=airlines)
    assert requests == []


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


def test_search_tools_describe_the_airline_format_and_take_no_sort_or_limit(make_client):
    client, _ = make_client(flights_handler)
    listed = {t.name: t for t in asyncio.run(build_server(client).list_tools())}
    flights, multi = listed["search_flights"], listed["search_multi_city"]
    assert set(flights.inputSchema["properties"]) == {
        "origin", "destination", "date", "return_date", "adults", "airlines", "airline"
    }
    assert set(multi.inputSchema["properties"]) == {"legs", "adults", "airlines"}
    for tool in (flights, multi):
        description = " ".join(tool.description.split())  # the docstring wraps lines
        assert "cheapest and fastest" in description
        assert "more airlines" in description and "IATA" in description
    assert '"airline"' in multi.description


def test_airlines_over_the_limit_reaches_the_model_as_a_clear_error(make_client):
    from mcp.server.fastmcp.exceptions import ToolError

    client, _ = make_client(mix_handler)
    args = {"origin": "TLV", "destination": "OSA", "date": "2027-05-10", "airlines": 9}
    with pytest.raises(ToolError, match="airlines must be between 1 and 8, got 9"):
        asyncio.run(build_server(client).call_tool("search_flights", args))


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
