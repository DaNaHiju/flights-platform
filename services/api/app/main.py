"""FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import bookings, deals, flights
from app.config import settings
from app.database import create_tables, get_db
from app.utils.metrics import request_count, request_duration
from shared import cache
from shared.utils.logging import log


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run startup / shutdown tasks."""
    log.info(
        "Starting %s v%s (env=%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )
    create_tables()
    yield
    log.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title="Flights API",
    description="FastAPI booking service backed by fli (reverse-engineered Google Flights).",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Error responses: contract error bodies are flat ({"error": "..."}), not
# wrapped in FastAPI's default {"detail": ...} envelope.
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def flat_http_exception_handler(request: Request, exc: HTTPException):
    """Unwrap dict `detail` payloads so error bodies match docs/api-contract.md."""
    content = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=content)


# ---------------------------------------------------------------------------
# Middleware: track request metrics
# ---------------------------------------------------------------------------


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record latency and request count for every HTTP call."""
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()
    request_duration.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)

    return response


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["observability"])
def health_check():
    """Liveness only — must not touch Postgres or Redis. See /ready for that."""
    return {"status": "ok"}


@app.get("/ready", tags=["observability"])
def readiness_check(db: Session = Depends(get_db)):
    """Check PostgreSQL and Redis connectivity."""
    postgres_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any DB failure means "not ready"
        postgres_ok = False

    redis_ok = cache.ping()

    body = {
        "postgres": "ok" if postgres_ok else "unreachable",
        "redis": "ok" if redis_ok else "unreachable",
    }
    status_code = 200 if postgres_ok and redis_ok else 503
    return JSONResponse(status_code=status_code, content=body)


@app.get("/metrics", response_class=PlainTextResponse, tags=["observability"])
def metrics():
    """Expose Prometheus metrics in text format."""
    return PlainTextResponse(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ---------------------------------------------------------------------------
# Feature routers
# ---------------------------------------------------------------------------

app.include_router(flights.router, prefix="/flights", tags=["flights"])
app.include_router(deals.router, prefix="/deals", tags=["deals"])
app.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
