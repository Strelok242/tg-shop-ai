from __future__ import annotations

from app.db.database import SessionLocal
from app.db.models import Product


def list_active_products(limit: int = 20) -> list[Product]:
    session = SessionLocal()
    try:
        return (
            session.query(Product)
            .filter(Product.is_active.is_(True))
            .order_by(Product.id)
            .limit(limit)
            .all()
        )
    finally:
        session.close()
