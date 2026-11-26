# API Contract — flights-platform

Any change to this document must be reflected in the Helm charts (ConfigMap,
ExternalSecrets, Service, probes) of the manifests repo, and vice versa.

## Scope: bookings are simulated

The flight data provider sells nothing through this service. Each offer carries
a `deep_link` to the airline's own booking page, where the real purchase
happens. `POST /bookings` validates the payload, stores the offer snapshot and
returns an id: it records intent, it does not buy a ticket.

A real booking would span three systems with independent state — this service,
an inventory provider and a payment processor — with no transaction spanning
all three. It would need a hold-charge-confirm sequence with compensating
actions (a saga) and a status field on the booking. That is deliberately out
of scope.

## Provider decision

Flight data comes from the **Amadeus Travel Builder APIs** (API key in an
`X-API-Key` header), behind the `FlightProvider` interface in
`shared/providers/`. History:

- Amadeus Self-Service: closed on July 17, 2026.
- `fli` (PyPI `flights`): reverse-engineered Google Flights. Used until this
  change; dropped because it has no contract or SLA and failed silently.
- Kiwi Tequila: invite-only. Duffel: sandbox returns fabricated data.

---

## 1. Service identity

### flights-api

| Field | Value |
|---|---|
| Runtime | Python 3.12 / FastAPI |
| Container port | 8000 |
| Liveness | `GET /health` |
| Readiness | `GET /ready` |
| Metrics | `GET /metrics` (Prometheus text format) |
| Dependencies | PostgreSQL, Redis, Amadeus Travel Builder APIs |

`/health` returns 200 while the process is alive. It must not check external
dependencies: a failing liveness probe restarts the pod, and wiring it to a
dependency turns a transient blip into a restart cascade.

`/ready` checks PostgreSQL and Redis. It deliberately does **not** check
Amadeus: an upstream outage must degrade search to 502/503, not remove every
pod from the Service (bookings, deals and health would go down with it).

### flights-web

| Field | Value |
|---|---|
| Runtime | Static build served by nginx-unprivileged |
| Container port | 8080 |
| Liveness / Readiness | `GET /` |
| API access | same origin: nginx proxies `/api/*` to flights-api |

The browser never calls Amadeus and never sees the API key.

---

## 2. Environment variables

### flights-api and flights-worker

| Variable | Source | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | Secret (ExternalSecret template) | — required (api only) | see composition below |
| `REDIS_URL` | ConfigMap | — required | |
| `AMADEUS_API_KEY` | Secret (ExternalSecret `<release>-amadeus`) | unset | **secret**; optional: unset → searches answer 503 `provider_not_configured` |
| `AMADEUS_GATEWAY_URL` | ConfigMap | `https://api.amadeus.com` | |
| `AMADEUS_SEARCH_TIMEOUT_SECONDS` | ConfigMap | 25 | flight search read timeout |
| `AMADEUS_LOOKUP_TIMEOUT_SECONDS` | ConfigMap | 5 | airlines / locations read timeout |
| `AMADEUS_MAX_RESULTS_PER_MERCHANT` | ConfigMap | 20 | `number_of_results` per airline |
| `FLIGHTS_PROVIDER` | ConfigMap | `amadeus` | provider selector |
| `FLIGHTS_CURRENCY` | ConfigMap | `USD` | |
| `FLIGHTS_DEFAULT_ORIGIN` | ConfigMap | `TLV` | worker: origin of the deals |
| `SEARCH_CACHE_TTL` | ConfigMap | 600 | seconds |
| `OFFER_CACHE_TTL` | ConfigMap | 600 | seconds |
| `AIRLINES_CACHE_TTL` | ConfigMap | 604800 | seconds (7 days) |
| `LOCATIONS_CACHE_TTL` | ConfigMap | 86400 | seconds (1 day) |
| `DEALS_CACHE_TTL` | ConfigMap | 25200 | seconds; must exceed the 6 h CronJob interval |
| `DEALS_TRIP_LENGTH_DAYS` | ConfigMap | 7 | worker: days between a deal's outbound and return |
| `ENVIRONMENT`, `LOG_LEVEL` | ConfigMap | | |

**Required vs optional.** `DATABASE_URL` (api) and `REDIS_URL` (both) have no
default: if one is missing the service fails at import with one error naming
every missing variable (`require_env` in `shared/config.py`). `AMADEUS_API_KEY`
is optional on purpose: a missing key must degrade search, not crash-loop the
pod.

