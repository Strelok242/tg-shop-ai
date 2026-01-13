from __future__ import annotations

from sqlalchemy import func

from app.db.database import SessionLocal
from app.db.models import Order, OrderItem, Product, User


def get_product_by_sku(sku: str) -> Product | None:
    session = SessionLocal()
    try:
        return (
            session.query(Product)
            .filter(Product.sku == sku, Product.is_active.is_(True))
            .one_or_none()
        )
    finally:
        session.close()


def create_order_for_user(tg_id: int, sku: str, qty: int = 1) -> Order:
    if qty < 1:
        qty = 1

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.tg_id == tg_id).one_or_none()
        if user is None:
            raise ValueError("User not found in DB. Use /start first.")

        product = (
            session.query(Product)
            .filter(Product.sku == sku, Product.is_active.is_(True))
            .one_or_none()
        )
        if product is None:
            raise ValueError("Product not found. Check SKU or use /catalog.")

        order = Order(user_id=user.id, status="new", total_cents=0)
        session.add(order)
        session.flush()  # получить order.id

        item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            qty=qty,
            price_cents=product.price_cents,
        )
        session.add(item)
        session.flush()  # важно: autocommit/autoflush выключены, иначе SUM может не увидеть item

        total = (
            session.query(func.sum(OrderItem.qty * OrderItem.price_cents))
            .filter(OrderItem.order_id == order.id)
            .scalar()
        )
        order.total_cents = int(total or 0)

        session.commit()
        session.refresh(order)
        return order
    finally:
        session.close()
