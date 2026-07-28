"""FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api import cart, orders, products
from app.config import settings
from app.database import create_tables
from app.utils.logging import log
from app.utils.metrics import request_count, request_duration


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
    title="E-Commerce API",
    description="FastAPI-based e-commerce backend for the jenkins-argocd-platform CI/CD demo.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

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
    """Return service liveness status."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


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

app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(cart.router, prefix="/cart", tags=["cart"])
app.include_router(orders.router, prefix="/orders", tags=["orders"])
