"""Tests for core application endpoints."""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    """GET /health must return 200 {"status": "ok"} exactly, per the contract."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_check(client: TestClient):
    """GET /ready must return 200 when Postgres and Redis are both reachable."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"postgres": "ok", "redis": "ok"}


def test_metrics_endpoint(client: TestClient):
    """GET /metrics must return 200 with Prometheus text format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
