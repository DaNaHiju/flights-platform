# jenkins-argocd-platform

CI/CD platform demo: FastAPI flights booking API deployed to Kubernetes via Jenkins + ArgoCD (GitOps). Flight data comes from [`fli`](https://github.com/punitarani/fli) (PyPI: `flights`), which retrieves live Google Flights results by reverse-engineering its internal endpoints — no API key, no official quota. See [docs/api-contract.md](docs/api-contract.md) for the full contract, including why Amadeus/Kiwi/Duffel were evaluated and discarded.

**Repo 1 (this):** Application code, Dockerfile, Jenkinsfile, Terraform infrastructure.  
**Repo 2 (separate):** [jenkins-argocd-manifests](https://github.com/user/jenkins-argocd-manifests) — Helm charts, ArgoCD Applications, staging/prod overlays, and the CronJob that refreshes `/deals`.

---

## Architecture

```
flights-platform/
├── services/
│   └── flights-api/           FastAPI flights booking service
│       ├── app/
│       │   ├── api/           Route handlers: flights, deals, bookings
│       │   ├── jobs/          refresh_deals.py — invoked on a schedule by Repo 2's CronJob
│       │   ├── utils/         JSON logging + Prometheus metrics
│       │   ├── providers.py   fli (Google Flights) search wrapper
│       │   ├── cache.py       Redis client + JSON cache helpers
│       │   ├── models.py      Pydantic schemas + SQLAlchemy ORM
│       │   ├── database.py    PostgreSQL connection (SQLAlchemy)
│       │   └── config.py      Settings from environment variables
│       ├── tests/             pytest test suite (sqlite in-memory, fli/Redis mocked)
│       ├── Dockerfile         Multi-stage build (builder + slim runtime)
│       └── requirements.txt
├── docs/
│   └── api-contract.md        Endpoints, schemas, env vars, caching strategy
├── docker-compose.yml         Local dev: api + PostgreSQL + Redis
├── Jenkinsfile                CI pipeline: lint → test → build → push
├── Makefile                   Dev shortcuts + AWS budget alarm
├── terraform/                 AWS VPC + EKS (used in Project 2)
└── k8s/                       Raw manifests for kind (local cluster)
```

**CI/CD flow:**
1. Developer pushes to `main` → Jenkins picks up via webhook
2. Jenkins: lint → test → `docker build` → `docker push`
3. Jenkins updates image tag in Repo 2 (manifests) — *stage enabled after Repo 2 is ready*
4. ArgoCD detects diff in Repo 2 → syncs to cluster automatically

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Docker | 24+ |
| kind | 0.20+ |
| kubectl | 1.29+ |
| Terraform | 1.6+ |
| AWS CLI | 2.x |

---

## Running locally

### A) Without Kubernetes (docker-compose)

```bash
git clone https://github.com/user/jenkins-argocd-platform.git
cd jenkins-argocd-platform

# Start api + PostgreSQL + Redis
docker-compose up --build

# In a second terminal: run tests
cd services/flights-api
pip install -r requirements.txt
pytest tests/ -v
```

API available at http://localhost:8000  
Docs at http://localhost:8000/docs

### B) With kind (local Kubernetes)

```bash
# 1. Create local cluster
kind create cluster --name jenkins-argocd

# 2. Apply base manifests (namespace + postgres + redis)
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres-local.yaml
kubectl apply -f k8s/redis-local.yaml

# 3. Build and load image into kind
docker build -t flights-api:local services/flights-api
kind load docker-image flights-api:local --name jenkins-argocd

# 4. Verify postgres is ready
kubectl -n jenkins-argocd rollout status statefulset/postgres

# Or use make:
make kind-up
```

### C) AWS (Project 2 scope)

```bash
cd terraform
terraform init
terraform plan
terraform apply   # creates VPC + EKS

# Get kubeconfig
aws eks update-kubeconfig --region us-east-1 --name flights-api-dev-eks

# IMPORTANT: Always destroy when done to stop billing
make destroy
```

---

## Running tests

```bash
cd services/flights-api
pip install -r requirements.txt
pytest tests/ -v --cov=app --cov-report=term-missing
```

fli itself is never called in tests — `search_one_way` and the Redis client are mocked (see `tests/conftest.py`), so the suite runs fully offline.

---

## Linting

```bash
black --check services/flights-api/app/
pylint services/flights-api/app/ --fail-under=7.0

# Or via make:
make lint
```

---

## Building the Docker image

```bash
docker build -t flights-api:v1 services/flights-api

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
make install       # pip install -r services/flights-api/requirements.txt
make lint          # black + pylint
make test          # pytest with coverage
make build         # docker build (services/flights-api)
make run           # docker-compose up
make kind-up       # create kind cluster + apply k8s/
make kind-down     # delete kind cluster
make tf-apply      # terraform apply (AWS)
make destroy       # terraform destroy (ALWAYS after EKS session)
make budget-alarm  # create $10 AWS budget alert
```

---

## Costos — cuenta Free Plan (post-julio 2025)

> Esta cuenta usa creditos AWS (~$200, vigencia 6 meses desde apertura / expiran a los 12 meses).  
> **No hay tier gratuito real para EKS, NAT Gateway ni ALB** — todo consume creditos.

| Recurso | Costo aproximado |
|---------|-----------------|
| EKS cluster | ~$0.10/hora |
| t3.small x2 nodos | ~$0.046/hora c/u |
| NAT Gateway | ~$0.045/hora + datos |
| ALB (cuando se agregue) | ~$0.008/hora + LCU |

**Reglas de oro para no quemar los creditos:**

1. **Siempre correr `make destroy` al terminar una sesion con EKS activo.**
2. Verificar que no queden recursos huerfanos: `aws ec2 describe-instances`, `aws elb describe-load-balancers`.
3. Configurar la alarma de budget antes del primer `terraform apply`: `make budget-alarm ALERT_EMAIL=tu@email.com`
4. **Antes de la sesion del Proyecto 2 (PDF):** pedir aumento de vCPU quota en AWS Console → Service Quotas → EC2 → `Running On-Demand Standard instances` (pedir al menos 8 vCPUs en us-east-1).

---

## Provider risk

`fli` depends on an internal Google Flights endpoint, not a documented public API. Google can change its shape without notice, which would break search until `fli` is updated upstream. There's no SLA or quota to plan capacity against — see the open questions in [docs/api-contract.md](docs/api-contract.md).

---

## Links

- Repo 2 (manifests): https://github.com/user/jenkins-argocd-manifests
- fli / flights on PyPI: https://github.com/punitarani/fli
- FastAPI docs: https://fastapi.tiangolo.com
- ArgoCD docs: https://argo-cd.readthedocs.io
- kind docs: https://kind.sigs.k8s.io
