API Contract — flights-platform
Status: draft. Written before implementation. Any change to this document must be reflected in the Helm chart (ConfigMap, Secret, Service, probes) and vice versa.


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
PostgreSQL, Redis, Amadeus Self-Service API


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
AMADEUS_CLIENT_ID
Secret
—
AMADEUS_CLIENT_SECRET
Secret
—
AMADEUS_BASE_URL
ConfigMap
https://test.api.amadeus.com
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
Top deals, always served from Redis. This endpoint never calls Amadeus — the cache is populated out-of-band by the CronJob.

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

502 → { "error": "provider_unavailable" }

409 is the important case: Amadeus offers expire within minutes, and the platform does not own seat inventory. A booking records an intent with the offer data frozen at purchase time — it cannot guarantee the seat.
GET /bookings/{booking_id}
200 → Booking

404 → { "error": "booking_not_found" }


4. Data model
Only bookings are persisted. Flight data is never replicated into PostgreSQL — it is fetched from Amadeus and cached in Redis.

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

offer_snapshot stores the complete offer as returned by the provider. Booking history stays readable even after the offer expires upstream, and the schema does not break when the provider changes its response shape.


5. Caching strategy
Key
TTL
Written by
Read by
amadeus:token
~25 min
flights-api
flights-api
search:{origin}:{dest}:{date}:{adults}
SEARCH_CACHE_TTL
flights-api
flights-api
deals:top
DEALS_CACHE_TTL
CronJob
flights-api


Search results are cached, not just deals — otherwise every visitor query consumes provider quota directly. The OAuth2 token is cached separately because it expires on its own schedule and re-requesting it on every call would double the request count.

TTL values are provisional and must be reconciled against the actual Amadeus free tier monthly quota.


6. Open questions
Amadeus free tier: monthly call limit, available endpoints, quality of test data
Which Amadeus endpoint backs /deals — Flight Inspiration Search vs a fixed set of popular routes queried on a schedule
Authentication: currently none. Bookings are identified by contact_email only
CronJob schedule, derived from the quota above

