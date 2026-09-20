# syntax=docker/dockerfile:1
# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip --quiet && \
    pip install --user --no-cache-dir -r requirements.txt

# ── Stage 2: minimal runtime image ───────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy only the installed packages, not the full pip / build toolchain
COPY --from=builder /root/.local /root/.local

# Application source
COPY app/ ./app/

# Ensure local bin (uvicorn, etc.) is on PATH
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    ENVIRONMENT=production \
    DATABASE_URL=postgresql://user:password@postgres:5432/flights \
    REDIS_URL=redis://redis:6379/0

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
