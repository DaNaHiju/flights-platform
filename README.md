# flights-platform

API de búsqueda y reserva de vuelos (FastAPI), repo de código de aplicación.

**This repo:** Application code, Dockerfile.  
**Infra repo:** [flights-platform-infra](https://github.com/danahiju/flights-platform-infra) — Terraform (EKS, VPC, IAM, ECR, backend).  
**Manifests repo:** [flights-platform-manifests](https://github.com/danahiju/flights-platform-manifests) — Helm charts, ArgoCD Applications, staging/prod overlays, and the CronJob that refreshes `/deals`.

---

## Architecture

```
flights-platform/
├── shared/                    Code shared across services (imported as `shared.*`)
│   ├── utils/                 JSON logging + provider_errors metric
│   ├── providers.py           fli (Google Flights) search wrapper
│   ├── cache.py               Redis client + JSON cache helpers
│   ├── schemas.py             Pydantic flight schemas (FlightOffer, Leg, Deal)
│   └── config.py              Shared settings (REDIS_URL, ...) + require_env() check
├── services/
│   ├── api/                   FastAPI flights booking service
│   │   ├── app/
│   │   │   ├── api/           Route handlers: flights, deals, bookings
│   │   │   ├── config.py      API settings (DATABASE_URL, ...) on top of shared
│   │   │   ├── utils/         HTTP + bookings Prometheus metrics
│   │   │   ├── db_models.py   SQLAlchemy ORM + booking schemas
│   │   │   └── database.py    PostgreSQL connection (SQLAlchemy)
│   │   ├── tests/             pytest test suite (sqlite in-memory, fli/Redis mocked)
│   │   ├── Dockerfile         Multi-stage build; context is the repo root
│   │   └── requirements.txt
│   └── worker/                Deals refresh job — run on a schedule by Repo 2's CronJob
│       ├── worker/            refresh_deals.py + worker settings (no DATABASE_URL)
│       ├── tests/             pytest test suite (fli/Redis mocked)
│       ├── Dockerfile         Multi-stage build; context is the repo root; no HEALTHCHECK
│       └── requirements.txt   Subset of the api's pins: no fastapi/sqlalchemy/psycopg2
├── docs/
│   └── api-contract.md        Endpoints, schemas, env vars, caching strategy
├── pytest.ini                 Puts the repo root on the path so `shared` resolves
├── docker-compose.yml         Local dev: api + worker + PostgreSQL + Redis
└── Makefile                   Dev shortcuts
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12 |
| Docker | 24+ |

---

## Running locally

```bash
git clone https://github.com/danahiju/flights-platform.git
cd flights-platform

# Start api + PostgreSQL + Redis
docker-compose up --build

# In a second terminal: run tests
cd services/api
pip install -r requirements.txt
pytest tests/ -v
```

API available at http://localhost:8000  
Docs at http://localhost:8000/docs

---

## Running tests

```bash
cd services/api
pip install -r requirements.txt
pytest tests/ -v --cov=app --cov-report=term-missing
```

fli itself is never called in tests — `search_one_way` and the Redis client are mocked (see `tests/conftest.py`), so the suite runs fully offline.

---

## Linting

```bash
black --check services/api/app/ shared/
pylint services/api/app/ shared/ --fail-under=7.0

# Or via make:
make lint
```

---

## Building the Docker image

```bash
# Run from the repo root: the build context must include shared/
docker build -f services/api/Dockerfile -t flights-api:v1 .

# Verify health check
docker run -e DATABASE_URL=sqlite:/// -p 8000:8000 flights-api:v1
curl http://localhost:8000/health
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (Postgres + Redis) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/flights/?origin=&destination=&date=&adults=` | Search live one-way offers |
| GET | `/deals/?limit=` | Top cached deals from `FLIGHTS_DEFAULT_ORIGIN` |
| POST | `/bookings/` | Register a booking against a previously returned offer |
| GET | `/bookings/{id}` | Get a booking |

Full request/response schemas: [docs/api-contract.md](docs/api-contract.md).

---

## Branch strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready code; triggers full CI + image push |
| `develop` | Integration branch; runs lint + tests only |
| `feature/*` | Feature branches; PR into develop |

---

## Makefile targets

```bash
make install       # pip install -r services/api/requirements.txt
make lint          # black + pylint
make test          # pytest with coverage
make build         # docker build (context = repo root)
make run           # docker-compose up
```

---

## Provider risk

`fli` depends on an internal Google Flights endpoint, not a documented public API. Google can change its shape without notice, which would break search until `fli` is updated upstream. There's no SLA or quota to plan capacity against — see the open questions in [docs/api-contract.md](docs/api-contract.md).

---

## Links

- Infra repo: https://github.com/danahiju/flights-platform-infra
- Manifests repo: https://github.com/danahiju/flights-platform-manifests
- fli / flights on PyPI: https://github.com/punitarani/fli
- FastAPI docs: https://fastapi.tiangolo.com
- ArgoCD docs: https://argo-cd.readthedocs.io

---

## Estado

README en reescritura. Este repo se está reorganizando hacia un layout multi-servicio (api + worker + shared) con CI en GitHub Actions. La versión completa llega al cerrar esa migración.
