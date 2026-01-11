import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _default_db_url() -> str:
    # SQLite file in ./data/app.db
    return "sqlite:///data/app.db"


DB_URL = os.getenv("DATABASE_URL", _default_db_url())

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
