"""FastMCP server (stdio). Run: python mcp/server.py  (see README for registration)."""
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from brisa_mcp import tools
from brisa_mcp.client import BrisaClient, BrisaError
from brisa_mcp.config import load_settings


def _run(fn, *args, **kwargs) -> str:
    # A BrisaError message is already written for the model; ToolError delivers it
    # as an error result without a stack trace.
    try:
        return fn(*args, **kwargs)
    except BrisaError as e:
        raise ToolError(str(e)) from None


def build_server(client: BrisaClient) -> FastMCP:
    server = FastMCP("brisa")

    @server.tool()
    def search_locations(keyword: str) -> str:
        """Find airports and cities by name, to get the code that search_flights needs.

        Call this FIRST whenever the user gives a city or airport name instead of a code
        (e.g. "Tokyo", "Heathrow"). Returns up to 8 matches, most travelled first, each with
        name, sub_type (CITY or AIRPORT), iata_code, search_code, city and country.
        Use the search_code of the match as origin/destination: a CITY code such as "TYO"
        searches all its airports; an AIRPORT code ends in "+", e.g. "NRT+" searches only Narita.
        """
        return _run(tools.search_locations, client, keyword)

    @server.tool()
    def search_flights(
        origin: str,
        destination: str,
        date: str,
        return_date: str | None = None,
        adults: int = 1,
        sort: str = "best",
        limit: int = 10,
    ) -> str:
        """Search priced flight offers for one way or a round trip and summarise the best ones.

        origin / destination: a search_code from search_locations ("TYO" = a whole city,
        "NRT+" = one airport). If the user gave a place name, call search_locations first.
        date / return_date: YYYY-MM-DD, today or later. Leave return_date empty for one way.
        adults: 1-9; prices are the total for all of them.
        sort: "best" (balances price, duration and stops; same ranking as the Brisa web app),
        "cheapest" or "fastest". limit: how many offers to show (max 20).

        Returns a header (how many offers exist and their price range) then, per offer: total
        price and currency, airlines, departure -> arrival in LOCAL airport time (+N days when it
        lands later), total duration, each stop with its airport and layover length, checked bags
        ("unknown" when the airline did not say; that is NOT "no bag") and a deep_link to the
        airline's booking page. A round trip is priced as one fare and shows both directions.
        Read-only: this tool cannot book anything; the user books through deep_link.
        """
        return _run(tools.search_flights, client, origin, destination, date, return_date, adults, sort, limit)

    @server.tool()
    def search_multi_city(legs: list[dict], adults: int = 1, limit: int = 3) -> str:
        """Price a multi-city trip as separate one-way searches, one per leg.

        legs: a list of 2-6 objects like {"origin": "TLV", "destination": "TYO", "date": "2027-05-10"};
        origin/destination are search_codes (see search_locations), date is YYYY-MM-DD.
        Returns the best `limit` offers of each leg and the cheapest combined total
        (the cheapest offer of every leg added up). The legs are SEPARATE tickets, not one
        itinerary: say so to the user (no protection on a missed connection between legs).
        """
        return _run(tools.search_multi_city, client, legs, adults, limit)

    @server.tool()
    def get_deals() -> str:
        """List the current flight deals the Brisa worker found (cheap round trips from its home airport).

        No arguments. Each deal has origin, destination, departure and return dates, price and
        airline. Deals are precomputed every few hours, so a price can be stale: confirm it with
        search_flights before telling the user it is available.
        """
        return _run(tools.get_deals, client)

    return server


def main() -> None:
    settings = load_settings()
    client = BrisaClient(settings.api_url, settings.timeout_seconds)
    build_server(client).run(transport="stdio")


if __name__ == "__main__":
    main()
