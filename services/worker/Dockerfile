# syntax=docker/dockerfile:1
# Build context is the REPO ROOT (not services/worker/) so that shared/ is reachable:
#   docker build -f services/worker/Dockerfile .
# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY services/worker/requirements.txt .

# --prefix (not --user): installs under /install, which the runtime stage copies
# into /usr/local. Readable by any UID and independent of $HOME.
RUN pip install --upgrade pip --quiet && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: minimal runtime image ───────────────────────────────────────────
FROM python:3.12-slim

# Non-root runtime user. Numeric UID/GID so the kubelet can verify runAsNonRoot
# (it cannot resolve a user name to check that it is not root).
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Copy only the installed packages, not the full pip / build toolchain
COPY --from=builder /install /usr/local

# Application source: shared/ (common code) + the worker package.
# Left root-owned on purpose: the app user can read it but not modify it.
COPY shared/ ./shared/
COPY services/worker/worker/ ./worker/

# /app on PYTHONPATH makes both `worker` and `shared` importable.
# REDIS_URL is deliberately NOT set here: it is injected at runtime (ConfigMap
# in Kubernetes, docker-compose.yml locally). The worker needs no DATABASE_URL.
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    ENVIRONMENT=production \
    APP_NAME=flights-worker

USER 10001:10001

# No EXPOSE and no HEALTHCHECK: this is not a server. It runs one refresh and
# exits; the CronJob (manifests repo) reads its exit code.
CMD ["python", "-m", "worker.refresh_deals"]
