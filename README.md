# jenkins-argocd-platform

CI/CD platform demo: FastAPI e-commerce API deployed to Kubernetes via Jenkins + ArgoCD (GitOps).

**Repo 1 (this):** Application code, Dockerfile, Jenkinsfile, Terraform infrastructure.  
**Repo 2 (separate):** [jenkins-argocd-manifests](https://github.com/user/jenkins-argocd-manifests) — Helm charts, ArgoCD Applications, staging/prod overlays.

---

## Architecture

```
jenkins-argocd-platform/
├── app/                  FastAPI e-commerce service (products, cart, orders)
│   ├── api/              Route handlers
│   ├── utils/            JSON logging + Prometheus metrics
│   ├── models.py         Pydantic schemas + SQLAlchemy ORM
│   ├── database.py       PostgreSQL connection (SQLAlchemy)
│   └── config.py         Settings from environment variables
├── tests/                pytest test suite (sqlite in-memory)
├── Dockerfile            Multi-stage build (builder + slim runtime)
├── docker-compose.yml    Local dev: app + PostgreSQL
├── Jenkinsfile           CI pipeline: lint → test → build → push
├── Makefile              Dev shortcuts + AWS budget alarm
├── terraform/            AWS VPC + EKS (used in Project 2)
└── k8s/                  Raw manifests for kind (local cluster)
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

# Start app + PostgreSQL
docker-compose up --build

# In a second terminal: run tests
pip install -r requirements.txt
pytest tests/ -v
```

API available at http://localhost:8000  
Docs at http://localhost:8000/docs

### B) With kind (local Kubernetes)

```bash
# 1. Create local cluster
kind create cluster --name jenkins-argocd

# 2. Apply base manifests (namespace + postgres)
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres-local.yaml

# 3. Build and load image into kind
docker build -t myapp:local .
kind load docker-image myapp:local --name jenkins-argocd

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
aws eks update-kubeconfig --region us-east-1 --name ecommerce-api-dev-eks

# IMPORTANT: Always destroy when done to stop billing
make destroy
```

---

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## Linting

```bash
black --check app/
pylint app/ --fail-under=7.0

# Or via make:
make lint
```

---

## Building the Docker image

```bash
docker build -t myapp:v1 .

# Verify health check
docker run -e DATABASE_URL=sqlite:/// -p 8000:8000 myapp:v1
curl http://localhost:8000/health
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/metrics` | Prometheus metrics |
| GET | `/products/` | List products |
| POST | `/products/` | Create product |
| GET | `/products/{id}` | Get product |
| POST | `/cart/` | Add to cart |
| GET | `/cart/?session_id=X` | View cart |
| DELETE | `/cart/{item_id}` | Remove cart item |
| POST | `/orders/` | Create order |
| GET | `/orders/` | List orders |
| GET | `/orders/{id}` | Get order |

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
make install       # pip install -r requirements.txt
make lint          # black + pylint
make test          # pytest with coverage
make build         # docker build
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

## Links

- Repo 2 (manifests): https://github.com/user/jenkins-argocd-manifests
- FastAPI docs: https://fastapi.tiangolo.com
- ArgoCD docs: https://argo-cd.readthedocs.io
- kind docs: https://kind.sigs.k8s.io
