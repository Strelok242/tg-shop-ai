from app.db.database import Base, engine
from app.db import models  # noqa: F401  (важно: чтобы модели зарегистрировались)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
