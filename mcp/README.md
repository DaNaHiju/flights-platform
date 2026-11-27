# Brisa MCP server

A local [Model Context Protocol](https://modelcontextprotocol.io) server that lets
Claude (Claude Code and the Claude desktop app) search flights **through the Brisa API**
of this repo (`services/api`). Claude asks for "flights from Tel Aviv to Tokyo in May";
the server calls `GET /flights`, `/locations` and `/deals` and hands back a short,
readable summary instead of the ~1 MB of raw offers.

It runs on your machine over stdio. There is no Docker image and nothing is deployed:
the client (Claude) starts it as a child process.

## Why it is read-only

Brisa does not sell tickets: each offer carries a `deep_link` to the airline's own
booking page (see "Scope: bookings are simulated" in
[docs/api-contract.md](../docs/api-contract.md)). An assistant that can write would be
able to record bookings with a passenger's personal data on the strength of a
misunderstood sentence. So the server exposes only searches (`GET`), has no booking tool,
and has no code path that sends anything but `GET`. The user books through the link.

## Tools

| Tool | What it does |
|---|---|
| `search_locations(keyword)` | Airports and cities matching a name, with the `search_code` to use as origin/destination. |
| `search_flights(origin, destination, date, return_date=None, adults=1, airlines=4, airline=None)` | Offers for one way, or a round trip with `return_date`, grouped by airline: the cheapest and the fastest offer of each of the first `airlines` airlines. `airline` (IATA code) shows only that airline. |
| `search_multi_city(legs, adults=1, airlines=4)` | One one-way search per leg, shown the same way, and the cheapest combined total. A leg may carry `"airline": "AI"`. The legs are separate tickets. |
| `get_deals()` | The current deals the worker found. |

### Output format

The API returns 70-170 offers per search, and one airline with many schedules (Etihad,
say) can fill any "top N". So the tools do not show a top-N list. Each search (each leg, for
`search_multi_city`) is shown like this:

```text
71 offers from 12 airlines, price range 2,580 ILS to 44,936 ILS.

Airline 1: Aegean Airlines + Qatar Airways (A3 + QR), 1 offer
cheapest and fastest: 2,580 ILS
   <times, duration, stops with layovers, checked bags, deep_link>

Airline 2: Etihad Airways (EY), 8 offers
cheapest: 3,100 ILS
   ...
fastest: 3,134 ILS
   ...

...up to `airlines` groups...

8 more airlines: ITA Airways, Etihad Airways + Korean Air, ...
```

- **Groups.** Offers are grouped by the airlines that fly them, in flight order. A mixed
  itinerary is its own group: "Aegean Airlines + Qatar Airways" is not counted under Qatar
  Airways. For a round trip the airlines of both directions are joined. The "N airlines" in
  the header counts groups.
- **Order.** Groups are ordered by their cheapest offer (ties: shorter trip, then name), and the
  first `airlines` are shown (default 4, between 1 and 8; anything else is rejected).
- **Two offers per group.** `cheapest` is the lowest price (ties: shorter trip). `fastest` is
  the shortest total duration (ties: lower price). When one offer is both, it is shown once as
  `cheapest and fastest`.
- **The rest.** The last line names the groups that did not fit, so the model knows they exist
  and can ask for them.
- **One airline.** `airline="AI"` (2-character IATA code, any case) answers "and Air India?": it
  returns the cheapest and the fastest offer among all offers where that airline flies at least
  one flight, alone or in a mixed itinerary, even if it is not in the top. If it flies nothing
  in the results, the answer lists the airlines that do. In `search_multi_city` the filter is
  set per leg, and for the combined total that leg counts the filtered airline's cheapest offer.

There is no `sort` or `limit`: the old `best` ranking and the top-N list are gone, because
they are what let one airline take the whole answer.

Notes for reading the output:

- Times are **local to each airport**, as the API sends them; nothing is converted to your timezone. `(+1 day)` means it lands the next local day.
- `checked bags: unknown` means the airline did not say. It is not "no bag".
- Offers with the same flights are collapsed to the cheapest, like the web app does (`dedupe` in `services/web/src/results.ts`).

## Install

Python 3.12.

```bash
python3 -m venv mcp/.venv
mcp/.venv/bin/pip install -r mcp/requirements.txt
```

`requirements.txt` pins `mcp` (the official Python SDK, which provides `FastMCP`) and
`httpx`. The SDK is pinned to 1.x because 2.x renamed `FastMCP` to `MCPServer`.

## Configuration

| Variable | Default | |
|---|---|---|
| `BRISA_API_URL` | `http://10.100.102.12/api` | Base URL of the Brisa API (staging, behind nginx). |
| `BRISA_TIMEOUT_SECONDS` | `40` | Read timeout. A live search can take a while (the API itself waits up to 25 s on the provider). |

If the API cannot be reached, tools answer `Brisa API not reachable at <url>`. API errors
(400, 422, 502, 503) are turned into a one-line explanation for the model, never a stack trace.

## Register it

Use absolute paths: Claude starts the server from its own working directory.

### Claude Code

```bash
claude mcp add brisa -e BRISA_API_URL=http://10.100.102.12/api -- \
  /ABSOLUTE/PATH/TO/flights-platform/mcp/.venv/bin/python \
  /ABSOLUTE/PATH/TO/flights-platform/mcp/server.py
```

Then run `claude mcp list` (it should show `brisa` as connected) or `/mcp` inside a session.
Add `--scope user` to make it available in every project.

### Claude desktop app

Edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`) and restart the app:

```json
{
  "mcpServers": {
    "brisa": {
      "command": "/ABSOLUTE/PATH/TO/flights-platform/mcp/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/TO/flights-platform/mcp/server.py"],
      "env": { "BRISA_API_URL": "http://10.100.102.12/api" }
    }
  }
}
```

On Windows the interpreter is `mcp\.venv\Scripts\python.exe`.

## Example requests

- "Find me flights from Tel Aviv to Tokyo in May, leaving around the 10th and coming back around the 24th. Show me the cheapest and the fastest of each airline."
- "And what does Air India have for that same flight?"
- "I want to go TLV → Rome on 2027-03-04, Rome → Paris on 2027-03-08 and Paris → TLV on 2027-03-12. What is the cheapest way to do it?"
- "What flight deals are there right now? Is the cheapest one still available this week?"

Claude will call `search_locations` first when you give a city name, then `search_flights`
(or `search_multi_city` / `get_deals`).

## Develop

```bash
cd mcp
.venv/bin/pip install -r requirements-dev.txt ruff==0.17.2
.venv/bin/ruff check .
.venv/bin/pytest -q
```

Tests use `httpx.MockTransport` with answers trimmed from the real API
(`tests/fixtures/`); they never touch the network. CI runs lint and tests for `mcp/`
only when it changes (job `mcp` in `.github/workflows/ci.yml`).
