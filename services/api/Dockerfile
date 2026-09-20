# syntax=docker/dockerfile:1
# Build context is the REPO ROOT (not services/api/) so that shared/ is reachable:
#   docker build -f services/api/Dockerfile .
# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY services/api/requirements.txt .

# --prefix (not --user): installs under /install, which the runtime stage copies
# into /usr/local. Readable by any UID and independent of $HOME.
RUN pip install --upgrade pip --quiet && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: minimal runtime image ───────────────────────────────────────────
FROM python:3.11-slim

# Non-root runtime user. Numeric UID/GID so the kubelet can verify runAsNonRoot
# (it cannot resolve a user name to check that it is not root).
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

# Copy only the installed packages, not the full pip / build toolchain
COPY --from=builder /install /usr/local

# Application source: shared/ (common code) + the API package.
# Left root-owned on purpose: the app user can read it but not modify it.
COPY shared/ ./shared/
COPY services/api/app/ ./app/

# /app on PYTHONPATH makes both `app` and `shared` importable
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    ENVIRONMENT=production \
    DATABASE_URL=postgresql://user:password@postgres:5432/flights \
    REDIS_URL=redis://redis:6379/0

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
