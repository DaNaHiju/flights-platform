"""Tests for the products API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

SQLALCHEMY_TEST_URL = "sqlite:///./test_products.db"

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


def test_list_products_empty(client: TestClient):
    """GET /products returns 200 with an empty list when no products exist."""
    response = client.get("/products/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_product(client: TestClient):
    """POST /products creates a product and returns 201."""
    payload = {
        "name": "Widget Pro",
        "description": "A high-quality widget",
        "price": 29.99,
        "stock": 100,
    }
    response = client.post("/products/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Widget Pro"
    assert data["price"] == 29.99
    assert "id" in data


def test_list_products_returns_list(client: TestClient):
    """GET /products returns the created products as a list."""
    client.post(
        "/products/",
        json={"name": "Gadget", "price": 9.99, "stock": 50},
    )
    response = client.get("/products/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1


def test_get_product_by_id(client: TestClient):
    """GET /products/{id} returns the correct product."""
    created = client.post(
        "/products/",
        json={"name": "Single Item", "price": 5.0, "stock": 10},
    ).json()
    response = client.get(f"/products/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_product_not_found(client: TestClient):
    """GET /products/9999 returns 404 for a non-existent product."""
    response = client.get("/products/9999")
    assert response.status_code == 404
