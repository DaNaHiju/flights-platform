API Contract — flights-platform
Status: draft. Written before implementation. Any change to this document must be reflected in the Helm chart (ConfigMap, Secret, Service, probes) and vice versa.


Provider decision. This contract originally assumed the Amadeus Self-Service API. Amadeus Self-Service closed on July 17, 2026. The data provider is now `fli` (PyPI package `flights`, github.com/punitarani/fli), a Python library that retrieves live data from Google Flights by reverse-engineering its internal endpoints. It requires no API key and no OAuth2 flow. Alternatives evaluated and discarded:
Amadeus Self-Service — discarded, portal closed July 17, 2026
Kiwi Tequila — discarded, access has been invite-only since 2026, no self-serve signup
Duffel — discarded, sandbox only returns fabricated test data, not usable for real search results


1. Service identity
flights-api
Field
Value
Runtime
Python 3.12 / FastAPI
Container port
8000
Liveness
GET /health
Readiness
GET /ready
Metrics
GET /metrics (Prometheus text format)
Dependencies
PostgreSQL, Redis, Google Flights (via fli, no official API)


/health returns 200 while the process is alive. It must not check external dependencies — a failing liveness probe restarts the pod, and wiring it to the database turns a transient Postgres blip into a cluster-wide restart cascade.

/ready checks PostgreSQL and Redis connectivity. A failing readiness probe removes the pod from the Service endpoints without restarting it.
flights-web
Field
Value
Runtime
Static build served by nginx
Container port
8080 (non-root nginx)
Liveness / Readiness
GET /
Runtime config
/config.js, mounted from a ConfigMap


The API base URL is not compiled into the bundle. It is read at runtime from /config.js, so the same image is promoted from staging to production unchanged.


2. Environment variables
flights-api
Variable
Source
Example
DB_HOST
ConfigMap
flights-postgres
DB_PORT
ConfigMap
5432
DB_NAME
ConfigMap
flights
DB_USER
Secret
flights_app
DB_PASSWORD
Secret
—
REDIS_URL
ConfigMap
redis://flights-redis:6379/0
FLIGHTS_CURRENCY
ConfigMap
USD
FLIGHTS_DEFAULT_ORIGIN
ConfigMap
TLV
ENVIRONMENT
ConfigMap
staging | production
LOG_LEVEL
ConfigMap
info
SEARCH_CACHE_TTL
ConfigMap
600
DEALS_CACHE_TTL
ConfigMap
7200


The database URL is split rather than stored as a single connection string, so that only the credentials live in the Secret and the rest stays readable in the ConfigMap. The application composes the DSN at startup.

fli requires no credentials, so there is no Secret for the data provider. DB_USER and DB_PASSWORD are the only Secrets left in this table.
flights-web
Variable
Source
Notes
API_BASE_URL
ConfigMap
Rendered into /config.js


3. Endpoints — flights-api
Operational
GET /health   → 200 {"status": "ok"}

GET /ready    → 200 {"postgres": "ok", "redis": "ok"}

              → 503 {"postgres": "ok", "redis": "unreachable"}

GET /metrics  → 200 Prometheus text format
FlightOffer schema
This is the subset of the fli response that flights-api exposes publicly — not fli's raw offer.
Field
Type
offer_id
string — opaque, the fli booking_token; passed back on POST /bookings
price
float
currency
string
duration_minutes
int
stops
int
primary_airline
string
legs
array of Leg (below)

Leg
Field
Type
airline
string
flight_number
string
departure_airport
string
arrival_airport
string
departure_datetime
string
arrival_datetime
string
duration_minutes
int

fli additionally returns amenities, legroom, co2_emissions, aircraft, and layovers on the offer and on each leg. These are excluded from the public response — they're Google Flights' own presentation detail and add noise to the booking use case, which only needs price, schedule, and airline identity to search and confirm a seat.
GET /flights
Search live offers. Served from Redis when the same query was made recently.

