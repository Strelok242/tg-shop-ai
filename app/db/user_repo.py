from __future__ import annotations

from app.db.database import SessionLocal
from app.db.models import User


def upsert_user(tg_id: int, username: str | None) -> User:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.tg_id == tg_id).one_or_none()
        if user is None:
            user = User(tg_id=tg_id, username=username)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

        # обновим username, если поменялся
        if username and user.username != username:
            user.username = username
            session.commit()
            session.refresh(user)

        return user
    finally:
        session.close()
