"""Cart API router."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CartItemCreate, CartItemORM, CartItemResponse, ProductORM
from app.utils.logging import log

router = APIRouter()


@router.post("/", response_model=CartItemResponse, status_code=status.HTTP_201_CREATED)
def add_to_cart(payload: CartItemCreate, db: Session = Depends(get_db)):
    """Add a product to the cart identified by session_id."""
    product = db.query(ProductORM).filter(ProductORM.id == payload.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {payload.product_id} not found",
        )
    if product.stock < payload.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient stock",
        )

    item = CartItemORM(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    log.info(
        "Cart add session=%s product=%d qty=%d",
        payload.session_id,
        payload.product_id,
        payload.quantity,
    )
    return item


@router.get("/", response_model=List[CartItemResponse])
def get_cart(session_id: str, db: Session = Depends(get_db)):
    """Return all cart items for a given session."""
    items = (
        db.query(CartItemORM)
        .filter(CartItemORM.session_id == session_id)
        .all()
    )
    return items


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_cart_item(item_id: int, db: Session = Depends(get_db)):
    """Remove a specific item from the cart."""
    item = db.query(CartItemORM).filter(CartItemORM.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cart item {item_id} not found",
        )
    db.delete(item)
    db.commit()
    log.info("Removed cart item id=%d", item_id)
