"""Pydantic request/response models and SQLAlchemy ORM models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class ProductORM(Base):
    """SQLAlchemy model for the products table."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    cart_items = relationship("CartItemORM", back_populates="product")
    order_items = relationship("OrderItemORM", back_populates="product")


class CartItemORM(Base):
    """SQLAlchemy model for the cart_items table."""

    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())

    product = relationship("ProductORM", back_populates="cart_items")


class OrderStatus(str, enum.Enum):
    """Allowed order lifecycle states."""

    pending = "pending"
    confirmed = "confirmed"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class OrderORM(Base):
    """SQLAlchemy model for the orders table."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_email = Column(String(255), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending)
    total_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())

    items = relationship("OrderItemORM", back_populates="order")


class OrderItemORM(Base):
    """SQLAlchemy model for the order_items table."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)

    order = relationship("OrderORM", back_populates="items")
    product = relationship("ProductORM", back_populates="order_items")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ProductCreate(BaseModel):
    """Payload to create a new product."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    stock: int = Field(default=0, ge=0)


class ProductResponse(BaseModel):
    """Product representation returned by the API."""

    id: int
    name: str
    description: Optional[str]
    price: float
    stock: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CartItemCreate(BaseModel):
    """Payload to add an item to the cart."""

    product_id: int
    quantity: int = Field(default=1, ge=1)
    session_id: str = Field(..., min_length=1, max_length=64)


class CartItemResponse(BaseModel):
    """Cart item representation returned by the API."""

    id: int
    session_id: str
    product_id: int
    quantity: int
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderItemCreate(BaseModel):
    """Single line item inside an order creation payload."""

    product_id: int
    quantity: int = Field(default=1, ge=1)


class OrderCreate(BaseModel):
    """Payload to create a new order."""

    customer_email: str = Field(..., min_length=5)
    items: List[OrderItemCreate] = Field(..., min_length=1)


class OrderItemResponse(BaseModel):
    """Order line item returned by the API."""

    id: int
    product_id: int
    quantity: int
    unit_price: float

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    """Order representation returned by the API."""

    id: int
    customer_email: str
    status: OrderStatus
    total_amount: float
    created_at: datetime
    items: List[OrderItemResponse] = []

    model_config = {"from_attributes": True}