**DATABASE_URL composition.** The API consumes a single `DATABASE_URL`. The
ExternalSecret in the manifests repo builds it from `DB_USER` and `DB_PASSWORD`
(`spec.target.template`); those two keys are also in the Secret for the Bitnami
postgresql subchart (`auth.existingSecret`). The password must not contain
URL-reserved characters (`@ : / # ? [ ]`); it is not percent-encoded.

**Amadeus key.** A separate ExternalSecret writes `<release>-amadeus` with the
single key `AMADEUS_API_KEY`. flights-api mounts it with `envFrom` (optional);
flights-worker reads it with `secretKeyRef` (optional). Homelab source: a Secret
created by hand in `external-secrets` (store `homelab-secrets`); see the
manifests repo `CLAUDE.md`.

---

## 3. Endpoints — flights-api

Error bodies are flat: `{"error": "<code>"}`.

### Operational

```
GET /health   → 200 {"status": "ok"}
GET /ready    → 200 {"postgres": "ok", "redis": "ok"}
              → 503 {"postgres": "ok", "redis": "unreachable"}
GET /metrics  → 200 Prometheus text format
```

`provider_errors_total{provider, reason}` counts provider failures; `reason` is
`unavailable`, `rate_limited`, `not_configured` or `bad_request`.

### Provider errors (every endpoint that calls the provider)

| Status | Body | Cause |
|---|---|---|
| 400 | `{"error": "invalid_search"}` | the provider rejected the parameters |
| 502 | `{"error": "provider_unavailable"}` | timeout, network error, upstream 5xx, rejected API key |
| 503 | `{"error": "provider_rate_limited"}` + `Retry-After` | quota for our key exhausted |
| 503 | `{"error": "provider_not_configured"}` | no `AMADEUS_API_KEY` |

### FlightOffer

| Field | Type | Notes |
|---|---|---|
| `offer_id` | string | stable hash of the itinerary and price; passed back to `POST /bookings` |
| `price` | float | total of the whole offer (for a round trip, of the pair) |
| `currency` | string | ISO 4217 |
| `duration_minutes` | int | first departure → last arrival, layovers included, computed from the timestamps with their offsets |
| `total_duration_minutes` | int | same value, named for what it is |
| `stops` | int | connections (flights − 1) |
| `primary_airline` | string | name of the first flight's airline |
| `primary_airline_code` | string\|null | its IATA code |
| `carriers` | [string] | every distinct airline name, in flight order |
| `merchant` | string\|null | IATA code of the airline selling the offer |
| `deep_link` | string\|null | airline booking page; absent on some offers — show the offer without a link |
| `legs` | [Leg] | |

### Leg

| Field | Type | Notes |
|---|---|---|
| `airline` | string | resolved name (falls back to the code) |
| `airline_code` | string\|null | marketing carrier IATA code |
| `flight_number` | string | carrier + number, e.g. `BA322` |
| `operating_airline` | string\|null | set only when another airline operates it |
| `departure_airport`, `arrival_airport` | string | airport name (airportsdata), or the code |
| `departure_datetime`, `arrival_datetime` | string | **local time at that airport with its UTC offset**, as sent by Amadeus. Display as is; never convert to the viewer's timezone |
| `duration_minutes` | int | this flight |
| `departure_airport_code`, `arrival_airport_code` | string\|null | IATA |
| `departure_city`, `arrival_city` | string\|null | airportsdata |
| `departure_country_code`, `arrival_country_code` | string\|null | ISO 3166-1 alpha-2 |

### GET /flights

```
query: origin       3-letter airport or city code, optional trailing "+" (required)
       destination  same format (required)
       date         YYYY-MM-DD, today or later (required)
       adults       int 1-9, default 1
       return_date  YYYY-MM-DD, not before date (optional → round trip)

200 → { "results": [FlightOffer], "cached": bool, "cached_at": timestamp|null }
      with return_date: { "results": [RoundTripOffer], ... }

400 → { "error": "invalid_iata_code" | "same_origin_and_destination"
                 | "invalid_date_format" | "date_in_past" | "return_before_departure" }
```

`LON` searches every London airport; `LHR+` searches Heathrow only. Results are
sorted by price, cheapest first.

```
RoundTripOffer: { "price": float,          # one fare for the pair
                  "currency": string,
                  "merchant": string|null,
                  "deep_link": string|null,
                  "outbound": FlightOffer,
                  "return": FlightOffer }  # each carries the pair's price
```

Round trip offers are not registered for `POST /bookings`.

### GET /locations

```
query: keyword  1-60 chars (required). Normalized server-side: text before the
                first comma, transliterated to ASCII, other characters
                replaced by spaces, 30 chars max. Under 2 usable characters
                returns [] without calling the provider.

200 → { "results": [Location] }   # most travelled first, max 8
422 → keyword missing
```

