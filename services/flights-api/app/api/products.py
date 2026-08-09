"""Products API router."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProductCreate, ProductORM, ProductResponse
from app.utils.logging import log
from app.utils.metrics import inventory_updates

router = APIRouter()


@router.get("/", response_model=List[ProductResponse])
def list_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Return a paginated list of all products."""
    products = db.query(ProductORM).offset(skip).limit(limit).all()
    log.info("list_products returned %d items", len(products))
    return products


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Return a single product by ID or 404."""
    product = db.query(ProductORM).filter(ProductORM.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {product_id} not found",
        )
    return product


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    """Create and persist a new product."""
    product = ProductORM(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    inventory_updates.inc()
    log.info("Created product id=%d name=%s", product.id, product.name)
    return product