query: origin (IATA, 3 chars, required)

       destination (IATA, 3 chars, required)

       date (YYYY-MM-DD, required)

       adults (int, default 1)

200 → { "results": [FlightOffer], "cached": bool, "cached_at": timestamp|null }

400 → { "error": "invalid_iata_code" | "invalid_date_format" | "date_in_past" }

502 → { "error": "provider_unavailable" }
GET /deals
Top deals, always served from Redis. This endpoint never calls fli directly — the cache is populated out-of-band by the CronJob.

query: limit (int, default 10, max 50)

200 → { "deals": [Deal], "refreshed_at": timestamp }

503 → { "error": "deals_not_available" }   # cache empty, CronJob has not run yet
POST /bookings
Registers a booking against a previously returned offer.

body: { "offer_id": str,

        "passenger": { "first_name": str, "last_name": str, "date_of_birth": date },

        "contact_email": str }

201 → { "booking_id": uuid, "status": "confirmed", "snapshot": FlightOffer }

400 → { "error": "invalid_passenger_data" }

409 → { "error": "offer_expired" }

409 is the important case: fli booking tokens expire within minutes (exact window unverified, see open questions), and the platform does not own seat inventory. A booking records an intent with the offer data frozen at purchase time — it cannot guarantee the seat. This endpoint does not call fli — it only checks whether the offer is still sitting in the offer:{offer_id} cache written by GET /flights, so there is no provider_unavailable case here.
GET /bookings/{booking_id}
200 → Booking

404 → { "error": "booking_not_found" }


4. Data model
Only bookings are persisted. Flight data is never replicated into PostgreSQL — it is fetched via fli and cached in Redis.

CREATE TABLE bookings (

    id              UUID PRIMARY KEY,

    offer_id        TEXT        NOT NULL,

    offer_snapshot  JSONB       NOT NULL,

    passenger_name  TEXT        NOT NULL,

    contact_email   TEXT        NOT NULL,

    price_amount    NUMERIC(10,2) NOT NULL,

    price_currency  CHAR(3)     NOT NULL,

    status          TEXT        NOT NULL DEFAULT 'confirmed',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()

);

CREATE INDEX idx_bookings_email ON bookings (contact_email);

offer_snapshot stores the complete, untrimmed response returned by fli for that offer — not the trimmed FlightOffer shape described in section 3. Booking history stays readable even after the offer expires upstream, and the schema does not break when fli changes its response shape.


5. Caching strategy
Key
TTL
Written by
Read by
search:{origin}:{dest}:{date}:{adults}
SEARCH_CACHE_TTL
flights-api
flights-api
offer:{offer_id}
OFFER_CACHE_TTL (~10 min)
flights-api
flights-api
deals:top
DEALS_CACHE_TTL
CronJob
flights-api


Search results are cached, not just deals — otherwise every visitor query hits Google Flights directly through fli, which increases the chance of the reverse-engineered endpoint rate-limiting or blocking us. There is no OAuth2 token to cache — fli is unauthenticated.

Every offer returned by GET /flights is also cached individually under offer:{offer_id} (offer_id being fli's booking_token), separate from the search-result cache. POST /bookings checks this key rather than re-calling fli — a miss means the offer is treated as expired. Its TTL is the same "assumed 10 minutes" window from the open questions below; it is not refreshed by repeat searches or cache hits on search:*.

TTL values are provisional and must be reconciled against how much load fli's underlying endpoint actually tolerates. There is no official quota to reference, unlike Amadeus's free tier.


6. Open questions
Booking token validity window: unverified. Assumed 10 minutes for the 409 offer_expired error — pending verification against real usage
fli's departure_datetime / arrival_datetime values carry no timezone. Determine which timezone they represent before persisting them in Postgres
Provider risk: fli depends on an internal Google Flights endpoint that is not a documented public API and can change without notice. Needs to be documented in the repo README
Authentication: currently none. Bookings are identified by contact_email only
