"""Tests for the orders API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

SQLALCHEMY_TEST_URL = "sqlite:///./test_orders.db"

engine = create_engine(
    SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def existing_product(client: TestClient) -> dict:
    """Create a product and return its JSON response."""
    response = client.post(
        "/products/",
        json={"name": "Test Product", "price": 10.0, "stock": 50},
    )
    return response.json()


def test_create_order_valid(client: TestClient, existing_product: dict):
    """POST /orders with a valid payload returns 201 and the order data."""
    payload = {
        "customer_email": "buyer@example.com",
        "items": [{"product_id": existing_product["id"], "quantity": 2}],
    }
    response = client.post("/orders/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["customer_email"] == "buyer@example.com"
    assert data["total_amount"] == 20.0
    assert data["status"] == "pending"
    assert len(data["items"]) == 1


def test_create_order_no_items(client: TestClient):
    """POST /orders without items returns 422 (validation error)."""
    payload = {"customer_email": "buyer@example.com", "items": []}
    response = client.post("/orders/", json=payload)
    # Pydantic min_length=1 on items list raises 422
    assert response.status_code == 422


def test_create_order_nonexistent_product(client: TestClient):
    """POST /orders referencing a missing product returns 400."""
    payload = {
        "customer_email": "buyer@example.com",
        "items": [{"product_id": 99999, "quantity": 1}],
    }
    response = client.post("/orders/", json=payload)
    assert response.status_code == 400


def test_create_order_insufficient_stock(client: TestClient, existing_product: dict):
    """POST /orders requesting more stock than available returns 400."""
    payload = {
        "customer_email": "buyer@example.com",
        "items": [{"product_id": existing_product["id"], "quantity": 9999}],
    }
    response = client.post("/orders/", json=payload)
    assert response.status_code == 400


def test_list_orders(client: TestClient, existing_product: dict):
    """GET /orders returns all created orders."""
    client.post(
        "/orders/",
        json={
            "customer_email": "a@b.com",
            "items": [{"product_id": existing_product["id"], "quantity": 1}],
        },
    )
    response = client.get("/orders/")
    assert response.status_code == 200
    assert len(response.json()) == 1
