API Contract — flights-platform
Status: draft. Written before implementation. Any change to this document must be reflected in the Helm chart (ConfigMap, Secret, Service, probes) and vice versa.

## Scope: bookings are simulated

fli reads data from Google Flights; it does not sell tickets. This
service has no payment processor and no airline inventory integration,
so POST /bookings does not purchase anything: it validates the payload,
stores the offer snapshot and returns an id.

A real booking would span three systems with independent state — this
service, an inventory provider (Amadeus, Sabre, Duffel) and a payment
processor — with no transaction spanning all three. It would need a
hold-charge-confirm sequence with compensating actions (a saga) and a
status field on the booking. That is deliberately out of scope.

The offer_snapshot column is not affected by this: storing the exact
offer as shown at booking time is what a real system does too, because
the upstream price changes between display and confirmation.


Provider decision. This contract originally assumed the Amadeus Self-Service API. Amadeus Self-Service closed on July 17, 2026. The data provider is now `fli` (PyPI package `flights`, github.com/punitarani/fli), a Python library that retrieves live data from Google Flights by reverse-engineering its internal endpoints. It requires no API key and no OAuth2 flow. Alternatives evaluated and discarded:
Amadeus Self-Service — discarded, portal closed July 17, 2026
Kiwi Tequila — discarded, access has been invite-only since 2026, no self-serve signup
Duffel — discarded, sandbox only returns fabricated test data, not usable for real search results


1. Service identity
flights-api
Field
Value
Runtime
Python 3.11 / FastAPI
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
DATABASE_URL
Secret (composed by the ExternalSecret, see below)
postgresql://<credentials>@flights-postgres:5432/flights
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
OFFER_CACHE_TTL
ConfigMap
600


DATABASE_URL composition. The API consumes a single DATABASE_URL, exactly as given (services/api/app/config.py). It does not read separate DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD variables and it does not build the DSN itself. The composition happens in the ExternalSecret (flights-platform-manifests repo), not in the app: its spec.target.template builds DATABASE_URL from the individual credential keys stored in AWS Secrets Manager. The names of those keys are not literals: they are the Helm values externalSecrets.remoteKeys.dbUser and externalSecrets.remoteKeys.dbPassword. Locally, docker-compose.yml sets DATABASE_URL directly. Because the URL embeds the credentials, the whole string lives in the Secret; host, port and database name are not separately readable from a ConfigMap.

The Kubernetes Secret the pod receives has three keys: DATABASE_URL (composed by the ExternalSecret template), and DB_USER and DB_PASSWORD as separate keys. flights-api reads only DATABASE_URL; DB_USER and DB_PASSWORD are consumed by the Bitnami postgresql subchart through auth.existingSecret.

Password constraint. DATABASE_URL is a URI, so the PostgreSQL password must not contain URL-reserved characters: @ : / # ? [ ]. Terraform must generate the password with override_special excluding them. The password is not percent-encoded when DATABASE_URL is composed, because encoding a password that is already correct would double-encode it. This is marked TODO(terraform) in the chart.

DATABASE_URL and REDIS_URL are required and have no default in the code. If one is missing, the service fails at import with an error naming the missing variable(s), instead of falling back to localhost and failing later on a connection error. REDIS_URL is required by both services, DATABASE_URL only by the API. Each service checks its complete list in a single call at startup (services/api/app/config.py, services/worker/worker/config.py, using require_env from shared/config.py), so when several are missing one error names them all. The worker does not read DATABASE_URL and runs without it.

fli requires no credentials, so there is no Secret for the data provider. All three Secret keys above are PostgreSQL credentials.
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

fli additionally returns amenities, legroom, co2_emissions, aircraft, and layovers on the offer and on each leg. These are excluded from the public response — they're Google Flights' own presentation detail and add noise to the booking use case, which only needs price, schedule, and airline identity to search offers and record a booking.
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

201 → { "booking_id": uuid, "status": "recorded", "snapshot": FlightOffer }

400 → { "error": "invalid_passenger_data" }

409 → { "error": "offer_expired" }

409 is the important case: fli booking tokens expire within minutes (exact window unverified, see open questions), and the platform does not own seat inventory. A booking records an intent with the offer data frozen at booking time — it cannot guarantee the seat. This endpoint does not call fli — it only checks whether the offer is still sitting in the offer:{offer_id} cache written by GET /flights, so there is no provider_unavailable case here.
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

    status          TEXT        NOT NULL DEFAULT 'recorded',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()

);

CREATE INDEX idx_bookings_email ON bookings (contact_email);

`recorded` means this service persisted the booking intent. It is the only value today; the remaining states (held, charged, confirmed, failed) belong to the real integration described in "Scope: bookings are simulated".

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
