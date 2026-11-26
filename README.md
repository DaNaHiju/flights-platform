# flights-platform

Flight search and booking platform: a FastAPI API, a deals worker and a React
frontend, with live flight data from the **Amadeus Travel Builder APIs**.
This repo holds application code, tests, Dockerfiles and CI only.

| Repo | Contents |
|------|----------|
| **flights-platform** (this one) | `flights-api`, `flights-worker`, `flights-web`, GitHub Actions CI |
| [flights-platform-manifests](https://github.com/danahiju/flights-platform-manifests) | Helm charts, ArgoCD Applications, ExternalSecrets (GitOps source of truth) |
| [flights-platform-infra](https://github.com/danahiju/flights-platform-infra) | Terraform (EKS, VPC, IAM, ECR, remote-state backend) |

---

## Architecture

```
 Browser
    │  GET /, GET /api/*            (same origin: no CORS, no key in the browser)
    ▼
 flights-web  (nginx, React build)
    │  /api/*  →  proxy_pass, prefix stripped
    ▼
 flights-api  (FastAPI) ─────────────── Redis ── search, offer, airline and
    │   │                                │        location caches
    │   └── PostgreSQL (bookings)        │
    │                                    │
    │  X-API-Key: $AMADEUS_API_KEY       │
    ▼                                    │
 Amadeus Travel Builder APIs             │
    • GET /api/v3/search/                 flight offers (one-way, round trip)
    • GET /v1/reference-data/airlines     airline code → name
    • GET /v1/reference-data/locations    airport / city typeahead
    ▲                                    │
    │                                    │
 flights-worker (CronJob, every 6 h) ────┘  writes deals:top, read by GET /deals
```

A search, step by step:

1. The user types "madr" in the destination box. `flights-web` waits 250 ms,
   then calls `GET /api/locations?keyword=madr`.
2. `flights-api` normalizes the keyword, answers from Redis if it has it, and
   otherwise asks Amadeus and caches the answer for a day.
3. The user picks *Adolfo Suarez Barajas (MAD)*. The form keeps its
   `search_code`, `MAD+` (the `+` pins that airport; a city pick sends `MAD`,
   covering every airport of the city).
4. `GET /api/flights?origin=TLV&destination=MAD%2B&date=...&adults=2` → `flights-api`
   checks the search cache, then calls Amadeus flight search, resolves every
   airline code to a name in one batched (and cached) lookup, and returns
   provider-neutral offers: price, carriers, local times, duration, stops, the
   checked bags included in the fare (`null` when the airline did not say) and
   the airline **deep link**.
5. "Book" opens the deep link: the purchase happens on the airline's own site.

The form's **Travelers** menu (1–9) is sent as `adults`. Every price is the
total for all travelers, and the rows say so ("total for 2 travelers"). A
deal's "See flights" always searches for one traveler, which is what its price
covers.

Everything after step 4 happens in the browser, on the offers already returned
(no extra API calls). Each step's list can be sorted with the tabs (Best,
Cheapest, Fastest) or the **Sort by** menu: Best, Price, Duration, Departure
time, Arrival time and Stops. Price and Duration are the Cheapest and Fastest
tabs, so both controls always agree. Departure and arrival are the **local**
clock time of the API's string, never converted, of the flight that step shows
(the return flight in the return step). Stops puts nonstop first and breaks ties
by price.

The same lists can be **filtered**, again without calling the API: a panel on
the left (the "Filters" button on a phone) with Stops (Nonstop / 1 / 2+, each
with its count), Airlines, Departure time (local: Morning 05–12, Afternoon
12–18, Evening 18–24, Night 00–05), Max price and Max duration, plus "Clear
filters" and "Showing N of M". Inside a group (say, two airlines) an offer needs
to match any ticked box; across groups it needs to match all of them. Filters
apply to the flight each step shows, so in the return step they look at the
return flight. Sorting and "Show more" work on the filtered list.

### Layout

```
shared/                       Code shared by api and worker (imported as shared.*)
├── providers/
│   ├── base.py               FlightProvider protocol + provider errors
│   ├── amadeus.py            Amadeus client (HTTP) + provider (parsing, lookups)
│   └── __init__.py           get_provider(): picks the implementation
├── schemas.py                Provider-neutral models: FlightOffer, Leg, RoundTripOffer, Location, Deal
├── airports.py               Offline airport name/city/country (airportsdata)
├── cache.py                  Redis JSON helpers (strict and best-effort variants)
└── config.py                 Shared settings, require_env()
services/
├── api/                      FastAPI: /flights, /locations, /deals, /bookings, probes, /metrics
├── worker/                   refresh_deals: cheapest round trip per popular route → Redis
└── web/                      React + Vite, served by nginx-unprivileged
docs/api-contract.md          Endpoints, schemas, env vars, error codes
```

---

## Why Amadeus

The previous source, `fli`, reverse-engineered an internal Google Flights
endpoint: no API key, but also no contract, no SLA, and it broke silently
(it returned `None` instead of failing). Amadeus Travel Builder is a documented,
versioned API with an API key, explicit rate limits, documented error codes,
and airline deep links that turn "Book" into a real booking page.

### The provider abstraction

Nothing outside `shared/providers/` knows which provider is in use:

- **`FlightProvider`** (`shared/providers/base.py`) is the interface:
  `search_one_way`, `search_round_trip`, `search_locations`.
- Every provider returns the models in `shared/schemas.py`, never its own wire
  format. The API, the cache, the bookings table and the frontend only see those.
- Every provider maps its failures onto four errors, and the API maps each one
  to a single HTTP answer (`services/api/app/api/errors.py`):

  | Provider error | HTTP | `error` |
  |---|---|---|
  | `ProviderUnavailableError` (timeout, 5xx, rejected key) | 502 | `provider_unavailable` |
  | `ProviderRateLimitedError` | 503 + `Retry-After` | `provider_rate_limited` |
  | `ProviderNotConfiguredError` (no key) | 503 | `provider_not_configured` |
  | `ProviderBadRequestError` | 400 | `invalid_search` |

- `FLIGHTS_PROVIDER` selects the implementation in `get_provider()`. Adding a
  provider = one new module implementing the protocol + one branch there.
- The search cache key includes the provider name, so a switch never serves
  one provider's offers as another's.

---

## How the Amadeus API key is provisioned

The key exists **only in the backend process environment**: never in the
frontend bundle, the image, the code, or Git.

```
 (homelab) kubectl-created Secret        (EKS, not wired yet) AWS Secrets Manager
 external-secrets/flights-amadeus                  │
           │  ClusterSecretStore homelab-secrets   │  ClusterSecretStore aws-secrets-manager
           ▼                                       ▼
 ExternalSecret staging/flights-api-staging-amadeus   (manifests repo, staging only)
           │
           ▼
 Secret flights-api-staging-amadeus  { AMADEUS_API_KEY }
           │                                   │
           ▼  envFrom (optional)               ▼  secretKeyRef (optional)
     flights-api pods                   flights-worker Job
```

- Get a key: request access through the Amadeus Travel Builder access form
  (https://eu1.ironcladapp.com/public-launch/6aaa463f6f95614fe0f6db9d).
- Store it on the homelab: see "Bootstrap: homelab source secrets" in the
  manifests repo's `CLAUDE.md` (one `kubectl create secret` fed from stdin).
- Without a key the services still start; searches answer 503
  `provider_not_configured` and the worker keeps the previous deals.
- The browser only calls `/api/*` on its own origin; it never talks to Amadeus.

---

## Caching strategy

Redis sits in front of every Amadeus call. Reference data changes rarely and is
cached long; prices are live and are cached briefly.

| Key | Content | TTL (env var, default) | Why |
|---|---|---|---|
| `search:{provider}:{o}:{d}:{date}:{adults}:{currency}[:rt:{ret}]` | full search response | `SEARCH_CACHE_TTL`, 600 s | identical searches within 10 min cost no quota |
| `offer:{offer_id}` | one one-way offer | `OFFER_CACHE_TTL`, 600 s | lets `POST /bookings` find the offer the user saw |
| `airline:{code}` | airline display name (unknown codes too) | `AIRLINES_CACHE_TTL`, 7 days | one batched lookup per new code, then free |
| `locations:{keyword}` | typeahead results | `LOCATIONS_CACHE_TTL`, 1 day | popular prefixes ("lon", "mad") are answered from Redis |
| `deals:top` | worker output | `DEALS_CACHE_TTL`, 7 h | outlives the 6 h CronJob interval |

Also part of the strategy:

- The typeahead is debounced (250 ms) and skips keywords under 2 characters.
- Errors and empty results are never cached: a merchant that failed looks like "no offers", and caching that would keep answering "no flights" after the provider recovers.
- Redis being down makes searches slower (cache misses), not failing.
- Retries are bounded: one retry after a 5xx, one inline wait after a 429 only
  if `Retry-After` ≤ 2 s; timeouts are not retried. Otherwise the client gets
  503 + `Retry-After`.
- Search results are capped with `AMADEUS_MAX_RESULTS_PER_MERCHANT` (20).

---

## Running locally

Prerequisites: Python 3.12, Node 22, Docker 24+.

```bash
git clone https://github.com/danahiju/flights-platform.git
cd flights-platform

# The key comes from your shell, never from a file in the repo.
read -rs AMADEUS_API_KEY && export AMADEUS_API_KEY

# api + worker + PostgreSQL + Redis (compose passes AMADEUS_API_KEY through)
docker-compose up --build
# API: http://localhost:8000   docs: http://localhost:8000/docs

# Frontend dev server (proxies /api to localhost:8000)
cd services/web && npm ci && npm run dev
```

Without `AMADEUS_API_KEY` everything starts; flight and location searches
answer 503 `provider_not_configured`.

### Tests and lint

The suites never reach Amadeus: the gateway is an `httpx.MockTransport` with
canned responses (`services/api/tests/amadeus_fixtures.py`) and Redis is an
in-memory fake. Conftest removes `AMADEUS_API_KEY` from the environment.

```bash
pip install -r services/api/requirements-dev.txt -r services/worker/requirements-dev.txt ruff==0.17.2
ruff check services/api services/worker shared
pytest -q services/api      # one run per service: both have a `tests` package
pytest -q services/worker
cd services/web && npm ci && npm run lint && npm test
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (Postgres + Redis) |
| GET | `/metrics` | Prometheus metrics (`provider_errors_total{provider,reason}` among them) |
| GET | `/flights?origin=&destination=&date=&adults=&return_date=` | Live offers; one-way, or round trip with `return_date` |
| GET | `/locations?keyword=` | Airport/city typeahead |
| GET | `/deals?limit=` | Top cached deals from `FLIGHTS_DEFAULT_ORIGIN` |
| POST | `/bookings` | Record a booking against an offer returned by `/flights` |
| GET | `/bookings/{id}` | Get a booking |

Full schemas and error codes: [docs/api-contract.md](docs/api-contract.md).

---

## CI/CD

GitHub Flow: short-lived branches, PRs into `main`, ruleset `protect-main`
requires the `ci-ok` check. CI (`.github/workflows/ci.yml`) builds only the
services a change touches (`dorny/paths-filter`): lint → test → image build →
Trivy → push to GHCR on `main` → a GitHub App bumps the image tag in the
manifests repo → ArgoCD syncs staging.

---

## Not done yet

- **Production / EKS key wiring**: the Amadeus ExternalSecret exists for
  staging only. Production and EKS need the key in AWS Secrets Manager and the
  `amadeus` block enabled in their values; production is synced manually.
- **Multi-city as one Amadeus call**: the frontend still runs multi-city as two
  independent one-way searches (two tickets). Amadeus supports multi-city
  natively (up to 6 bounds) with one fare.
- **Key rotation without restart**: `envFrom` is read at container start, so a
  rotated key needs a pod restart (no Reloader in the cluster).
- **Circuit breaker**: repeated Amadeus failures are retried per request; there
  is no shared breaker across pods.
- **Egress policy**: the mesh allows any outbound host; a `ServiceEntry` for
  `api.amadeus.com` plus `REGISTRY_ONLY` would tighten it.
- **Booking**: `POST /bookings` records intent only; the real purchase happens
  on the airline's site through the deep link.

### Future work

- **Watchlist**: track a route and notify when its price drops (replaces the
  simulated bookings flow). Not started.
