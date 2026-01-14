from __future__ import annotations

from app.db.database import SessionLocal
from app.db.models import AILog, User


def add_ai_log(tg_id: int, prompt: str, response: str) -> AILog:
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.tg_id == tg_id).one_or_none()
        if user is None:
            raise ValueError("User not found in DB. Use /start first.")

        log = AILog(user_id=user.id, prompt=prompt, response=response)
        session.add(log)
        session.commit()
        session.refresh(log)
        return log
    finally:
        session.close()
