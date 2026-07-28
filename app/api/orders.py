"""Orders API router."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    OrderCreate,
    OrderItemORM,
    OrderORM,
    OrderResponse,
    ProductORM,
)
from app.utils.logging import log
from app.utils.metrics import orders_created

router = APIRouter()


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    """Create an order; validates stock and computes total."""
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item",
        )

    total = 0.0
    order_items = []

    for line in payload.items:
        product = db.query(ProductORM).filter(ProductORM.id == line.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {line.product_id} not found",
            )
        if product.stock < line.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for product {line.product_id}",
            )
        total += product.price * line.quantity
        order_items.append(
            OrderItemORM(
                product_id=line.product_id,
                quantity=line.quantity,
                unit_price=product.price,
            )
        )
        product.stock -= line.quantity

    order = OrderORM(
        customer_email=payload.customer_email,
        total_amount=round(total, 2),
    )
    db.add(order)
    db.flush()

    for item in order_items:
        item.order_id = order.id
        db.add(item)

    db.commit()
    db.refresh(order)

    orders_created.inc()
    log.info(
        "Order created id=%d email=%s total=%.2f",
        order.id,
        order.customer_email,
        order.total_amount,
    )
    return order


@router.get("/", response_model=List[OrderResponse])
def list_orders(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Return a paginated list of all orders."""
    return db.query(OrderORM).offset(skip).limit(limit).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """Return a single order by ID or 404."""
    order = db.query(OrderORM).filter(OrderORM.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )
    return order