`Location`: `id` (`AMAD` / `CMAD`: unique, unlike `iata_code`), `iata_code`,
`sub_type` (`AIRPORT` | `CITY`), `name`, `detailed_name`, `city_name`,
`city_code`, `country_name`, `country_code`, and `search_code`: the value to
send as origin/destination (`MAD+` for an airport, `MAD` for a city).

### GET /deals

Always served from Redis; never calls the provider (the CronJob fills it).

```
query: limit (int, default 10, max 50)
200 → { "deals": [Deal], "refreshed_at": timestamp }
503 → { "error": "deals_not_available" }   # cache empty, CronJob has not run yet
```

Deals carry no `deep_link`: prices are live and a deal can be hours old.

```
Deal: { "destination": "MAD",          # code; the origin is FLIGHTS_DEFAULT_ORIGIN
        "departure_date": "2099-01-12",
        "return_date": "2099-01-19"|null,   # null / absent = one-way deal
        "price": float,                # round trip: total of the cheapest pair
        "currency": string,
        "airline": string,             # the outbound flight's airline
        "total_duration_minutes": int|null,   # the outbound flight's
        ...origin_* and destination_* names, cities and country codes }
```

The worker searches one **round trip** per popular destination (one provider
call each): outbound is today + 30 days, return is outbound +
`DEALS_TRIP_LENGTH_DAYS`. `price` is the pair's total, so a deal reads "from X ·
round trip". Same `deals:top` key as before: deals written by an older worker
have no `return_date` and are one-way deals, still valid until the next run
replaces them.

### POST /bookings

```
body: { "offer_id": str,
        "passenger": { "first_name": str, "last_name": str, "date_of_birth": date },
        "contact_email": str }

201 → { "booking_id": uuid, "status": "recorded", "snapshot": FlightOffer }
400 → { "error": "invalid_passenger_data" }
409 → { "error": "offer_expired" }
```

The endpoint does not call the provider: it requires the offer to still be in
`offer:{offer_id}` (written by `GET /flights`). A miss, or an entry cached by an
older release in another shape, is `409 offer_expired`.

### GET /bookings/{booking_id}

```
200 → Booking
404 → { "error": "booking_not_found" }
```

---

## 4. Data model

Only bookings are persisted. Flight data is never replicated into PostgreSQL.

```sql
CREATE TABLE bookings (
    id              UUID PRIMARY KEY,
    offer_id        TEXT          NOT NULL,
    offer_snapshot  JSONB         NOT NULL,
    passenger_name  TEXT          NOT NULL,
    contact_email   TEXT          NOT NULL,
    price_amount    NUMERIC(10,2) NOT NULL,
    price_currency  CHAR(3)       NOT NULL,
    status          TEXT          NOT NULL DEFAULT 'recorded',
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_bookings_email ON bookings (contact_email);
```

`offer_snapshot` stores the offer exactly as `GET /flights` returned it (the
FlightOffer shape, `deep_link` included), so booking history stays readable
after the offer is gone upstream. Snapshots written before the Amadeus change
hold the old fli shape; readers must not assume one shape for every row.

---

## 5. Caching strategy

| Key | TTL | Written by | Read by |
|---|---|---|---|
| `search:{provider}:{origin}:{dest}:{date}:{adults}:{currency}[:rt:{return}]` | `SEARCH_CACHE_TTL` | flights-api | flights-api |
| `offer:{offer_id}` | `OFFER_CACHE_TTL` | flights-api | flights-api (bookings) |
| `airline:{code}` | `AIRLINES_CACHE_TTL` | provider (api, worker) | provider |
| `locations:{keyword}` | `LOCATIONS_CACHE_TTL` | provider (api) | provider |
| `deals:top` | `DEALS_CACHE_TTL` | worker | flights-api |

- Searches are cached so repeated queries do not spend Amadeus quota.
- Airline names are resolved in one batched lookup per search for the codes not
  yet cached; unknown codes are cached as the code so they are not looked up again.
- Errors are never cached; empty results are.
- Search, airline and location caches are best-effort: Redis being down turns
  them into misses (logged), not failures. `offer:*` stays strict: bookings must
  not silently treat a Redis outage as "offer expired".
- Retries: one after a 5xx; one inline wait after a 429 only when
  `Retry-After` ≤ 2 s; timeouts are not retried.

---

## 6. Open questions

- Amadeus quota for the key: confirm the actual rate limit and size the TTLs
  and the typeahead debounce against it.
- Deep link validity: how long an offer's `deep_link` stays bookable.
  `OFFER_CACHE_TTL` (10 min) is an assumption.
- Authentication: none. Bookings are identified by `contact_email` only.
