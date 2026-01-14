from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Order, User


def list_orders_by_tg_id(tg_id: int, limit: int = 5) -> list[Order]:
    session: Session = SessionLocal()
    try:
        user = session.query(User).filter(User.tg_id == tg_id).one_or_none()
        if user is None:
            return []

        return (
            session.query(Order)
            .filter(Order.user_id == user.id)
            .order_by(Order.id.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()
